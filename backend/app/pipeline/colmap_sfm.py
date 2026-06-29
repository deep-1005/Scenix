import os
import shutil
import subprocess
import numpy as np
import pycolmap  # type: ignore

COLMAP_BIN = "/home/cave/miniconda3/envs/forensic/bin/colmap"

# Resize panoramas to this width before COLMAP — 11968px is way too large
# 3000px wide = 1500px tall, still very detailed, much faster matching
MAX_COLMAP_WIDTH = 3000


def _resize_images(src_dir: str, dst_dir: str, max_width: int) -> str:
    """Resize images to max_width if larger, copy as-is if smaller."""
    try:
        import cv2
    except ImportError:
        # No cv2 — just symlink/copy as-is
        if src_dir != dst_dir:
            shutil.copytree(src_dir, dst_dir, dirs_exist_ok=True)
        return dst_dir

    os.makedirs(dst_dir, exist_ok=True)
    exts = (".jpg", ".jpeg", ".png")
    for fname in sorted(os.listdir(src_dir)):
        if not fname.lower().endswith(exts):
            continue
        src = os.path.join(src_dir, fname)
        dst = os.path.join(dst_dir, fname)
        img = cv2.imread(src)
        if img is None:
            continue
        h, w = img.shape[:2]
        if w > max_width:
            scale = max_width / w
            img = cv2.resize(img, (max_width, int(h * scale)), interpolation=cv2.INTER_AREA)
            print(f"[colmap] resized {fname}: {w}x{h} -> {img.shape[1]}x{img.shape[0]}", flush=True)
        cv2.imwrite(dst, img, [cv2.IMWRITE_JPEG_QUALITY, 92])
    return dst_dir


def _run(cmd, stream=False):
    print("[colmap] $", " ".join(str(c) for c in cmd), flush=True)
    if stream:
        result = subprocess.run(cmd)
        if result.returncode != 0:
            raise RuntimeError(f"COLMAP step failed: {' '.join(str(c) for c in cmd[:2])}")
        return ""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"COLMAP step failed: {' '.join(str(c) for c in cmd[:2])}\n"
            f"STDERR:\n{result.stderr[-2000:]}"
        )
    return result.stdout


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
    """
    Run COLMAP on equirectangular 360 panoramas.
    - Resizes images to MAX_COLMAP_WIDTH first (11968px is too large for COLMAP)
    - Uses SIMPLE_RADIAL camera model (SPHERICAL not in this COLMAP build)
    - One camera model shared per folder (single_camera=1)
    """
    os.makedirs(work_dir, exist_ok=True)

    # Step 0: Resize images to a manageable size
    resized_dir = os.path.join(work_dir, "colmap_images_resized")
    print(f"[colmap] Resizing images to max width {MAX_COLMAP_WIDTH}px...", flush=True)
    images_dir = _resize_images(images_dir, resized_dir, MAX_COLMAP_WIDTH)

    db_path    = os.path.join(work_dir, "database.db")
    sparse_dir = os.path.join(work_dir, "sparse")
    os.makedirs(sparse_dir, exist_ok=True)

    gpu_flag = "1" if use_gpu else "0"

    # 1) Feature extraction
    #    SIMPLE_PINHOLE — FastGS ONLY accepts PINHOLE or SIMPLE_PINHOLE.
    #    single_camera=1 means all images share one camera model (same physical camera).
    _run([
        COLMAP_BIN, "feature_extractor",
        "--database_path", db_path,
        "--image_path", images_dir,
        "--ImageReader.single_camera", "1",
        "--ImageReader.camera_model", "SIMPLE_PINHOLE",
        "--FeatureExtraction.use_gpu", gpu_flag,
        "--FeatureExtraction.num_threads", "-1",
        "--SiftExtraction.max_num_features", "16384",
        "--SiftExtraction.peak_threshold", "0.003",
        "--SiftExtraction.max_image_size", "3200",
    ], stream=True)

    # 2) Matching — sequential first (catches adjacent views), then vocab tree for loop closure
    # For 450-1050 images, exhaustive is too slow. Sequential + vocab tree is standard.
    _run([
        COLMAP_BIN, "sequential_matcher",
        "--database_path", db_path,
        "--FeatureMatching.use_gpu", gpu_flag,
        "--SequentialMatching.overlap", "15",
        "--SequentialMatching.quadratic_overlap", "1",
        "--SequentialMatching.loop_detection", "1",
        "--SequentialMatching.loop_detection_period", "10",
        "--SequentialMatching.loop_detection_num_images", "50",
    ], stream=True)

    # 3) Mapper — loose thresholds for indoor 360° scenes
    _run([
        COLMAP_BIN, "mapper",
        "--database_path", db_path,
        "--image_path", images_dir,
        "--output_path", sparse_dir,
        "--Mapper.init_min_num_inliers", "8",
        "--Mapper.init_min_tri_angle", "2",
        "--Mapper.abs_pose_min_num_inliers", "8",
        "--Mapper.abs_pose_min_inlier_ratio", "0.05",
        "--Mapper.max_reg_trials", "10",
        "--Mapper.ba_global_max_num_iterations", "30",
        "--Mapper.min_num_matches", "8",
    ], stream=True)

    # Pick largest reconstruction
    model0     = os.path.join(sparse_dir, "0")
    best_model = model0
    best_count = 0
    for sub in os.listdir(sparse_dir):
        sub_path = os.path.join(sparse_dir, sub)
        if os.path.exists(os.path.join(sub_path, "cameras.bin")):
            try:
                r = pycolmap.Reconstruction(sub_path)
                n = r.num_reg_images()
                if n > best_count:
                    best_count = n
                    best_model = sub_path
            except Exception:
                pass

    if not os.path.exists(os.path.join(best_model, "cameras.bin")):
        raise RuntimeError(
            "COLMAP produced no reconstruction. "
            "Check that your panoramas were taken from different physical positions "
            "(not just rotated on the spot) and have enough scene overlap."
        )

    print(f"[colmap] Best model: {best_model} with {best_count} registered images", flush=True)

    # 4) Export sparse PLY
    ply_path = os.path.join(work_dir, "points.ply")
    _run([
        COLMAP_BIN, "model_converter",
        "--input_path", best_model,
        "--output_path", ply_path,
        "--output_type", "PLY",
    ])

    if best_model != model0:
        if os.path.exists(model0):
            shutil.rmtree(model0)
        shutil.copytree(best_model, model0)

    # 5) Dense reconstruction — skip for equirectangular (undistorter doesn't support it well)
    #    FastGS doesn't need it anyway
    dense_ply = None
    print("[colmap] Skipping dense reconstruction (not needed for FastGS)", flush=True)

    # 7) Copy resized panoramas into the images/ dir (sibling of sparse/)
    #    FastGS reads image filenames from COLMAP's images.bin — those names
    #    point to the resized panoramas, so they must exist in images/.
    fastgs_images_dir = os.path.join(work_dir, "images")
    os.makedirs(fastgs_images_dir, exist_ok=True)
    copied = 0
    for fname in os.listdir(images_dir):
        src = os.path.join(images_dir, fname)
        dst = os.path.join(fastgs_images_dir, fname)
        if not os.path.exists(dst):
            shutil.copy2(src, dst)
            copied += 1
    print(f"[colmap] Copied {copied} resized panoramas -> images/ for FastGS", flush=True)


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
        "points3D": recon.num_points3D(),
        "cameras": len(recon.cameras),
        "camera_positions": cameras,
        "ply_file": "points.ply",
        "model_path": model0,
        "dense_ply": None,
    }
    print(
        f"[colmap] {summary['registered_images']} images registered, "
        f"{summary['points3D']} sparse points",
        flush=True,
    )
    return summary