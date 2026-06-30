import open3d as o3d
import numpy as np
import json
import os
import gc
import logging

logger = logging.getLogger(__name__)


def auto_tune(pcd):
    """
    FIX: the previous version's nearest-neighbor sampling loop ran 2000
    individual search_knn_vector_3d calls in a tight Python loop, which is
    slow but shouldn't crash on its own. The real risk is that Open3D's
    KDTreeFlann build + repeated queries can spike memory hard on certain
    builds/driver combos when run right after a CUDA-heavy process (COLMAP)
    has left the GPU/driver state under pressure. We reduce the sample size
    and add explicit cleanup to lower peak memory.
    """
    points = np.asarray(pcd.points)
    bbox = pcd.get_axis_aligned_bounding_box()
    extent = np.asarray(bbox.get_extent())

    pcd_tree = o3d.geometry.KDTreeFlann(pcd)
    distances = []
    # Reduced from 2000 -> 800: still a solid statistical sample for
    # auto-tuning spacing, far less memory/CPU pressure.
    sample = min(800, len(points))
    indices = np.random.choice(len(points), sample, replace=False)
    for i in indices:
        _, _, dist = pcd_tree.search_knn_vector_3d(points[i], 2)
        distances.append(np.sqrt(dist[1]))

    avg_spacing = float(np.mean(distances))

    # Explicitly drop the tree and force a collection before returning —
    # KDTreeFlann holds a fair amount of native memory that doesn't always
    # get reclaimed promptly otherwise.
    del pcd_tree
    gc.collect()

    return {
        "ransac_thresh" : float(np.clip(avg_spacing * 5,  0.01, 0.1)),
        "dbscan_eps"    : float(np.clip(avg_spacing * 20, 0.05, 2.0)),
        "dbscan_minpts" : max(5, int(len(points) * 0.0001)),
        "sor_neighbors" : 20,
        "sor_std"       : 1.5,
        "bbox_std"      : 2.5,
    }


def load_optuna_params(job_output_dir):
    """Load Optuna params if they exist for this job, else return None."""
    params_path = os.path.join(job_output_dir, "best_params.json")
    if os.path.exists(params_path):
        with open(params_path) as f:
            return json.load(f)
    return None


def clean_point_cloud(input_ply: str, output_ply: str, job_output_dir: str = None) -> dict:
    """
    Full cleaning pipeline: auto-tune → RANSAC → BBox crop → DBSCAN → SOR → save.
    Returns a dict with stats. Also writes a copy of the RAW (pre-clean)
    point cloud alongside the output so the UI can show a before/after
    comparison.
    """
    logger.info(f"[clean] Loading: {input_ply}")
    pcd = o3d.io.read_point_cloud(input_ply)
    original_count = len(pcd.points)
    logger.info(f"[clean] {original_count:,} points loaded")

    if original_count == 0:
        raise ValueError(f"Empty point cloud at {input_ply}")

    # Save an explicit "raw" copy for the before/after comparison view,
    # independent of whatever input_ply's lifecycle is.
    if job_output_dir:
        raw_copy_path = os.path.join(job_output_dir, "points_raw.ply")
        try:
            o3d.io.write_point_cloud(raw_copy_path, pcd)
            logger.info(f"[clean] Saved raw copy for comparison: {raw_copy_path}")
        except Exception as e:
            logger.warning(f"[clean] Could not save raw comparison copy: {e}")

    # ── Parameters ──────────────────────────────────────────
    params = None
    if job_output_dir:
        params = load_optuna_params(job_output_dir)
    if params:
        logger.info("[clean] Using Optuna params")
    else:
        logger.info("[clean] Auto-tuning params from scene stats")
        params = auto_tune(pcd)
        gc.collect()

    ransac_thresh = params["ransac_thresh"]
    dbscan_eps    = params["dbscan_eps"]
    dbscan_minpts = params["dbscan_minpts"]
    sor_neighbors = params.get("sor_neighbors", 20)
    sor_std       = params["sor_std"]
    bbox_std      = params.get("bbox_std", 2.5)

    logger.info(f"[clean] Params: ransac={ransac_thresh:.4f} eps={dbscan_eps:.4f} "
                f"minpts={dbscan_minpts} sor_std={sor_std:.2f} bbox_std={bbox_std:.2f}")

    # ── RANSAC plane detection (visualisation only — keep full cloud) ──
    _, inliers = pcd.segment_plane(
        distance_threshold=ransac_thresh,
        ransac_n=3,
        num_iterations=1000
    )
    logger.info(f"[clean] RANSAC: {len(inliers):,} plane inliers detected (kept in cloud)")
    gc.collect()

    # ── BBox crop ───────────────────────────────────────────
    points = np.asarray(pcd.points)
    center = np.mean(points, axis=0)
    std    = np.std(points, axis=0)
    mask   = np.all(np.abs(points - center) < bbox_std * std, axis=1)
    pcd    = pcd.select_by_index(np.where(mask)[0])
    logger.info(f"[clean] BBox crop: {len(pcd.points):,} points remaining")
    del points, mask
    gc.collect()

    # ── DBSCAN ──────────────────────────────────────────────
    labels = np.array(pcd.cluster_dbscan(
        eps=dbscan_eps, min_points=dbscan_minpts, print_progress=False
    ))
    valid = set(labels) - {-1}
    if valid:
        biggest = max(valid, key=lambda l: np.sum(labels == l))
        pcd     = pcd.select_by_index(np.where(labels == biggest)[0])
        logger.info(f"[clean] DBSCAN: kept largest cluster, {len(pcd.points):,} points")
    else:
        logger.warning("[clean] DBSCAN found no clusters — skipping cluster step")
    del labels
    gc.collect()

    # ── Statistical Outlier Removal ─────────────────────────
    before    = len(pcd.points)
    pcd, _    = pcd.remove_statistical_outlier(
        nb_neighbors=sor_neighbors, std_ratio=sor_std
    )
    logger.info(f"[clean] SOR: removed {before - len(pcd.points):,} outliers")
    gc.collect()

    # ── Save ────────────────────────────────────────────────
    os.makedirs(os.path.dirname(output_ply), exist_ok=True)
    o3d.io.write_point_cloud(output_ply, pcd)
    final_count = len(pcd.points)
    logger.info(f"[clean] Saved: {output_ply} ({final_count:,} points)")

    return {
        "original_points" : original_count,
        "final_points"    : final_count,
        "points_removed"  : original_count - final_count,
        "structure_kept"  : round(final_count / original_count * 100, 1),
        "output_ply"      : output_ply,
        "raw_ply"         : os.path.join(job_output_dir, "points_raw.ply") if job_output_dir else None,
        "params_used"     : params,
    }