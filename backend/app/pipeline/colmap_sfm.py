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
            print(f"[colmap] WARNING: cv2 could not read {fname}, skipping", flush=True)
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
    Run COLMAP on perspective views generated from 360 panoramas.

    Pipeline:
      1. Feature extraction with SIMPLE_RADIAL (per-image cameras, radial
         distortion — better reconstruction quality than SIMPLE_PINHOLE)
      2. Exhaustive matching (correct for non-sequential panoramic datasets)
      3. Mapper (produces distorted sparse model)
      4. image_undistorter (converts SIMPLE_RADIAL -> PINHOLE, produces
         undistorted images) — this is what FastGS actually needs, since
         FastGS only supports PINHOLE / SIMPLE_PINHOLE camera models.
         Without this step, FastGS crashes with:
           "Colmap camera model not handled: only undistorted datasets supported"
      5. Replace sparse/0 and images/ with the undistorted versions so
         the rest of the pipeline (cleaning, FastGS) works unchanged.
    """
    os.makedirs(work_dir, exist_ok=True)

    # Step 0: Resize images
    resized_dir = os.path.join(work_dir, "colmap_images_resized")
    print(f"[colmap] Resizing images to max width {MAX_COLMAP_WIDTH}px...", flush=True)
    images_dir = _resize_images(images_dir, resized_dir, MAX_COLMAP_WIDTH)

    resized_count = len([
        f for f in os.listdir(images_dir)
        if f.lower().endswith((".jpg", ".jpeg", ".png"))
    ])
    print(f"[colmap] {resized_count} images ready in {images_dir}", flush=True)
    if resized_count == 0:
        raise RuntimeError(
            f"No images survived resizing in {images_dir} — check that "
            f"the cubemaps stage actually wrote files to its images dir."
        )

    db_path    = os.path.join(work_dir, "database.db")
    sparse_dir = os.path.join(work_dir, "sparse")
    os.makedirs(sparse_dir, exist_ok=True)

    gpu_flag = "1" if use_gpu else "0"

    # 1) Feature extraction — SIMPLE_RADIAL per image for best reconstruction.
    #    FastGS doesn't support SIMPLE_RADIAL directly, but we undistort
    #    in step 4 to convert everything to PINHOLE before handing off.
    _run([
        COLMAP_BIN, "feature_extractor",
        "--database_path", db_path,
        "--image_path", images_dir,
        "--ImageReader.single_camera", "0",
        "--ImageReader.camera_model", "SIMPLE_RADIAL",
        "--FeatureExtraction.use_gpu", gpu_flag,
        "--FeatureExtraction.gpu_index", "-1",
        "--FeatureExtraction.num_threads", "-1",
        "--SiftExtraction.max_num_features", "16384",
        "--SiftExtraction.peak_threshold", "0.0067",
        "--SiftExtraction.max_image_size", "3200",
    ], stream=True)

    # 2) Exhaustive matching
    # NOTE: flag renamed from --SiftMatching.use_gpu to --FeatureMatching.use_gpu
    # in newer COLMAP versions.
    _run([
        COLMAP_BIN, "exhaustive_matcher",
        "--database_path", db_path,
        "--FeatureMatching.use_gpu", gpu_flag,
        "--FeatureMatching.gpu_index", "-1",
    ], stream=True)

    # 3) Mapper
    _run([
        COLMAP_BIN, "mapper",
        "--database_path", db_path,
        "--image_path", images_dir,
        "--output_path", sparse_dir,
        "--Mapper.init_min_num_inliers", "100",
        "--Mapper.init_min_tri_angle", "4",
        "--Mapper.abs_pose_min_num_inliers", "30",
        "--Mapper.abs_pose_min_inlier_ratio", "0.25",
        "--Mapper.max_reg_trials", "5",
        "--Mapper.ba_global_max_num_iterations", "50",
        "--Mapper.min_num_matches", "15",
        "--Mapper.multiple_models", "1",
    ], stream=True)

    # Pick largest reconstruction
    model0     = os.path.join(sparse_dir, "0")
    best_model = model0
    best_count = 0
    all_models_found = []
    for sub in sorted(os.listdir(sparse_dir)):
        sub_path = os.path.join(sparse_dir, sub)
        if os.path.exists(os.path.join(sub_path, "cameras.bin")):
            try:
                r = pycolmap.Reconstruction(sub_path)
                n = r.num_reg_images()
                all_models_found.append((sub, n))
                if n > best_count:
                    best_count = n
                    best_model = sub_path
            except Exception:
                pass

    if len(all_models_found) > 1:
        print(
            f"[colmap] WARNING: mapper produced {len(all_models_found)} separate "
            f"reconstructions instead of one connected model: {all_models_found}. "
            f"Using the largest one ({best_count} images).",
            flush=True,
        )

    if not os.path.exists(os.path.join(best_model, "cameras.bin")):
        raise RuntimeError(
            "COLMAP produced no reconstruction. "
            "Check that your panoramas were taken from different physical positions "
            "(not just rotated on the spot) and have enough scene overlap."
        )

    print(f"[colmap] Best model: {best_model} with {best_count} registered images", flush=True)

    # If best model isn't model0, move it there so undistorter always reads from sparse/0
    if best_model != model0:
        if os.path.exists(model0):
            shutil.rmtree(model0)
        shutil.copytree(best_model, model0)
        best_model = model0

    # 4) UNDISTORT — THE PERMANENT FIX FOR FastGS CAMERA MODEL ERROR
    #
    #    FastGS crashes on SIMPLE_RADIAL with:
    #      "Colmap camera model not handled: only undistorted datasets
    #       (PINHOLE or SIMPLE_PINHOLE cameras) supported!"
    #
    #    colmap image_undistorter:
    #      - reads the distorted sparse/0 + original images
    #      - produces undistorted images in dense/images/
    #      - produces a new sparse model in dense/sparse/ with PINHOLE cameras
    #    We then replace sparse/0 and images/ with the undistorted versions
    #    so the rest of the pipeline is unaffected.
    dense_dir = os.path.join(work_dir, "dense")
    os.makedirs(dense_dir, exist_ok=True)

    print("[colmap] Running image_undistorter to convert SIMPLE_RADIAL -> PINHOLE for FastGS...", flush=True)
    _run([
        COLMAP_BIN, "image_undistorter",
        "--image_path", images_dir,
        "--input_path", model0,
        "--output_path", dense_dir,
        "--output_type", "COLMAP",
        "--max_image_size", "3200",
    ], stream=True)

    # dense/sparse/ contains the undistorted PINHOLE model
    # dense/images/ contains the undistorted images
    dense_sparse = os.path.join(dense_dir, "sparse")
    dense_images = os.path.join(dense_dir, "images")

    if not os.path.isdir(dense_sparse) or not os.path.isdir(dense_images):
        raise RuntimeError(
            f"image_undistorter did not produce expected output at {dense_dir}. "
            f"Contents: {os.listdir(dense_dir) if os.path.isdir(dense_dir) else 'directory missing'}"
        )

    undist_img_count = len([
        f for f in os.listdir(dense_images)
        if f.lower().endswith((".jpg", ".jpeg", ".png"))
    ])
    print(f"[colmap] Undistortion complete: {undist_img_count} undistorted images", flush=True)

    # Replace sparse/0 with the undistorted PINHOLE model
    if os.path.exists(model0):
        shutil.rmtree(model0)
    shutil.copytree(dense_sparse, model0)
    print(f"[colmap] Replaced sparse/0 with undistorted PINHOLE model", flush=True)

    # 5) Export sparse PLY from the undistorted model
    ply_path = os.path.join(work_dir, "points.ply")
    _run([
        COLMAP_BIN, "model_converter",
        "--input_path", model0,
        "--output_path", ply_path,
        "--output_type", "PLY",
    ])

    print("[colmap] Skipping dense reconstruction (not needed for FastGS)", flush=True)

    # 6) Set up images/ for FastGS using the UNDISTORTED images.
    #    FastGS must use the same images that match the undistorted camera model —
    #    using the original distorted images with an undistorted camera model
    #    would produce a broken splat.
    fastgs_images_dir = os.path.join(work_dir, "images")

    # If images/ exists from a previous run or earlier step, clear it
    # so we don't mix distorted and undistorted images.
    if os.path.exists(fastgs_images_dir):
        shutil.rmtree(fastgs_images_dir)
    shutil.copytree(dense_images, fastgs_images_dir)

    final_count = len([
        f for f in os.listdir(fastgs_images_dir)
        if f.lower().endswith((".jpg", ".jpeg", ".png"))
    ])
    print(
        f"[colmap] Copied {final_count} undistorted images -> images/",
        flush=True,
    )
    if final_count == 0:
        raise RuntimeError(
            f"images/ folder is empty after undistortion copy ({fastgs_images_dir}). "
            f"Undistortion may have produced no output images."
        )

    # Read final stats from the undistorted model
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
        "total_input_images": resized_count,
        "points3D": recon.num_points3D(),
        "cameras": len(recon.cameras),
        "camera_positions": cameras,
        "ply_file": "points.ply",
        "model_path": model0,
        "dense_ply": None,
        "fragmented_models": len(all_models_found) if len(all_models_found) > 1 else None,
    }
    print(
        f"[colmap] {summary['registered_images']}/{summary['total_input_images']} "
        f"images registered, {summary['points3D']} sparse points",
        flush=True,
    )
    return summary