import os
import json
import shutil
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks  # type: ignore
from fastapi.middleware.cors import CORSMiddleware  # type: ignore
from fastapi.responses import FileResponse  # type: ignore
from fastapi.staticfiles import StaticFiles  # type: ignore
from app.models.db import SessionLocal, Job, init_db
from app.workers.tasks import run_pipeline
from app.core.config import settings
from app.pipeline.fastgs import run_fastgs

app = FastAPI(title="Forensic Digital Twin API")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def startup():
    init_db()
    os.makedirs(settings.storage_uploads, exist_ok=True)
    os.makedirs(settings.storage_outputs, exist_ok=True)
    app.mount("/files",
              StaticFiles(directory=settings.storage_outputs),
              name="files")

def _job_dict(job: Job) -> dict:
    try:
        summary = json.loads(job.summary or "{}")
    except Exception:
        summary = {}
    return {
        "job_id": job.id, "status": job.status, "stage": job.stage,
        "progress": job.progress, "scene_name": job.scene_name,
        "output_path": job.output_path, "error": job.error,
        "summary": summary,
    }

@app.post("/jobs")
async def create_job(scene_name: str = Form(...),
                     files: list[UploadFile] = File(...)):
    db = SessionLocal()
    job = Job(scene_name=scene_name, status="queued")
    db.add(job); db.commit(); db.refresh(job)
    dest = os.path.join(settings.storage_uploads, job.id)
    os.makedirs(dest, exist_ok=True)
    for f in files:
        with open(os.path.join(dest, f.filename), "wb") as out:
            shutil.copyfileobj(f.file, out)
    job.upload_path = dest; db.commit()
    run_pipeline.delay(job.id)
    jid = job.id; db.close()
    return {"job_id": jid, "status": "queued"}

@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    db = SessionLocal()
    job = db.query(Job).get(job_id)
    db.close()
    if not job:
        raise HTTPException(404, "job not found")
    return _job_dict(job)

@app.get("/jobs")
def list_jobs():
    db = SessionLocal()
    jobs = db.query(Job).order_by(Job.created_at.desc()).all()
    db.close()
    return [{"job_id": j.id, "status": j.status, "stage": j.stage,
             "progress": j.progress, "scene_name": j.scene_name} for j in jobs]

@app.get("/jobs/{job_id}/images")
def list_images(job_id: str):
    """List cube-face image URLs for this job."""
    img_dir = os.path.join(settings.storage_outputs, job_id, "images")
    if not os.path.isdir(img_dir):
        return {"images": []}
    exts = (".jpg", ".jpeg", ".png")
    files = sorted(f for f in os.listdir(img_dir) if f.lower().endswith(exts))
    return {"images": [f"/files/{job_id}/images/{f}" for f in files]}

@app.get("/jobs/{job_id}/ply")
def get_ply(job_id: str):
    """Download the COLMAP point cloud PLY."""
    ply = os.path.join(settings.storage_outputs, job_id, "points.ply")
    if not os.path.exists(ply):
        raise HTTPException(404, "PLY not ready")
    return FileResponse(ply, media_type="application/octet-stream",
                        filename=f"{job_id}.ply")

# ── Gaussian Splatting ─────────────────────────────────────────────────────────

@app.post("/jobs/{job_id}/gaussian-splat")
async def start_gaussian_splat(job_id: str, background_tasks: BackgroundTasks):
    """Kick off FastGS training for a job that already has COLMAP output."""
    scene_dir = os.path.join(settings.storage_outputs, job_id)

    if not os.path.exists(scene_dir):
        raise HTTPException(404, f"Job {job_id} output folder not found")

    sparse_path = os.path.join(scene_dir, "sparse", "0")
    if not os.path.exists(sparse_path):
        raise HTTPException(400, "COLMAP sparse/0 output not found — run COLMAP first")

    def _run():
        try:
            run_fastgs(scene_dir=scene_dir, work_dir=scene_dir, stream=False)
        except Exception as e:
            print(f"[FastGS] ERROR for job {job_id}: {e}")

    background_tasks.add_task(_run)
    return {"status": "started", "job_id": job_id}

@app.get("/jobs/{job_id}/gaussian-splat/status")
def gaussian_splat_status(job_id: str):
    """Check whether FastGS has finished for this job."""
    scene_dir = os.path.join(settings.storage_outputs, job_id)
    ply_path = os.path.join(scene_dir, "gaussian_output", "point_cloud",
                            "iteration_30000", "point_cloud.ply")

    if os.path.exists(ply_path):
        return {
            "status": "done",
            "ply_url": f"/jobs/{job_id}/gaussian-splat/download"
        }

    output_dir = os.path.join(scene_dir, "gaussian_output")
    if os.path.exists(output_dir):
        return {"status": "running"}

    return {"status": "not_started"}

@app.get("/jobs/{job_id}/gaussian-splat/download")
def download_splat(job_id: str):
    """Serve the Gaussian Splat .ply file."""
    ply_path = os.path.join(settings.storage_outputs, job_id,
                            "gaussian_output", "point_cloud",
                            "iteration_30000", "point_cloud.ply")
    if not os.path.exists(ply_path):
        raise HTTPException(404, "Splat not generated yet")
    return FileResponse(ply_path, media_type="application/octet-stream",
                        filename=f"{job_id}_splat.ply")
