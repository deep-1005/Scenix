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

# Use the conda env's python directly — this is the critical fix.
# When Celery workers launch subprocesses, PATH may not include conda,
# so "python" resolves to system Python which lacks PyTorch/CUDA.
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

STUB_STAGES = ["cleanup", "mesh", "detection", "classify", "measure", "report"]


def _set(db, job, status=None, stage=None, progress=None, error=None, log_tail=None):
    if status is not None:   job.status = status
    if stage is not None:    job.stage = stage
    if progress is not None: job.progress = progress
    if error is not None:    job.error = error
    if log_tail is not None: job.log_tail = log_tail
    db.commit()


def _validate_colmap_output(scene_out: str):
    """
    FastGS scene/__init__.py detects COLMAP scenes by checking for sparse/0/.
    Raises clearly if the structure isn't right before we even launch FastGS.
    """
    sparse0 = os.path.join(scene_out, "sparse", "0")
    images  = os.path.join(scene_out, "images")

    if not os.path.isdir(images):
        raise RuntimeError(f"FastGS needs an images/ folder at: {images}")

    if not os.path.isdir(sparse0):
        raise RuntimeError(
            f"FastGS needs sparse/0/ at: {sparse0}\n"
            "COLMAP mapper may not have produced a reconstruction."
        )

    # At least one of .bin or .txt must be present for each key file
    for stem in ("cameras", "images", "points3D"):
        has_bin = os.path.exists(os.path.join(sparse0, f"{stem}.bin"))
        has_txt = os.path.exists(os.path.join(sparse0, f"{stem}.txt"))
        if not has_bin and not has_txt:
            raise RuntimeError(
                f"Missing {stem}.bin/.txt in {sparse0}. "
                "COLMAP reconstruction may be incomplete."
            )

    img_count = len([
        f for f in os.listdir(images)
        if f.lower().endswith((".jpg", ".jpeg", ".png"))
    ])
    sparse0_files = os.listdir(sparse0)
    print(
        f"[FastGS] Validated scene: {img_count} images, "
        f"sparse/0/ has: {sparse0_files}"
    )


def _run_fastgs(db, job, scene_out: str):
    # Validate BEFORE launching so we get a clear error, not an AssertionError
    _validate_colmap_output(scene_out)

    # FastGS writes its model inside scene_out/gaussian_output/
    model_path = os.path.join(scene_out, "gaussian_output")
    os.makedirs(model_path, exist_ok=True)

    cmd = [
        CONDA_PYTHON, FASTGS_TRAIN,   # explicit conda python + absolute train.py path
        "-s", scene_out,              # source: must contain images/ and sparse/0/
        "--model_path", model_path,   # where FastGS writes output
        "--iterations", str(FASTGS_ITERATIONS),
        "--save_iterations", str(FASTGS_ITERATIONS),   # ← ADD THIS
        "--checkpoint_iterations", str(FASTGS_ITERATIONS),  # ← AND THIS
        "-r", "1",
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

    last_progress = 55
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
    print("[FastGS] Training complete.")


@celery.task(bind=True)
def run_pipeline(self, job_id: str):
    db = SessionLocal()
    job = db.query(Job).get(job_id)
    try:
        _set(db, job, status="running", progress=0)

        scene_out  = os.path.abspath(os.path.join(settings.storage_outputs, job_id))
        images_dir = os.path.join(scene_out, "images")

        # Clean up any previous partial run for this job
        if os.path.exists(scene_out):
            print(f"[pipeline] Removing previous output dir: {scene_out}")
            shutil.rmtree(scene_out)
        os.makedirs(scene_out, exist_ok=True)

        # ---- Stage 2: Cubemaps ----
        _set(db, job, stage="cubemaps", progress=5)
        cube_summary = generate_cubemaps(job.upload_path, images_dir)
        print(f"[cubemaps] {cube_summary}")
        _set(db, job, progress=20)

        # ---- Stage 3: COLMAP ----
        _set(db, job, stage="colmap", progress=25)
        colmap_summary = run_colmap(images_dir, scene_out, use_gpu=True)
        job.summary = json.dumps({"colmap": colmap_summary})
        _set(db, job, progress=55)

        # ---- Stage 4: Gaussian Splatting ----
        _set(db, job, stage="gaussian_splat", progress=55,
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

    except Exception as e:
        _set(db, job, status="failed", error=str(e))
        raise
    finally:
        db.close()