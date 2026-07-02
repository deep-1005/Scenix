import os
import re
import json
import time
import shutil
import subprocess
import sys
from app.workers.celery_app import celery
from app.models.db import SessionLocal, Job
from app.core.config import settings
from app.pipeline.cubemaps import generate_cubemaps
from app.pipeline.colmap_sfm import run_colmap
from celery.exceptions import SoftTimeLimitExceeded

FASTGS_DIR = os.path.expanduser("~/Desktop/360_image_processing/FastGS")
FASTGS_TRAIN = os.path.join(FASTGS_DIR, "train.py")
FASTGS_ITERATIONS = 30_000

CONDA_PYTHON = "/home/cave/miniconda3/envs/forensic/bin/python"

FASTGS_ENV = {
    **os.environ,
    "CUDA_HOME": "/home/cave/miniconda3/envs/forensic",
    "PATH": "/home/cave/miniconda3/envs/forensic/bin:" + os.environ.get("PATH", ""),
    "LD_LIBRARY_PATH": (
        "/home/cave/miniconda3/envs/forensic/lib/python3.11/site-packages/torch/lib:"
        + os.environ.get("LD_LIBRARY_PATH", "")
    ),
}

CLEANING_TIMEOUT_SECONDS = 600  # 10 minutes

STUB_STAGES = ["cleanup", "mesh", "detection", "classify", "measure", "report"]

# Order matters — used to decide what to skip on resume.
STAGE_ORDER = ["cubemaps", "colmap", "cleaning", "gaussian_splat"]


def _set(db, job, status=None, stage=None, progress=None, error=None, log_tail=None):
    if status is not None:   job.status = status
    if stage is not None:    job.stage = stage
    if progress is not None: job.progress = progress
    if error is not None:    job.error = error
    if log_tail is not None: job.log_tail = log_tail
    db.commit()


# ── Stage completion checks (used for resume validation) ──────────────────

def _cubemaps_done(images_dir: str) -> bool:
    if not os.path.isdir(images_dir):
        return False
    exts = (".jpg", ".jpeg", ".png")
    count = len([f for f in os.listdir(images_dir) if f.lower().endswith(exts)])
    return count > 0


def _colmap_done(scene_out: str) -> bool:
    sparse0 = os.path.join(scene_out, "sparse", "0")
    if not os.path.isdir(sparse0):
        return False
    for stem in ("cameras", "images", "points3D"):
        bin_path = os.path.join(sparse0, f"{stem}.bin")
        txt_path = os.path.join(sparse0, f"{stem}.txt")
        has_bin = os.path.exists(bin_path) and os.path.getsize(bin_path) > 50
        has_txt = os.path.exists(txt_path) and os.path.getsize(txt_path) > 50
        if not has_bin and not has_txt:
            return False
    # Specifically guard against the near-empty points3D.bin failure mode
    # we hit earlier — require a meaningfully sized points file.
    points_bin = os.path.join(sparse0, "points3D.bin")
    if os.path.exists(points_bin) and os.path.getsize(points_bin) < 200:
        return False
    return True


def _cleaning_done(cleaned_ply: str) -> bool:
    return os.path.exists(cleaned_ply) and os.path.getsize(cleaned_ply) > 200


def _gaussian_done(scene_out: str) -> bool:
    pc_dir = os.path.join(scene_out, "gaussian_output", "point_cloud")
    if not os.path.isdir(pc_dir):
        return False
    for entry in os.listdir(pc_dir):
        if entry.startswith("iteration_"):
            candidate = os.path.join(pc_dir, entry, "point_cloud.ply")
            if os.path.exists(candidate) and os.path.getsize(candidate) > 200:
                return True
    return False


def _validate_colmap_output(scene_out: str):
    sparse0 = os.path.join(scene_out, "sparse", "0")
    images  = os.path.join(scene_out, "images")

    if not os.path.isdir(images):
        raise RuntimeError(f"FastGS needs an images/ folder at: {images}")

    img_count = len([
        f for f in os.listdir(images)
        if f.lower().endswith((".jpg", ".jpeg", ".png"))
    ])
    if img_count == 0:
        raise RuntimeError(
            f"images/ folder at {images} is EMPTY — FastGS has nothing to "
            f"train on. This means the COLMAP stage's copy step failed."
        )

    if not os.path.isdir(sparse0):
        raise RuntimeError(
            f"FastGS needs sparse/0/ at: {sparse0}\n"
            "COLMAP mapper may not have produced a reconstruction."
        )

    for stem in ("cameras", "images", "points3D"):
        has_bin = os.path.exists(os.path.join(sparse0, f"{stem}.bin"))
        has_txt = os.path.exists(os.path.join(sparse0, f"{stem}.txt"))
        if not has_bin and not has_txt:
            raise RuntimeError(
                f"Missing {stem}.bin/.txt in {sparse0}. "
                "COLMAP reconstruction may be incomplete."
            )

    points_bin = os.path.join(sparse0, "points3D.bin")
    if os.path.exists(points_bin) and os.path.getsize(points_bin) < 200:
        raise RuntimeError(
            f"COLMAP produced an essentially empty points3D.bin "
            f"({os.path.getsize(points_bin)} bytes) — the reconstruction "
            f"failed to triangulate points. Try exhaustive_matcher or check "
            f"image overlap/quality."
        )

    sparse0_files = os.listdir(sparse0)
    print(
        f"[FastGS] Validated scene: {img_count} images, "
        f"sparse/0/ has: {sparse0_files}"
    )


def _run_cleaning_subprocess(db, job, sparse_ply: str, cleaned_ply: str, scene_out: str) -> dict:
    runner_cmd = [
        sys.executable, "-m", "app.pipeline.clean_pointcloud_runner",
        "--input", sparse_ply,
        "--output", cleaned_ply,
        "--job-dir", scene_out,
    ]
    print(f"[cleaning] Launching isolated subprocess: {' '.join(runner_cmd)}", flush=True)

    try:
        result = subprocess.run(
            runner_cmd,
            capture_output=True,
            text=True,
            timeout=CLEANING_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"Point cloud cleaning timed out after {CLEANING_TIMEOUT_SECONDS}s. "
            f"The scene may be too large, or Open3D may be hanging on this GPU."
        )

    if result.stdout:
        print(result.stdout, flush=True)
    if result.stderr:
        print(result.stderr, flush=True)

    if result.returncode != 0:
        raise RuntimeError(
            f"Cleaning subprocess exited with code {result.returncode} "
            f"(likely crashed or was OOM-killed by the OS). "
            f"Last output: {(result.stdout or result.stderr)[-500:]}"
        )

    try:
        last_line = [l for l in result.stdout.strip().splitlines() if l.strip()][-1]
        stats = json.loads(last_line)
    except Exception as e:
        raise RuntimeError(
            f"Cleaning subprocess finished but its output stats could not be "
            f"parsed: {e}. Raw stdout tail: {result.stdout[-500:]}"
        )

    return stats


def _run_fastgs(db, job, scene_out: str):
    _validate_colmap_output(scene_out)

    model_path = os.path.join(scene_out, "gaussian_output")
    os.makedirs(model_path, exist_ok=True)

    cmd = [
        CONDA_PYTHON, FASTGS_TRAIN,
        "-s", scene_out,
        "--model_path", model_path,
        "--iterations", str(FASTGS_ITERATIONS),
        "--save_iterations", str(FASTGS_ITERATIONS),
        "--checkpoint_iterations", str(FASTGS_ITERATIONS),
        "-r", "2",
    ]
    print(f"[FastGS] Launching: {' '.join(cmd)}")
    print(f"[FastGS] cwd={FASTGS_DIR}, scene={scene_out}")

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=FASTGS_DIR,
        env=FASTGS_ENV,
    )

    last_progress = 65
    last_line = ""
    for line in process.stdout:
        line = line.strip()
        if not line:
            continue
        last_line = line
        print(f"[FastGS] {line}")

        iteration = None
        m = re.search(r'\[ITER[ATION]*\s+(\d+)\]', line, re.IGNORECASE)
        if m:
            iteration = int(m.group(1))
        else:
            m = re.search(r'iteration\s+(\d+)', line, re.IGNORECASE)
            if m:
                iteration = int(m.group(1))

        if iteration is not None:
            pct = 65 + int((iteration / FASTGS_ITERATIONS) * 20)
            if pct != last_progress:
                last_progress = pct
                _set(db, job, progress=pct, log_tail=line[:200])
        else:
            _set(db, job, log_tail=line[:200])

    process.wait()
    if process.returncode != 0:
        raise RuntimeError(
            f"FastGS exited with code {process.returncode}. "
            f"Last output: {last_line[:300]}"
        )
    print("[FastGS] Training complete.")


def _export_colmap_ply(scene_out: str) -> str:
    sparse0  = os.path.join(scene_out, "sparse", "0")
    ply_path = os.path.join(sparse0, "points3D.ply")

    if os.path.exists(ply_path):
        return ply_path

    print("[cleaning] No PLY found — running colmap model_converter...")
    subprocess.run([
        "colmap", "model_converter",
        "--input_path",  sparse0,
        "--output_path", ply_path,
        "--output_type", "PLY",
    ], check=True)

    if not os.path.exists(ply_path):
        raise RuntimeError(f"model_converter ran but PLY not found at {ply_path}")

    print(f"[cleaning] Exported PLY: {ply_path}")
    return ply_path


@celery.task(bind=True)
def run_pipeline(self, job_id: str, resume: bool = False):
    db = SessionLocal()
    job = db.query(Job).get(job_id)
    try:
        scene_out  = os.path.abspath(os.path.join(settings.storage_outputs, job_id))
        images_dir = os.path.join(scene_out, "images")
        cleaned_ply = os.path.join(scene_out, "sparse", "0", "points3D_cleaned.ply")

        if resume:
            print(f"[pipeline] RESUME requested for job {job_id}, last stage was '{job.stage}'")
            _set(db, job, status="running", error=None)
            if not os.path.isdir(scene_out):
                raise RuntimeError(
                    "Cannot resume — output directory no longer exists. "
                    "Start a fresh reconstruction instead."
                )
        else:
            _set(db, job, status="running", progress=0)
            if os.path.exists(scene_out):
                print(f"[pipeline] Removing previous output dir: {scene_out}")
                shutil.rmtree(scene_out)
            os.makedirs(scene_out, exist_ok=True)

        # ---- Stage 2: Cubemaps ----
        skip_cubemaps = resume and _cubemaps_done(images_dir)
        if skip_cubemaps:
            print("[pipeline] RESUME: cubemaps already present — skipping")
        else:
            _set(db, job, stage="cubemaps", progress=5)
            cube_summary = generate_cubemaps(job.upload_path, images_dir)
            print(f"[cubemaps] {cube_summary}")
            _set(db, job, progress=20)

        # ---- Stage 3: COLMAP ----
        skip_colmap = resume and _colmap_done(scene_out)
        if skip_colmap:
            print("[pipeline] RESUME: COLMAP output already valid — skipping")
        else:
            _set(db, job, stage="colmap", progress=25)
            colmap_summary = run_colmap(images_dir, scene_out, use_gpu=True)
            job.summary = json.dumps({"colmap": colmap_summary})
            _set(db, job, progress=50)

        # ---- Stage 4: Point Cloud Cleaning ----
        sparse_ply = os.path.join(scene_out, "sparse", "0", "points3D.ply")

        skip_cleaning = resume and _cleaning_done(cleaned_ply)
        if skip_cleaning:
            print("[pipeline] RESUME: cleaned point cloud already present — skipping")
            _set(db, job, stage="cleaning", progress=63)
        else:
            _set(db, job, stage="cleaning", progress=52,
                 log_tail="Starting point cloud cleaning...")

            if not os.path.exists(sparse_ply):
                sparse_ply = _export_colmap_ply(scene_out)

            try:
                cleaning_stats = _run_cleaning_subprocess(db, job, sparse_ply, cleaned_ply, scene_out)
                print(
                    f"[cleaning] Done — {cleaning_stats['structure_kept']}% structure kept, "
                    f"{cleaning_stats['final_points']:,} points remaining"
                )
                summary = json.loads(job.summary or "{}")
                summary["cleaning"] = cleaning_stats
                job.summary = json.dumps(summary)
                _set(db, job, progress=63,
                     log_tail=f"Cleaned: {cleaning_stats['structure_kept']}% kept")
            except Exception as clean_err:
                print(f"[cleaning] WARNING: cleaning failed ({clean_err}) — using raw PLY")
                cleaned_ply = sparse_ply
                _set(db, job, progress=63,
                     log_tail=f"Cleaning failed, using raw point cloud: {str(clean_err)[:150]}")

        # ---- Stage 5: Gaussian Splatting ----
        skip_gaussian = resume and _gaussian_done(scene_out)
        if skip_gaussian:
            print("[pipeline] RESUME: Gaussian splat output already present — skipping")
            _set(db, job, stage="gaussian_splat", progress=85,
                 log_tail="FastGS training complete (already done).")
        else:
            _set(db, job, stage="gaussian_splat", progress=65,
                 log_tail="Starting FastGS training...")
            _run_fastgs(db, job, scene_out)
            _set(db, job, stage="gaussian_splat", progress=85,
                 log_tail="FastGS training complete.")

        # ---- Remaining stages stubbed ----
        for i, stage in enumerate(STUB_STAGES):
            _set(db, job, stage=stage,
                 progress=85 + int((i / len(STUB_STAGES)) * 15))
            time.sleep(1)

        job.output_path = scene_out
        _set(db, job, status="done", stage="complete", progress=100)

    except SoftTimeLimitExceeded:
        _set(db, job, status="failed", error="Pipeline exceeded time limit (stuck or hung)")
        raise
    except Exception as e:
        _set(db, job, status="failed", error=str(e))
        raise
    finally:
        db.close()