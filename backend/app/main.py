import os
import json
import re
import shutil
import asyncio
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.models.db import SessionLocal, Job, init_db
from app.workers.tasks import run_pipeline
from app.core.config import settings
from app.pipeline.fastgs import run_fastgs
from starlette.middleware.cors import CORSMiddleware as StarletteCORSMiddleware
from starlette.applications import Starlette
from fastapi.middleware.cors import CORSMiddleware

# ── App setup (this was missing — `app` must exist before any @app.* decorator) ──
app = FastAPI(title="Forensic Digital Twin API")
app.add_middleware(CORSMiddleware, allow_origins=["*"],allow_credentials=False,
                   allow_methods=["*"], allow_headers=["*"])

# Matches perspective-view filenames produced by generate_cubemaps(),
# e.g. "IMG_20260604_141433_yaw144_pitch-20.jpg"
CUBEMAP_NAME_RE = re.compile(
    r"^(?P<source>.+)_yaw(?P<yaw>-?\d+)_pitch(?P<pitch>-?\d+)\.(?P<ext>jpg|jpeg|png)$",
    re.IGNORECASE,
)

@app.on_event("startup")
def startup():
    init_db()
    os.makedirs(settings.storage_uploads, exist_ok=True)
    os.makedirs(settings.storage_outputs, exist_ok=True)

    # CORS fix: StaticFiles mounted directly doesn't reliably inherit the
    # parent app's CORSMiddleware in all FastAPI/Starlette version combos.
    # <img> tags work regardless (no CORS needed for image element loads),
    # but fetch() calls — like the "Download all" zip feature — strictly
    # require Access-Control-Allow-Origin on the response, which the plain
    # mount wasn't sending. Wrapping it in its own Starlette app with its
    # own CORS middleware guarantees the header is always present.
    files_app = Starlette()
    files_app.add_middleware(
        StarletteCORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "HEAD", "OPTIONS"],
        allow_headers=["*"],
    )
    files_app.mount("/", StaticFiles(directory=settings.storage_outputs), name="static")
    app.mount("/files", files_app, name="files")

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
        os.path.join(base, job_id, "gaussian_output", "point_cloud",
                     f"iteration_{30000}", "point_cloud.ply"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
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

def _save_files_sync(dest: str, files_data: list[tuple[str, bytes]]):
    """
    Runs in a worker thread via asyncio.to_thread — keeps the actual
    (blocking) disk writes off the event loop so uvicorn can keep
    responding to other requests (health checks, job polls, etc.)
    while a large multi-image upload is being written to disk.

    [FORENSIC FIX] Previously wrote each file using ONLY its original
    filename (`os.path.join(dest, filename)`), with no collision handling.
    Phone photo exports very commonly reuse filenames across different
    capture sessions/folders (IMG_0001.jpg, IMG_0002.jpg, ...). If two
    uploaded files shared a name, the second silently overwrote the first
    on disk — no error, no warning — so the same "810 photos" could yield
    a different number of surviving files on different upload attempts,
    depending on enumeration order. Every file now gets a disk-unique name
    (an index prefix), so collisions are structurally impossible, while the
    original name is still preserved (after the prefix) for reference.
    """
    seen_names = set()
    for i, (filename, content) in enumerate(files_data):
        safe_name = os.path.basename(filename or f"upload_{i}")
        unique_name = f"{i:05d}__{safe_name}"
        if unique_name in seen_names:
            # Should be structurally impossible given the index prefix,
            # but guard anyway rather than silently overwriting.
            base, ext = os.path.splitext(unique_name)
            unique_name = f"{base}_{i}{ext}"
        seen_names.add(unique_name)
        with open(os.path.join(dest, unique_name), "wb") as out:
            out.write(content)

@app.post("/jobs")
async def create_job(scene_name: str = Form(...),
                     files: list[UploadFile] = File(...)):
    db = SessionLocal()
    job = Job(scene_name=scene_name, status="queued")
    db.add(job); db.commit(); db.refresh(job)
    dest = os.path.join(settings.storage_uploads, job.id)
    os.makedirs(dest, exist_ok=True)

    # Read uploads asynchronously, then push the actual disk-write work
    # to a thread so it doesn't block the event loop. Previously this used
    # a synchronous `shutil.copyfileobj` loop directly inside `async def`,
    # which froze the entire server for the duration of the write — long
    # enough over a slow connection (e.g. via ngrok) to trip proxy
    # timeouts and produce ERR_NGROK_3004 on the client side.
    files_data = [(f.filename, await f.read()) for f in files]
    print(f"[upload] Received {len(files_data)} file(s) for job {job.id}", flush=True)
    await asyncio.to_thread(_save_files_sync, dest, files_data)

    on_disk = len(os.listdir(dest))
    if on_disk != len(files_data):
        print(
            f"[upload] WARNING: received {len(files_data)} file(s) but only "
            f"{on_disk} exist on disk after save for job {job.id} — check "
            f"disk space / permissions.",
            flush=True,
        )

    job.upload_path = dest; db.commit()
    run_pipeline.delay(job.id)
    jid = job.id; db.close()
    return {"job_id": jid, "status": "queued", "files_received": len(files_data), "files_saved": on_disk}

@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    db = SessionLocal()
    job = db.query(Job).get(job_id)
    db.close()
    if not job:
        raise HTTPException(404, "job not found")
    return _job_dict(job)

@app.post("/jobs/{job_id}/resume")
def resume_job(job_id: str):
    db = SessionLocal()
    job = db.query(Job).get(job_id)
    if not job:
        db.close()
        raise HTTPException(404, "job not found")
    if job.status != "failed":
        current_status = job.status
        db.close()
        raise HTTPException(400, f"Can only resume failed jobs (current status: {current_status})")
    from_stage = job.stage
    db.close()
    run_pipeline.delay(job_id, resume=True)
    return {"status": "resuming", "job_id": job_id, "from_stage": from_stage}

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

@app.get("/jobs/{job_id}/cubemaps")
def list_cubemaps(job_id: str):
    """
    Lists perspective-view images generated by generate_cubemaps().
    Files are named like: {panorama_name}_yaw{yaw}_pitch{pitch}.jpg
    and live in storage/outputs/{job_id}/images/

    Returns 404 while the images/ folder doesn't exist yet or is empty,
    so the frontend can treat that as "not ready" rather than a hard error.
    """
    images_dir = os.path.join(settings.storage_outputs, job_id, "images")
    if not os.path.isdir(images_dir):
        raise HTTPException(404, "Cubemaps not generated yet")

    exts = (".jpg", ".jpeg", ".png")
    files = sorted(f for f in os.listdir(images_dir) if f.lower().endswith(exts))
    if not files:
        raise HTTPException(404, "Cubemaps not generated yet")

    cubemaps = []
    for fname in files:
        m = CUBEMAP_NAME_RE.match(fname)
        if m:
            source = m.group("source")
            yaw = m.group("yaw")
            pitch = m.group("pitch")
            face = f"yaw{yaw}_pitch{pitch}"
        else:
            source = os.path.splitext(fname)[0]
            face = "original"
        cubemaps.append({
            "source_image": source,
            "face": face,
            "url": f"/files/{job_id}/images/{fname}",
        })

    return {"cubemaps": cubemaps, "count": len(cubemaps)}

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

# [FORENSIC FIX] SuGaR refinement stage is temporarily disabled — the
# app.pipeline.sugar_refine module is missing (see tasks.py, which no
# longer imports/calls it either). Both endpoints below now return a clear
# 404 instead of crashing the entire API at import time, which is what
# was happening before: `from app.pipeline.sugar_refine import
# find_sugar_outputs` at the top of this file raised ModuleNotFoundError
# on startup, so FastAPI never came up and every request (including
# POST /jobs) just hung/failed with no response — that's why "Starting..."
# never resolved in the UI.
@app.get("/jobs/{job_id}/sugar-mesh")
def get_sugar_mesh(job_id: str):
    """SuGaR's refined, UV-textured mesh (.obj) — currently disabled."""
    raise HTTPException(404, "SuGaR refinement is currently disabled")

@app.get("/jobs/{job_id}/sugar-splat")
def get_sugar_splat(job_id: str):
    """SuGaR's refined Gaussian splat .ply — currently disabled."""
    raise HTTPException(404, "SuGaR refinement is currently disabled")

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
            run_fastgs(scene_dir=scene_dir, work_dir=scene_dir)
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


# backend/app/main.py

@app.get("/jobs/{job_id}/evidence")
def get_evidence(job_id: str):
    scene_out = os.path.abspath(os.path.join(settings.storage_outputs, job_id))

    classified_path = os.path.join(scene_out, "evidence_classified.json")
    measurements_path = os.path.join(scene_out, "measurements.json")

    if not os.path.exists(classified_path):
        return {"status": "not_ready", "evidence": [], "room_dimensions": None}

    with open(classified_path) as f:
        evidence = json.load(f)

    room_dimensions = None
    unit = "colmap_units"
    if os.path.exists(measurements_path):
        with open(measurements_path) as f:
            measurements = json.load(f)
        room_dimensions = measurements.get("room_dimensions")
        unit = measurements.get("unit", "colmap_units")
        # measurements.json's evidence list has the authoritative dimensions —
        # merge those in by id since evidence_classified.json only has label/classification
        dims_by_id = {e["id"]: e for e in measurements.get("evidence", [])}
        for item in evidence:
            if item["id"] in dims_by_id:
                item["dimensions"] = dims_by_id[item["id"]]["dimensions"]
                item["centroid"] = dims_by_id[item["id"]]["centroid"]

    return {"status": "ready", "evidence": evidence, "room_dimensions": room_dimensions, "unit": unit}