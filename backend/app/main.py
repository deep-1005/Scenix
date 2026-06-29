import os
import json
import shutil
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
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

def _find_splat_ply(job_id: str) -> str | None:
    """Find the FastGS output PLY — checks multiple possible locations."""
    base = settings.storage_outputs
    candidates = [
        # Primary: what tasks.py saves via _find_splat_ply
        os.path.join(base, job_id, "gaussian_output", "point_cloud",
                     f"iteration_{30000}", "point_cloud.ply"),
        # Fallback: any iteration
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    # Search all iterations
    pc_dir = os.path.join(base, job_id, "gaussian_output", "point_cloud")
    if os.path.isdir(pc_dir):
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
        if best_path:
            return best_path
    return None

# ── Jobs ───────────────────────────────────────────────────────────────────────

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
             "progress": j.progress, "scene_name": j.scene_name,
             "created_at": j.created_at.isoformat() if j.created_at else None} for j in jobs]

@app.get("/jobs/{job_id}/images")
def list_images(job_id: str):
    img_dir = os.path.join(settings.storage_outputs, job_id, "images")
    if not os.path.isdir(img_dir):
        return {"images": []}
    exts = (".jpg", ".jpeg", ".png")
    files = sorted(f for f in os.listdir(img_dir) if f.lower().endswith(exts))
    return {"images": [f"/files/{job_id}/images/{f}" for f in files]}

@app.get("/jobs/{job_id}/ply")
def get_ply(job_id: str):
    """Sparse COLMAP point cloud PLY for the 3D viewer."""
    ply = os.path.join(settings.storage_outputs, job_id, "points.ply")
    if not os.path.exists(ply):
        raise HTTPException(404, "PLY not ready")
    return FileResponse(ply, media_type="application/octet-stream",
                        filename=f"{job_id}_sparse.ply")

@app.get("/jobs/{job_id}/splat")
def get_splat(job_id: str):
    """
    FastGS Gaussian Splat PLY — this is what the frontend calls splatPlyUrl().
    Returns the trained point_cloud.ply with Content-Disposition: attachment
    so the browser downloads it with a .ply extension SuperSplat can open.
    """
    splat_ply = _find_splat_ply(job_id)
    if not splat_ply:
        raise HTTPException(404, "Gaussian splat not ready yet")
    return FileResponse(
        splat_ply,
        media_type="application/octet-stream",
        filename=f"{job_id}_gaussian.ply",
        headers={"Content-Disposition": f'attachment; filename="{job_id}_gaussian.ply"'},
    )

@app.delete("/jobs/{job_id}")
def delete_job(job_id: str):
    db = SessionLocal()
    job = db.query(Job).get(job_id)
    if not job:
        db.close()
        raise HTTPException(404, "job not found")
    upload_path = os.path.join(settings.storage_uploads, job_id)
    output_path = os.path.join(settings.storage_outputs, job_id)
    if os.path.exists(upload_path):
        shutil.rmtree(upload_path)
    if os.path.exists(output_path):
        shutil.rmtree(output_path)
    db.delete(job)
    db.commit()
    db.close()
    return {"deleted": job_id}

@app.get("/storage/summary")
def storage_summary():
    db = SessionLocal()
    jobs = db.query(Job).order_by(Job.created_at.desc()).all()
    db.close()
    result = []
    for j in jobs:
        upload_path = os.path.join(settings.storage_uploads, j.id)
        output_path = os.path.join(settings.storage_outputs, j.id)
        def dir_size(p):
            total = 0
            if os.path.exists(p):
                for dirpath, _, filenames in os.walk(p):
                    for f in filenames:
                        try:
                            total += os.path.getsize(os.path.join(dirpath, f))
                        except Exception:
                            pass
            return total
        result.append({
            "job_id": j.id,
            "scene_name": j.scene_name,
            "status": j.status,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "upload_mb": round(dir_size(upload_path) / 1024 / 1024, 1),
            "output_mb": round(dir_size(output_path) / 1024 / 1024, 1),
        })
    return result

# ── Gaussian Splatting (manual trigger — normally run via pipeline) ─────────────

@app.post("/jobs/{job_id}/gaussian-splat")
async def start_gaussian_splat(job_id: str, background_tasks: BackgroundTasks):
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
    splat_ply = _find_splat_ply(job_id)
    if splat_ply:
        return {"status": "done", "ply_url": f"/jobs/{job_id}/splat"}
    output_dir = os.path.join(settings.storage_outputs, job_id, "gaussian_output")
    if os.path.exists(output_dir):
        return {"status": "running"}
    return {"status": "not_started"}

@app.get("/jobs/{job_id}/gaussian-splat/download")
def download_splat_legacy(job_id: str):
    """Legacy endpoint — redirects to /splat."""
    return get_splat(job_id)