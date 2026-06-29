import os
import re
import json
import time
import shutil
import subprocess
from app.workers.celery_app import celery
from app.models.db import SessionLocal, Job
from app.core.config import settings
from app.pipeline.cubemaps import generate_cubemaps
from app.pipeline.colmap_sfm import run_colmap

FASTGS_DIR = os.path.expanduser("~/Desktop/360_image_processing/FastGS")
FASTGS_TRAIN = os.path.join(FASTGS_DIR, "train.py")
FASTGS_ITERATIONS = 30_000
FASTGS_MIN_POINTS = 100          # lowered — cubemap faces give fewer points per image

CONDA_PYTHON = "/home/cave/miniconda3/envs/forensic/bin/python"

FASTGS_ENV = {
    **os.environ,
    "CUDA_HOME": "/home/cave/miniconda3/envs/forensic",
    "PATH": "/home/cave/miniconda3/envs/forensic/bin:" + os.environ.get("PATH", ""),
    "LD_LIBRARY_PATH": (
        "/home/cave/miniconda3/envs/forensic/lib/python3.11/site-packages/torch/lib:"
        + os.environ.get("LD_LIBRARY_PATH", "")
    ),
    "CUDA_LAUNCH_BLOCKING": "1",
}

STUB_STAGES = ["cleanup", "mesh", "detection", "classify", "measure", "report"]


def _set(db, job, status=None, stage=None, progress=None, error=None, log_tail=None):
    if status is not None:   job.status = status
    if stage is not None:    job.stage = stage
    if progress is not None: job.progress = progress
    if error is not None:    job.error = error
    if log_tail is not None: job.log_tail = log_tail
    db.commit()


def _validate_colmap_output(scene_out: str, min_points: int = FASTGS_MIN_POINTS):
    sparse0 = os.path.join(scene_out, "sparse", "0")
    images  = os.path.join(scene_out, "images")

    if not os.path.isdir(images):
        raise RuntimeError(f"FastGS needs an images/ folder at: {images}")
    if not os.path.isdir(sparse0):
        raise RuntimeError(f"FastGS needs sparse/0/ at: {sparse0}")

    for stem in ("cameras", "images", "points3D"):
        has_bin = os.path.exists(os.path.join(sparse0, f"{stem}.bin"))
        has_txt = os.path.exists(os.path.join(sparse0, f"{stem}.txt"))
        if not has_bin and not has_txt:
            raise RuntimeError(f"Missing {stem}.bin/.txt in {sparse0}.")

    try:
        import pycolmap
        recon = pycolmap.Reconstruction(sparse0)
        n_pts = recon.num_points3D()
        print(f"[FastGS] Sparse point count: {n_pts}", flush=True)
        if n_pts < min_points:
            raise RuntimeError(
                f"Only {n_pts} 3D points — need at least {min_points} for FastGS. "
                "COLMAP registration was too sparse."
            )
    except ImportError:
        pass


def _find_splat_ply(model_path: str):
    pc_dir = os.path.join(model_path, "point_cloud")
    if not os.path.isdir(pc_dir):
        return None
    best_iter, best_path = -1, None
    for entry in os.listdir(pc_dir):
        if entry.startswith("iteration_"):
            try:
                n = int(entry.split("_")[1])
            except ValueError:
                continue
            candidate = os.path.join(pc_dir, entry, "point_cloud.ply")
            if os.path.exists(candidate) and n > best_iter:
                best_iter, best_path = n, candidate
    return best_path


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
    print(f"[FastGS] Launching: {' '.join(cmd)}", flush=True)

    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, cwd=FASTGS_DIR, env=FASTGS_ENV,
    )

    last_progress, last_line = 55, ""
    for line in process.stdout:
        line = line.strip()
        if not line:
            continue
        last_line = line
        print(f"[FastGS] {line}", flush=True)

        iteration = None
        m = re.search(r'\[ITER[ATION]*\s+(\d+)\]', line, re.IGNORECASE)
        if m:
            iteration = int(m.group(1))
        else:
            m = re.search(r'iteration\s+(\d+)', line, re.IGNORECASE)
            if m:
                iteration = int(m.group(1))

        if iteration is not None:
            pct = 55 + int((iteration / FASTGS_ITERATIONS) * 30)
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

    splat_ply = _find_splat_ply(model_path)
    if not splat_ply:
        raise RuntimeError(
            f"FastGS completed but no point_cloud.ply found under {model_path}/point_cloud/."
        )
    print(f"[FastGS] Splat PLY: {splat_ply} ({os.path.getsize(splat_ply)//1024} KB)", flush=True)
    return splat_ply


@celery.task(bind=True)
def run_pipeline(self, job_id: str):
    db = SessionLocal()
    job = db.query(Job).get(job_id)
    try:
        _set(db, job, status="running", progress=0)

        scene_out  = os.path.abspath(os.path.join(settings.storage_outputs, job_id))
        # images/ holds cubemap faces — used by BOTH COLMAP and FastGS
        images_dir = os.path.join(scene_out, "images")

        if os.path.exists(scene_out):
            shutil.rmtree(scene_out)
        os.makedirs(scene_out, exist_ok=True)

        # ---- Stage 1: Generate cubemap faces from 360° panoramas ----
        # 70 panoramas × 4 faces = 280 images → images/
        # Original panoramas also copied to colmap_images/ (unused now, kept for reference)
        _set(db, job, stage="cubemaps", progress=5)
        cube_summary = generate_cubemaps(job.upload_path, images_dir)
        print(f"[cubemaps] {cube_summary}", flush=True)
        _set(db, job, progress=20)

        # ---- Stage 2: COLMAP on cubemap faces ----
        # cubemap faces from different physical positions have real parallax
        # → COLMAP can compute camera poses and sparse 3D points
        _set(db, job, stage="colmap", progress=25)
        colmap_summary = run_colmap(images_dir, scene_out, use_gpu=True)
        job.summary = json.dumps({"colmap": colmap_summary})
        _set(db, job, progress=55)

        # ---- Stage 3: FastGS on cubemap faces (same images/ folder) ----
        # COLMAP sparse/0/ has poses for the cubemap faces
        # FastGS trains a Gaussian splat on those faces
        _set(db, job, stage="gaussian_splat", progress=55,
             log_tail="Starting FastGS training...")
        # Free GPU memory before FastGS
        import torch; torch.cuda.empty_cache() if torch.cuda.is_available() else None
        splat_ply = _run_fastgs(db, job, scene_out)

        summary = json.loads(job.summary)
        summary["splat_ply"] = os.path.relpath(splat_ply, scene_out)
        job.summary = json.dumps(summary)
        _set(db, job, stage="gaussian_splat", progress=85,
             log_tail="FastGS training complete.")

        # ---- Stub stages (future: cleanup, mesh, detection etc.) ----
        for i, stage in enumerate(STUB_STAGES):
            _set(db, job, stage=stage,
                 progress=85 + int((i / len(STUB_STAGES)) * 15))
            time.sleep(1)

        job.output_path = scene_out
        _set(db, job, status="done", stage="complete", progress=100)

    except Exception as e:
        _set(db, job, status="failed", error=str(e))
        raise
    finally:
        db.close()