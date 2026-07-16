# backend/app/pipeline/measure.py
import json
import os
import cv2
import numpy as np
import open3d as o3d

from app.pipeline.colmap_geometry import load_reconstruction, get_projection_matrix, triangulate_multiview


def find_scale_reference(scene_out: str, images_dir: str, known_marker_size_m: float = 0.10) -> float | None:
    """Detects an ArUco marker across all undistorted images, triangulates its 4 corners
    into real COLMAP-space 3D points using actual camera poses, then compares that
    triangulated size to the known physical marker size to get units-per-meter.
    Returns None if the marker isn't visible in at least 2 images (falls back to
    unscaled/relative measurements)."""
    recon = load_reconstruction(scene_out)
    aruco_detector = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50))

    # corner_observations[corner_idx] = list of (K, Rt, pixel_xy)
    corner_observations = {0: [], 1: [], 2: [], 3: []}

    for fname in os.listdir(images_dir):
        if not fname.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        img = cv2.imread(os.path.join(images_dir, fname))
        if img is None:
            continue
        corners, ids, _ = aruco_detector.detectMarkers(img)
        if ids is None or len(corners) == 0:
            continue

        try:
            K, Rt = get_projection_matrix(recon, fname)
        except KeyError:
            continue  # image wasn't registered by COLMAP — skip

        marker_corners = corners[0][0]  # (4, 2)
        for i in range(4):
            corner_observations[i].append((K, Rt, marker_corners[i]))

    # Need the marker seen from >=2 registered views to triangulate
    if any(len(obs) < 2 for obs in corner_observations.values()):
        print("[measure] ArUco marker not visible from enough registered views — "
              "falling back to unscaled measurements")
        return None

    corners_3d = np.array([
        triangulate_multiview(corner_observations[i]) for i in range(4)
    ])

    # Average the 4 edge lengths of the triangulated marker in COLMAP units
    edge_lengths = [
        np.linalg.norm(corners_3d[i] - corners_3d[(i + 1) % 4]) for i in range(4)
    ]
    triangulated_size = float(np.mean(edge_lengths))

    if triangulated_size <= 1e-6:
        print("[measure] Degenerate marker triangulation — skipping scale calibration")
        return None

    scale_factor = known_marker_size_m / triangulated_size
    print(f"[measure] Scale calibrated: {triangulated_size:.4f} colmap-units == "
          f"{known_marker_size_m}m -> scale_factor={scale_factor:.6f}")
    return scale_factor


def measure_scene(job_output_dir: str, scale_factor: float | None) -> dict:
    pcd_path = os.path.join(job_output_dir, "sparse", "0", "points3D_cleaned.ply")
    if not os.path.exists(pcd_path):
        pcd_path = os.path.join(job_output_dir, "sparse", "0", "points3D.ply")

    pcd = o3d.io.read_point_cloud(pcd_path)
    bbox = pcd.get_axis_aligned_bounding_box()
    extent = np.array(bbox.get_extent())

    scaled = scale_factor is not None
    dims = extent * scale_factor if scaled else extent

    return {
        "scaled": scaled,
        "unit": "m" if scaled else "colmap_units",
        "room_dimensions": {"x": float(dims[0]), "y": float(dims[1]), "z": float(dims[2])},
    }


def measure_evidence(evidence_list: list[dict], scale_factor: float | None) -> list[dict]:
    scaled = scale_factor is not None
    results = []
    for item in evidence_list:
        pts = np.array(item["points"])
        if len(pts) == 0:
            continue
        item_bbox = o3d.geometry.AxisAlignedBoundingBox(pts.min(axis=0), pts.max(axis=0))
        extent = np.array(item_bbox.get_extent())
        dims = extent * scale_factor if scaled else extent
        results.append({
            "id": item["id"],
            "label": item.get("label"),
            "dimensions": {"x": float(dims[0]), "y": float(dims[1]), "z": float(dims[2])},
            "centroid": pts.mean(axis=0).tolist(),
        })
    return results


def run_measure(job_output_dir: str, images_dir: str, evidence_json_path: str | None = None) -> dict:
    try:
        scale_factor = find_scale_reference(job_output_dir, images_dir)
    except Exception as e:
        print(f"[measure] Scale calibration failed ({e}) — using unscaled units")
        scale_factor = None

    scene_stats = measure_scene(job_output_dir, scale_factor)

    evidence_results = []
    if evidence_json_path and os.path.exists(evidence_json_path):
        with open(evidence_json_path) as f:
            evidence_list = json.load(f)
        evidence_results = measure_evidence(evidence_list, scale_factor)

    output = {**scene_stats, "evidence": evidence_results}

    out_path = os.path.join(job_output_dir, "measurements.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    return output