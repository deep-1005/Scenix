import os
import subprocess
import numpy as np
import pycolmap  # type: ignore


COLMAP_ENV = {
    **os.environ,
    "PATH": "/home/cave/miniconda3/envs/forensic/bin:" + os.environ.get("PATH", ""),
    "CUDA_HOME": "/home/cave/miniconda3/envs/forensic",
    "LD_LIBRARY_PATH": (
        "/home/cave/miniconda3/envs/forensic/lib/python3.11/site-packages/torch/lib:"
        + os.environ.get("LD_LIBRARY_PATH", "")
    ),
}


def _run(cmd, stream=False):
    print("[colmap] $", " ".join(cmd), flush=True)
    if stream:
        result = subprocess.run(cmd, env=COLMAP_ENV)
        if result.returncode != 0:
            raise RuntimeError(f"COLMAP step failed: {' '.join(cmd[:2])}")
        return ""
    result = subprocess.run(cmd, capture_output=True, text=True, env=COLMAP_ENV)
    if result.returncode != 0:
        raise RuntimeError(
            f"COLMAP step failed: {' '.join(cmd[:2])}\n"
            f"STDERR:\n{result.stderr[-2000:]}"
        )
    return result.stdout


def _model_exists(model0: str) -> bool:
    """
    Check that all three required COLMAP output files exist (either .bin or .txt).
    FastGS accepts both formats so we check for either.
    """
    for stem in ("cameras", "images", "points3D"):
        has_bin = os.path.exists(os.path.join(model0, f"{stem}.bin"))
        has_txt = os.path.exists(os.path.join(model0, f"{stem}.txt"))
        if not has_bin and not has_txt:
            return False
    return True


def _camera_center(image):
    try:
        c = image.project_center()
        return [float(c[0]), float(c[1]), float(c[2])]
    except Exception:
        pass
    try:
        c = image.projection_center()
        return [float(c[0]), float(c[1]), float(c[2])]
    except Exception:
        pass
    try:
        cfw = image.cam_from_world
        R = np.array(cfw.rotation.matrix())
        t = np.array(cfw.translation)
        C = -R.T @ t
        return [float(C[0]), float(C[1]), float(C[2])]
    except Exception:
        return None


def run_colmap(images_dir: str, work_dir: str, use_gpu: bool = False) -> dict:
    os.makedirs(work_dir, exist_ok=True)

    db_path   = os.path.join(work_dir, "database.db")
    sparse_dir = os.path.join(work_dir, "sparse")
    os.makedirs(sparse_dir, exist_ok=True)

    gpu_flag = "1" if use_gpu else "0"

    # 1) Feature extraction — PINHOLE required for FastGS compatibility
    _run([
        "colmap", "feature_extractor",
        "--database_path", db_path,
        "--image_path",    images_dir,
        "--ImageReader.single_camera_per_image", "1",
        "--ImageReader.camera_model",            "PINHOLE",
        "--FeatureExtraction.use_gpu",           gpu_flag,
    ], stream=True)

    # 2) Exhaustive matching
    _run([
        "colmap", "exhaustive_matcher",
        "--database_path",          db_path,
        "--FeatureMatching.use_gpu", gpu_flag,
    ], stream=True)

    # 3) Mapper
    _run([
        "colmap", "mapper",
        "--database_path", db_path,
        "--image_path",    images_dir,
        "--output_path",   sparse_dir,
    ], stream=True)

    model0 = os.path.join(sparse_dir, "0")

    if not os.path.isdir(model0) or not _model_exists(model0):
        raise RuntimeError(
            "COLMAP produced no reconstruction. Usual causes: too little overlap "
            "between views, or the camera did not physically move between panoramas."
        )

    print(f"[colmap] Reconstruction OK — sparse/0/ contains: {os.listdir(model0)}", flush=True)

    # 4) Export point cloud to PLY for the viewer
    ply_path = os.path.join(work_dir, "points.ply")
    _run([
        "colmap", "model_converter",
        "--input_path",  model0,
        "--output_path", ply_path,
        "--output_type", "PLY",
    ])

    # 5) Parse reconstruction stats via pycolmap
    recon = pycolmap.Reconstruction(model0)

    cameras = []
    try:
        for image in recon.images.values():
            center = _camera_center(image)
            if center is not None:
                cameras.append({"name": image.name, "position": center})
    except Exception as e:
        print(f"[colmap] camera positions unavailable: {e}", flush=True)

    try:
        n_reg = recon.num_reg_images()
    except Exception:
        n_reg = len(recon.images)

    summary = {
        "registered_images": n_reg,
        "points3D":          recon.num_points3D(),
        "cameras":           len(recon.cameras),
        "camera_positions":  cameras,
        "ply_file":          "points.ply",
        "model_path":        model0,
    }

    print(
        f"[colmap] {summary['registered_images']} images, "
        f"{summary['points3D']} points, "
        f"{len(cameras)} camera markers",
        flush=True,
    )

    return summary