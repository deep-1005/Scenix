import os
import shutil
import cv2
import numpy as np
from PIL import Image
import py360convert

# ── [FORENSIC FIX] ──────────────────────────────────────────────────────
# OpenCV spins up its own internal thread pool on import. Celery's default
# "prefork" worker pool uses os.fork() to create child processes — if cv2
# has already initialized threads before the fork happens, the forked
# child can end up with a broken/inconsistent thread state, surfacing as
# intermittent "[Errno 32] Broken pipe" errors. Disabling OpenCV's internal
# threading is the standard fix for the cv2 + fork() conflict.
cv2.setNumThreads(0)

# ── [FORENSIC FIX] Broader format support ───────────────────────────────
# pillow-heif registers a HEIC/HEIF decoder with Pillow so Image.open() can
# read iPhone-native photos like any other format. Without it, HEIC files
# are still accepted by the extension filter below but will fail to open —
# tracked in `unreadable`, not silently dropped.
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    _HEIF_SUPPORTED = True
except ImportError:
    _HEIF_SUPPORTED = False
    print(
        "[cubemaps] WARNING: pillow-heif not installed — .heic/.heif files "
        "will fail to decode. Run: pip install pillow-heif --break-system-packages",
        flush=True,
    )

SUPPORTED_EXTS = (
    ".jpg", ".jpeg", ".png",
    ".webp", ".bmp", ".tif", ".tiff",
    ".heic", ".heif",
)

# Perspective projection settings — 15 views per panorama (5 yaw × 3 pitch)
# Much better COLMAP overlap than 4 cubemap faces
FOV        = 90
IMG_WIDTH  = 1400
IMG_HEIGHT = 1400
YAW_ANGLES   = [0, 72, 144, 216, 288]       # every 72° around the panorama
PITCH_ANGLES = [-20, 0, 20]                  # slight down, level, slight up

# Max panoramas to process — set high, let COLMAP handle the full set
MAX_PANORAMAS = 100

# [FORENSIC FIX] Safety cap on the RAW panorama width before we even decode
# it into a numpy array for e2p(). Some phone/360-camera exports come out
# at 8000-12000px wide; decoding + holding several of those in memory at
# once is a common OOM trigger. Does NOT touch the final crop resolution
# (still IMG_WIDTH x IMG_HEIGHT) — just caps the source panorama.
MAX_PANO_WIDTH = 6000


def _subsample(images: list, target: int) -> list:
    if len(images) <= target:
        return images
    step = len(images) / target
    return [images[int(i * step)] for i in range(target)]


def _probe_image(path: str):
    """
    [FORENSIC FIX] Replaces the old cv2.imread() probe.

    cv2.imread() returning None on failure gives ZERO information about
    WHY a file couldn't be decoded — it just silently disappears from the
    count. PIL (with pillow-heif registered) is more tolerant of real-world
    format quirks AND, critically, raises a real exception with a real
    message when a file actually is bad — instead of a bare None. im.load()
    forces full pixel decode (not just header parsing) so truncated/corrupt
    files raise HERE, with a clear reason, rather than failing mysteriously
    later in e2p().

    Returns (width, height).
    """
    with Image.open(path) as im:
        im.load()
        return im.size


def is_equirectangular_ratio(w: int, h: int) -> bool:
    if h == 0:
        return False
    ratio = w / h
    return 1.8 <= ratio <= 2.2


def _load_panorama_as_array(path: str) -> np.ndarray:
    """
    Load a panorama and downscale it if it's absurdly large, BEFORE handing
    it to py360convert.e2p(). Keeps memory bounded regardless of what the
    user uploads.
    """
    with Image.open(path) as im:
        im = im.convert("RGB")
        w, h = im.size
        if w > MAX_PANO_WIDTH:
            scale = MAX_PANO_WIDTH / w
            new_size = (MAX_PANO_WIDTH, int(h * scale))
            print(
                f"[cubemaps] {os.path.basename(path)} is {w}x{h}, "
                f"downscaling to {new_size[0]}x{new_size[1]} before e2p()",
                flush=True,
            )
            im = im.resize(new_size, Image.LANCZOS)
        return np.array(im)


def generate_cubemaps(input_dir: str, output_dir: str, face_size: int = 1400) -> dict:
    """
    Converts 360° equirectangular panoramas into perspective views using e2p.
    15 views per panorama (5 yaw × 3 pitch) at 90° FOV, 1400×1400px.

    ALSO accepts already-done perspective photos (regular flat images, any
    resolution) and passes them through as "flat" images — both input types
    are supported in the same upload.

    [FORENSIC FIX] Returns "all_synthetic": True only when every output
    image is a synthetic e2p() crop with KNOWN intrinsics (FOV=90,
    1400x1400). If the upload included ANY real/flat photos, this is False
    — colmap_sfm.py uses this flag to decide whether it's safe to lock in
    the fixed synthetic PINHOLE intrinsics (only valid when 100% of images
    share the same known camera model) or whether it must fall back to
    COLMAP's normal per-image intrinsics estimation, which is the only
    correct approach for real camera photos of unknown/varying FOV.
    Previously flat/real photos were silently forced through the same
    fixed-intrinsics fast path as panorama crops, which is simply wrong for
    them and caused those images to fail registration.
    """
    os.makedirs(output_dir, exist_ok=True)

    # Keep colmap_images/ for reference (not used by pipeline anymore)
    colmap_images_dir = os.path.join(os.path.dirname(output_dir), "colmap_images")
    os.makedirs(colmap_images_dir, exist_ok=True)

    all_images = sorted(f for f in os.listdir(input_dir) if f.lower().endswith(SUPPORTED_EXTS))
    if not all_images:
        raise RuntimeError(
            f"No images found in {input_dir} (looked for: {', '.join(SUPPORTED_EXTS)})"
        )

    # Separate panoramas from flat images
    panorama_files = []
    flat_files = []
    unreadable = []  # tracked with a real reason, not just silently dropped

    for fname in all_images:
        path = os.path.join(input_dir, fname)
        try:
            w, h = _probe_image(path)
        except Exception as e:
            reason = f"{type(e).__name__}: {e}"
            print(f"[cubemaps] WARNING: could not read {fname}, skipping — {reason}", flush=True)
            unreadable.append({"file": fname, "reason": reason})
            continue

        if is_equirectangular_ratio(w, h):
            panorama_files.append(fname)
        else:
            flat_files.append(fname)
            print(
                f"[cubemaps] {fname} is {w}x{h} (ratio {w/h:.2f}) — not "
                f"equirectangular (need 1.8-2.2), treating as a flat/"
                f"already-perspective photo (passthrough)",
                flush=True,
            )

    original_count = len(panorama_files)

    if original_count == 0 and not flat_files:
        raise RuntimeError(
            f"No readable images found in {input_dir} — all {len(all_images)} "
            f"file(s) failed to decode. First failure reason: "
            f"{unreadable[0]['reason'] if unreadable else 'unknown'}"
        )

    # Copy originals to colmap_images/ for reference
    for fname in panorama_files + flat_files:
        try:
            shutil.copy2(
                os.path.join(input_dir, fname),
                os.path.join(colmap_images_dir, fname),
            )
        except OSError as e:
            print(f"[cubemaps] WARNING: failed to copy {fname} to colmap_images/: {e}", flush=True)

    print(
        f"[cubemaps] Copied {len(panorama_files)} panoramas + {len(flat_files)} flat "
        f"to colmap_images/ (reference only)",
        flush=True,
    )
    if unreadable:
        print(
            f"[cubemaps] {len(unreadable)}/{len(all_images)} uploaded file(s) "
            f"could not be decoded: {unreadable}",
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
    failed_panoramas = []

    for fname in panorama_files_gs:
        path = os.path.join(input_dir, fname)
        print(f"[cubemaps] Processing {fname}", flush=True)

        try:
            pano = _load_panorama_as_array(path)
        except Exception as e:
            print(f"[cubemaps] WARNING: failed to load {fname}, skipping: {e}", flush=True)
            failed_panoramas.append(fname)
            continue

        pano_base = os.path.splitext(fname)[0]

        for pitch in PITCH_ANGLES:
            for yaw in YAW_ANGLES:
                try:
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
                except Exception as e:
                    print(
                        f"[cubemaps] WARNING: failed to render yaw={yaw} pitch={pitch} "
                        f"for {fname}, skipping this view: {e}",
                        flush=True,
                    )

    # Pass through any flat (already-perspective / real-photo) images.
    # Normalize non-jpg/png formats to jpg so downstream stages (which
    # filter on .jpg/.jpeg/.png) always see them, regardless of upload format.
    for fname in flat_files:
        src_path = os.path.join(input_dir, fname)
        ext = os.path.splitext(fname)[1].lower()
        base = os.path.splitext(fname)[0]
        try:
            if ext in (".jpg", ".jpeg", ".png"):
                shutil.copy2(src_path, os.path.join(output_dir, fname))
                passthrough += 1
                face_files.append(fname)
            else:
                out_name = f"{base}.jpg"
                with Image.open(src_path) as im:
                    im.convert("RGB").save(os.path.join(output_dir, out_name), "JPEG", quality=95)
                passthrough += 1
                face_files.append(out_name)
        except OSError as e:
            print(f"[cubemaps] WARNING: failed to pass through {fname}: {e}", flush=True)

    if views_written == 0 and passthrough == 0:
        raise RuntimeError(
            "No usable images after perspective projection stage "
            f"(panoramas found: {original_count}, failed to load: {len(failed_panoramas)})"
        )

    total = views_written + passthrough
    views_per_pano = len(YAW_ANGLES) * len(PITCH_ANGLES)
    print(
        f"[cubemaps] {len(panorama_files_gs)} panos x {views_per_pano} views "
        f"= {views_written} + {passthrough} flat = {total} total perspective images",
        flush=True,
    )
    if failed_panoramas:
        print(f"[cubemaps] {len(failed_panoramas)} panorama(s) failed to load and were skipped: {failed_panoramas}", flush=True)

    # [FORENSIC FIX] True only if EVERY output image is a synthetic e2p()
    # crop with known FOV=90 / 1400x1400 intrinsics. If any real/flat photo
    # made it into the output set, colmap_sfm.py must NOT use the locked
    # fixed-intrinsics fast path for this job.
    all_synthetic = (passthrough == 0 and views_written > 0)

    return {
        "input_images":        len(all_images),
        "unreadable_files":    unreadable,
        "panoramas_original":  original_count,
        "panoramas_used_for_gs": len(panorama_files_gs),
        "views_per_panorama":  views_per_pano,
        "views_written":       views_written,
        "passthrough":         passthrough,
        "total_output":        total,
        "failed_panoramas":    failed_panoramas,
        "all_synthetic":       all_synthetic,
        "files":               face_files,
        "colmap_images_dir":   colmap_images_dir,
    }