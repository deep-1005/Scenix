import os
import shutil
import cv2
import numpy as np
from PIL import Image
import py360convert

# Perspective projection settings — 15 views per panorama (5 yaw × 3 pitch)
# Much better COLMAP overlap than 4 cubemap faces
FOV        = 90
IMG_WIDTH  = 1400
IMG_HEIGHT = 1400
YAW_ANGLES   = [0, 72, 144, 216, 288]       # every 72° around the panorama
PITCH_ANGLES = [-20, 0, 20]                  # slight down, level, slight up

# Max panoramas to process — set high, let COLMAP handle the full set
MAX_PANORAMAS = 100


def is_equirectangular(img) -> bool:
    h, w = img.shape[:2]
    return 1.8 <= (w / h) <= 2.2


def _subsample(images: list, target: int) -> list:
    if len(images) <= target:
        return images
    step = len(images) / target
    return [images[int(i * step)] for i in range(target)]


def generate_cubemaps(input_dir: str, output_dir: str, face_size: int = 1400) -> dict:
    """
    Converts 360° equirectangular panoramas into perspective views using e2p.
    15 views per panorama (5 yaw × 3 pitch) at 90° FOV, 1400×1400px.
    These perspective views are used by BOTH COLMAP and FastGS.

    Also copies original panoramas to colmap_images/ (kept for reference).
    """
    os.makedirs(output_dir, exist_ok=True)

    # Keep colmap_images/ for reference (not used by pipeline anymore)
    colmap_images_dir = os.path.join(os.path.dirname(output_dir), "colmap_images")
    os.makedirs(colmap_images_dir, exist_ok=True)

    exts = (".jpg", ".jpeg", ".png")
    all_images = sorted(f for f in os.listdir(input_dir) if f.lower().endswith(exts))
    if not all_images:
        raise RuntimeError(f"No images found in {input_dir}")

    # Separate panoramas from flat images
    panorama_files = []
    flat_files = []
    for fname in all_images:
        path = os.path.join(input_dir, fname)
        img = cv2.imread(path)
        if img is None:
            continue
        if is_equirectangular(img):
            panorama_files.append(fname)
        else:
            flat_files.append(fname)

    original_count = len(panorama_files)

    # Copy originals to colmap_images/ for reference
    for fname in panorama_files + flat_files:
        shutil.copy2(
            os.path.join(input_dir, fname),
            os.path.join(colmap_images_dir, fname),
        )
    print(
        f"[cubemaps] Copied {len(panorama_files)} panoramas + {len(flat_files)} flat "
        f"to colmap_images/ (reference only)",
        flush=True,
    )

    # Subsample if too many panoramas
    panorama_files_gs = _subsample(panorama_files, MAX_PANORAMAS)
    if original_count > MAX_PANORAMAS:
        print(
            f"[cubemaps] Subsampled {original_count} -> {len(panorama_files_gs)} panoramas",
            flush=True,
        )

    views_written = 0
    passthrough   = 0
    face_files    = []

    for fname in panorama_files_gs:
        path = os.path.join(input_dir, fname)
        print(f"[cubemaps] Processing {fname}", flush=True)

        pano = np.array(Image.open(path).convert("RGB"))
        pano_base = os.path.splitext(fname)[0]

        for pitch in PITCH_ANGLES:
            for yaw in YAW_ANGLES:
                persp = py360convert.e2p(
                    pano,
                    fov_deg=FOV,
                    u_deg=yaw,
                    v_deg=pitch,
                    out_hw=(IMG_HEIGHT, IMG_WIDTH),
                )
                out_name = f"{pano_base}_yaw{yaw}_pitch{pitch}.jpg"
                out_path = os.path.join(output_dir, out_name)
                cv2.imwrite(
                    out_path,
                    cv2.cvtColor(persp, cv2.COLOR_RGB2BGR),
                    [cv2.IMWRITE_JPEG_QUALITY, 95],
                )
                views_written += 1
                face_files.append(out_name)

    # Pass through any flat (non-360) images unchanged
    for fname in flat_files:
        shutil.copy2(
            os.path.join(input_dir, fname),
            os.path.join(output_dir, fname),
        )
        passthrough += 1
        face_files.append(fname)

    if views_written == 0 and passthrough == 0:
        raise RuntimeError("No usable images after perspective projection stage")

    total = views_written + passthrough
    views_per_pano = len(YAW_ANGLES) * len(PITCH_ANGLES)
    print(
        f"[cubemaps] {len(panorama_files_gs)} panos × {views_per_pano} views "
        f"= {views_written} + {passthrough} flat = {total} total perspective images",
        flush=True,
    )

    return {
        "input_images":        len(all_images),
        "panoramas_original":  original_count,
        "panoramas_used_for_gs": len(panorama_files_gs),
        "views_per_panorama":  views_per_pano,
        "views_written":       views_written,
        "passthrough":         passthrough,
        "total_output":        total,
        "files":               face_files,
        "colmap_images_dir":   colmap_images_dir,
    }