# Scenix

Developed at CAVE labs, PES University under the guidance of mentors Professor Dr Adithya Balasubramanyam and Manoj Kumar HR.


**3D Scene Reconstruction using Gaussian Splatting with Insta360 360° camera**
Scenix is an end-to-end platform that converts raw 360° captures of any scene — rooms, buildings, labs, heritage sites, facilities — into a navigable, measurable, photorealistic 3D Gaussian splat, with automatically detected, classified, and labelled objects and an auto-generated PDF summary report as future scope.

Upload 360° panoramas of a scene; the system slices each one into pinhole perspective views, recovers camera poses and a sparse point cloud with COLMAP, statistically cleans the cloud, trains a Gaussian splat with FastGS, de-noises the splat, and serves the result through a web interface with per-stage progress tracking, resumable jobs, an interactive splat viewer, and an object-analytics table.

PS: Some file names are mentioned as forensic because it was initially meant for crime scene reconstruction.

<img width="1612" height="826" alt="image" src="https://github.com/user-attachments/assets/8c4551c6-8588-40ea-ade1-62b587a5996f" />


> **The core research contribution:** The proposed framework presents an end-to-end automated pipeline for 3D scene reconstruction from 360° panoramic images. Unlike conventional Gaussian Splatting workflows that require manual preprocessing and prepared datasets, the proposed system integrates automatic perspective-view generation, COLMAP-based Structure-from-Motion, adaptive point cloud cleaning using DBSCAN and RANSAC, FastGS-based Gaussian Splat training, and an interactive web-based visualization platform into a single unified framework. The pipeline further incorporates quality-enhancement techniques, including cleaned point cloud promotion and tuned densification, along with resumable execution and real-time progress monitoring, making it a scalable and deployment-ready solution for efficient 3D scene reconstruction.

---

## Table of Contents

- [Key Features](#key-features)
- [The 12-Stage Pipeline](#the-12-stage-pipeline)
- [Architecture](#architecture)
- [Repository Layout](#repository-layout)
- [Tech Stack](#tech-stack)
- [Installation](#installation)
- [Running the Platform](#running-the-platform)
- [Usage](#usage)
- [Training Configuration](#training-configuration)
- [Implementation Notes](#implementation-notes)
- [Troubleshooting](#troubleshooting)
- [Validation](#validation)
- [Future Scope](#future-scope)
- [Research Direction](#research-direction)

---

## Key Features

- **One-click reconstruction** — upload 360° images and the full chain (perspective views → COLMAP → cleaning → FastGS → cleanup → analytics → report) runs as a single tracked Celery job with per-stage progress and live log tail.
- **Resumable jobs** — every stage has an on-disk completion check; a failed or stopped job can be resumed from the last completed stage instead of restarting from scratch.
- **360° panorama support** — automatic equirectangular → perspective (`e2p`) conversion: 15 pinhole views per panorama (5 yaw × 3 pitch, 90° FOV, 1400×1400). Raw Insta360 exports are handled directly; JPG, PNG, WebP, BMP, TIFF and iPhone HEIC/HEIF are all accepted (via pillow-heif).
- **Cleaned point cloud promotion** — RANSAC + DBSCAN + statistical outlier removal (Open3D, auto-tuned from average point spacing) runs on the sparse cloud *before* training, and the cleaned cloud is promoted into `sparse/0/points3D.ply` so FastGS provably trains on cleaned points.
- **Photorealistic Gaussian splatting** — FastGS training with a tuned densification preset and mid-training checkpoints (see [Training Configuration](#training-configuration)).
- **Splat cleanup** — floaters and low-opacity noise removed from the trained splat with `3dgsconverter` (opacity threshold + statistical outlier removal).
- **Object analytics(future scope)** — open-vocabulary 2D detection (OwlViT) with prompts, multi-view triangulation of detections into 3D scene coordinates using recovered COLMAP poses, DBSCAN clustering into distinct objects, and OpenCLIP classification of per-item crops — surfaced as a tabulated Evidence view with dimensions and room dimensions.
- **Marker-based scale calibration** — an ArUco marker (4×4_50, default 10 cm) visible in ≥2 views is triangulated from real camera poses to convert COLMAP units to metres; without a marker, measurements fall back to relative units.
- **Automated PDF report(future scope)** — Jinja2 + WeasyPrint render the room dimensions and object table to `report.pdf` as the final pipeline stage.
- **Interactive web viewers** — generated-view gallery, sparse point cloud with camera-position markers, Gaussian splat preview, and a full in-browser splat viewer (`@mkkellogg/gaussian-splats-3d` + Three.js), with `.ply` downloads at every step.
- **Scene management** — multiple scenes with progress bars, search, per-stage stop, resume, delete, and a storage-usage summary.
- **Desktop wrapper** — an Electron shell (`desktop/`) for running the UI as a native app.

## The 12-Stage Pipeline

| # | Stage | What happens | Core tech |
|---|-------|--------------|-----------|
| 1 | **Capture & Ingestion** | 360° photos/video + metadata captured on site and uploaded | Insta360 X3/X4, FastAPI |
| 2 | **View Generation** | Each panorama sliced into 15 pinhole perspective views (5 yaw × 3 pitch, 90° FOV, 1400×1400) | py360convert (`e2p`), OpenCV |
| 3 | **Preprocessing & QC** | Blurry / duplicate / low-quality frames removed; video → frames (rejections logged) | OpenCV Laplacian, perceptual hash |
| 4 | **Photogrammetry** | Camera poses + sparse 3D point cloud recovered; multi-model handling; undistortion | COLMAP 3.13 / pycolmap |
| 5 | **Point-Cloud Cleaning** | RANSAC + DBSCAN + SOR on the sparse cloud, auto-tuned; cleaned cloud promoted for training | Open3D, NumPy |
| 6 | **Gaussian Splatting** | Photorealistic 3D model trained from `sparse/0` | FastGS, PyTorch, CUDA |
| 7 | **Splat Cleanup** | Floating noise / low-opacity splats auto-removed | 3dgsconverter |
| 8 | **3D Object Detection(future scope)** | Objects detected in 2D with text prompts, triangulated to 3D via COLMAP poses, clustered | OwlViT, DBSCAN, custom triangulation |
| 9 | **Classification & Tagging(future scope)** | Detected items classified from crops, assigned IDs and confidence scores | OpenCLIP (ViT-B-32) |
| 10 | **Measurement** | Room dimensions + per-item dimensions; metric scale from an ArUco marker when present | OpenCV ArUco, Open3D, NumPy |
| 11 | **Final Scene Viewer** | Walkable scene; labelled object overlay in progress | Three.js + gaussian-splats-3d |
| 12 | **Automated Report(future scope)** | PDF summary: room dimensions, object table with classifications and dimensions | Jinja2, WeasyPrint |

Stages 2, 8, 9, and 11 constitute the core research contribution of the project.

**Data flow principle:** the splat is for *viewing*; measurement relies on COLMAP poses and cleaned point clouds — plus scale calibration against a known reference before any distance is trusted.

## Architecture

```
                        ┌─────────────────────────────┐
                        │   React + Vite + Three.js   │
                        │   splat viewers (5173)      │
                        └──────────────┬──────────────┘
                                       │ REST (axios)
                        ┌──────────────▼──────────────┐
                        │      FastAPI  (8000)        │
                        │      backend/app/main.py    │
                        └──────┬───────────────┬──────┘
                               │               │
                     job queue │               │ scene metadata
                        ┌──────▼──────┐  ┌─────▼─────────────┐
                        │    Redis    │  │ SQLite (default)  │
                        └──────┬──────┘  │ or PostgreSQL     │
                               │         └───────────────────┘
                        ┌──────▼──────────────────────────────┐
                        │  Celery worker (workers/tasks.py)   │
                        │  views → COLMAP → cleaning → FastGS │
                        │  → cleanup → detect → classify      │
                        │  → measure → report                 │
                        └─────────────────────────────────────┘
```

Long-running reconstruction jobs (COLMAP and FastGS runs take minutes to hours) execute asynchronously in a Celery worker so the API and UI stay responsive; every stage reports status, progress, and a log tail back to the job record, and each stage's completion is verifiable on disk (which is what makes `resume` safe).

Scene metadata lives in SQLAlchemy models; the database defaults to **SQLite** (`sqlite:///./forensic.db`) and switches to PostgreSQL by setting `DATABASE_URL` in `backend/.env` — no code changes needed.

**Standard scene folder layout** (enforced — downstream tools depend on it):

```
storage/outputs/<job_id>/
├── images/                  # perspective views from Stage 2 (undistorted after COLMAP)
├── sparse/0/                # cameras.bin, images.bin, points3D.bin, points3D.ply (cleaned)
├── gaussian_output/         # FastGS model; point_cloud/iteration_*/point_cloud.ply (+ _clean.ply)
├── evidence.json            # detected objects (3D positions, supporting views)
├── evidence_classified.json # + classification labels and confidences
├── measurements.json        # room + per-item dimensions
├── report.pdf               # final generated report
└── database.db              # COLMAP database — kept OUT of images/; delete to reset COLMAP
```

Only `sparse/0/` matters for training; the COLMAP `dense/` output is used solely as the source of undistorted images.

## Repository Layout

```
Scenix/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI app + all REST endpoints
│   │   ├── core/config.py     # settings (.env): DATABASE_URL, REDIS_URL, storage paths, COLMAP GPU
│   │   ├── models/db.py       # SQLAlchemy Job model
│   │   ├── workers/tasks.py   # Celery pipeline: stage order, resume checks, FastGS preset
│   │   └── pipeline/          # cubemaps.py (e2p views), colmap_sfm.py, clean_pointcloud.py,
│   │                          # fastgs.py, cleanup.py, detection.py, classify.py,
│   │                          # measure.py, report.py, colmap_geometry.py
│   ├── fix_fastgs_flags.py    # strips regularizer flags unsupported by the FastGS build
│   └── requirements.txt
├── frontend/                  # React + Vite; components incl. GaussianSplatViewer,
│                              # PointCloudViewer, EvidenceViewer, StorageManager
├── desktop/                   # Electron wrapper (npm start)
├── run.sh                     # launcher: bash run.sh {api|worker|frontend}
└── services.sh                # user-space Postgres + Redis: bash services.sh {start|stop|status}
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Capture | Insta360 360° camera, Insta360 Studio |
| Conversion | py360convert (`e2p`), OpenCV, Pillow (+ pillow-heif for HEIC), NumPy |
| Photogrammetry | COLMAP 3.13 (conda-forge, CUDA build), pycolmap |
| Splatting | FastGS (primary); 3dgsconverter (splat cleanup) |
| Object Detection | OwlViT (open-vocabulary detection, via transformers), OpenCLIP ViT-B-32 (classification), scikit-learn DBSCAN; Grounding DINO / Ultralytics available in the environment for the detection upgrade path |
| Cleaning | Open3D (RANSAC / DBSCAN / SOR), auto-tuned parameters |
| Measurement | OpenCV ArUco (scale marker), Open3D, NumPy |
| Backend | Python, FastAPI, Celery, Redis, SQLAlchemy (SQLite default / PostgreSQL optional) |
| Frontend | React 18, Vite, Three.js, @mkkellogg/gaussian-splats-3d, axios |
| Desktop | Electron |
| Inspection | SuperSplat (browser splat cleanup), MeshLab |
| Reporting | Jinja2 + WeasyPrint (PDF) |
| Production target | Docker → Kubernetes + NVIDIA container runtime |

## Installation

The platform runs entirely user-space via conda — **no sudo required**. Developed on Ubuntu 24.04 with an NVIDIA GPU (CUDA required for FastGS training; COLMAP runs CPU-safe by default and GPU can be enabled via config).

### 1. Clone

```bash
git clone https://github.com/deep-1005/Scenix.git
cd Scenix
```

### 2. Create the conda environment

```bash
conda create -n forensic python=3.11 -y
conda activate forensic

# COLMAP (CUDA build) from conda-forge; add postgresql redis-server if not using SQLite
conda install -c conda-forge colmap pycolmap redis-server -y

# Python dependencies (FastAPI, Celery, py360convert, Open3D, pycolmap,
# 3dgsconverter, transformers/OwlViT deps, open_clip_torch, WeasyPrint, …)
pip install -r backend/requirements.txt
```

### 3. FastGS

```bash
git clone https://github.com/fastgs/FastGS.git
cd FastGS
pip install -e .          # builds diff_gaussian_rasterization_fastgs (needs CUDA toolkit)
cd ..
```

If training later fails with `ModuleNotFoundError: No module named 'diff_gaussian_rasterization_fastgs'`, the rasterizer extension didn't build — re-run the install inside the env with CUDA visible. This exact failure also surfaces *inside the platform* as `Failed: FastGS exited with code 1` on the Gaussian stage.

Then point the pipeline at your paths: `FASTGS_DIR`, `CONDA_PYTHON`, and the `FASTGS_ENV` CUDA paths at the top of `backend/app/workers/tasks.py` (or set the `FASTGS_DIR` environment variable).

### 4. Database and Redis

SQLite is the default — nothing to set up. Start Redis (required for Celery):

```bash
redis-server --daemonize yes
```

To use PostgreSQL instead, set `DATABASE_URL` in `backend/.env` and either run your own server or use the bundled user-space helper:

```bash
bash services.sh start     # user-space Postgres + Redis (data under .localdb/)
bash services.sh status
```

### 5. Frontend (and optional desktop shell)

```bash
cd frontend && npm install
# optional native wrapper:
cd ../desktop && npm install
```

## Running the Platform

Open **three terminals**, each with `conda activate forensic` — or use the launcher:

```bash
bash run.sh api        # Terminal 1 — FastAPI on :8000 (run from backend/)
bash run.sh worker     # Terminal 2 — Celery worker (runs the pipeline)
bash run.sh frontend   # Terminal 3 — Vite dev server on :5173
```

Equivalent manual commands:

```bash
cd backend && uvicorn app.main:app --reload --port 8000
cd backend && celery -A app.workers.tasks worker --loglevel=info
cd frontend && npm run dev
```

Open **http://localhost:5173**. The header shows `API connected` when the frontend can reach the backend. The Electron app is launched with `npm start` from `desktop/`.

> **Note:** Run uvicorn from `backend/`, not the repo root — `ModuleNotFoundError: No module named 'app'` always means it was launched from the wrong directory.


<img width="1844" height="968" alt="image" src="https://github.com/user-attachments/assets/c45430d1-d4a5-4ac1-a5cd-71eeb2a4fb53" />



### Remote / LAN access

- **SSH tunnel** (recommended): `ssh -L 5173:localhost:5173 -L 8000:localhost:8000 user@<host>`
- **ngrok** works but free-tier bandwidth is exhausted quickly by splat streaming; prefer LAN hosting or a duckdns.org subdomain for demos.

## Usage

1. **Create a scene** — enter a name and drop the 360° equirectangular exports (Insta360 Studio: use the *360 photos* export, not reframed DNG). JPG/PNG/WebP/BMP/TIFF/HEIC accepted; up to 100 panoramas per scene (larger sets are evenly subsampled).

2. **Start reconstruction** — the stage tracker runs Views → COLMAP → Cleaning → Gaussian → Cleanup → Detection → Classify → Measure → Report, with live progress and log tail per stage.

3. **Inspect results** in the tabs:
   - **Cubemaps** — the generated perspective views (15 per panorama), downloadable
     
      <img width="1498" height="777" alt="image" src="https://github.com/user-attachments/assets/361e46e1-0616-4b65-bf0e-4e1d1d90db01" />

   - **Point cloud** — sparse reconstruction with camera-position markers, `.ply` download
     
      <img width="1526" height="788" alt="image" src="https://github.com/user-attachments/assets/3e0f4d3f-16bf-47e2-8189-1d373674c277" />

   - **Gaussian splat** — splat-centers preview, trained `.ply` download (open in SuperSplat for full-quality inspection)
     
      <img width="1612" height="835" alt="image" src="https://github.com/user-attachments/assets/6218683c-98d1-4583-a24d-f2ec40c1801f" />

   - **Splat viewer** — full photorealistic reconstruction, explorable in the browser
     
      <img width="1608" height="837" alt="image" src="https://github.com/user-attachments/assets/2f0c3096-98ef-4390-904f-0b48022789ee" />

   - **Evidence** — detected/classified items with confidence and dimensions, plus room dimensions (Future Scope)

     
4. **Manage scenes** — every scene keeps its progress; failed or stopped jobs can be **resumed** from the last completed stage; scenes can be searched, stopped, and deleted from the sidebar, and disk usage is visible in the storage summary.

   <img width="1652" height="865" alt="image" src="https://github.com/user-attachments/assets/0c67bd74-0ed3-49ab-aa36-1180627920c6" />

### Capture Protocol (Stage 1)

**The camera must physically move between shots.** Rotation-only capture gives zero depth and reconstruction *will* fail regardless of downstream settings. Capture 360° panoramas from many standing positions across the scene with generous overlap; ~70 positions reconstructed a full classroom well. Avoid motion blur — motion-blurred frames significantly degrade COLMAP feature matching. For metric measurements, place a printed ArUco marker (4×4_50 dictionary, known size — default 10 cm) where at least two capture positions can see it.

Some images taken by Insta360 degree camera: 

<img width="1730" height="817" alt="image" src="https://github.com/user-attachments/assets/d024baa9-0f8d-4d05-907e-d961c9abb676" />
<img width="1565" height="766" alt="image" src="https://github.com/user-attachments/assets/e2a2566a-e803-4c96-9f17-842314713461" />

These are images of a classroom in PES University, BE block.

## Training Configuration

The live preset (`_build_fastgs_cmd` in `backend/app/workers/tasks.py`) wraps FastGS with tuned defaults:

```bash
python train.py -s <scene_path> --model_path <out> \
    --iterations 30000 \
    --save_iterations 15000 30000 \
    --checkpoint_iterations 30000 \
    -r 2 \
    --densification_interval 100 \
    --densify_until_iter 15000 \
    --grad_abs_thresh 0.0006 \
    --grad_thresh 0.00015 \
    --loss_thresh 0.06 \
    --highfeature_lr 0.02 \
    --lambda_dssim 0.3 \
    --test_iterations 7000 15000 30000
```

| Setting | Value | Why |
|---------|-------|-----|
| `--iterations` | 30 000 | Beyond ~30k FastGS overfits the training views rather than improving reconstruction. |
| Densification | interval 100, until iter 15 000, lowered gradient thresholds | Denser splat growth early in training for finer geometry, frozen for the second half. |
| `--lambda_dssim` | 0.3 | Heavier structural-similarity weighting for sharper reconstruction. |
| `-r` | 2 (preset) / 1 (max fidelity) | Input resolution divisor. Views are generated at 1400×1400 in Stage 2, so `-r 2` trains at 700 px for speed; switch to `-r 1` for maximum-fidelity runs. **Never rely on FastGS's default:** it silently downscales anything wider than 1600 px. |
| Mid-training saves | 15 000 + 30 000 | A usable splat exists halfway through, and checkpoints allow post-hoc comparison. |
| QA metrics | PSNR / SSIM / LPIPS at test iterations | Objective quality comparison across runs. |

> **Note on regularizer flags:** earlier presets passed custom opacity/scale regularization flags (`--lambda_opacity_reg`, `--lambda_scale_reg`, …). The current FastGS build does not accept them and training fails on unknown flags — `backend/fix_fastgs_flags.py` exists to strip them from `tasks.py` if they reappear. Floater/needle suppression is instead handled by the cleaned-cloud promotion (Stage 5) and the post-training cleanup pass (Stage 7: `3dgsconverter --min_opacity 5 --sor_intensity 8`).

COLMAP is run with **exhaustive matching** — mandatory for unordered generated views (see below).

## Implementation Notes

1. **Equirectangular images fed directly to COLMAP fail.** Conversion to pinhole views (Stage 2) is mandatory — this is the whole reason the view-generation stage exists. GUI converters were dead ends (Pano2VR free tier caps at 4 photos); scripted `e2p` is the solution.
2. **15 perspective views beat 6 cubemap faces.** 5 yaw × 3 pitch at 90° FOV gives much better inter-view overlap for COLMAP than plain `e2c` cube faces — this switch materially improved registration.
3. **Exhaustive matching is mandatory for generated views.** Consecutive filenames are not spatially adjacent, so sequential matching finds far too few correspondences.
4. **Synthetic views get locked PINHOLE intrinsics.** Stage-2 crops have exactly known focal/centre, so COLMAP runs with fixed shared PINHOLE intrinsics (`all_synthetic=True`); real photos fall back to per-image SIMPLE_RADIAL estimation, and `image_undistorter` then produces genuinely undistorted images for FastGS (a no-op for the PINHOLE path).
5. **The mapper can produce multiple partial models.** The pipeline scores all `sparse/*` models, keeps the one with the most registered images, and moves it to `sparse/0` so downstream stages always read one canonical model.
6. **Cleaned-cloud promotion is load-bearing.** FastGS reads `sparse/0/points3D.ply` directly if it exists — the cleaning stage must overwrite that exact file, or FastGS silently trains on raw uncleaned points.
7. **More iterations do not improve quality.** ~30,000 iterations is optimal; beyond that the model overfits the training views.
8. **Watch FastGS's silent downscaling.** Anything wider than 1600 px is downscaled unless `-r` is set explicitly; resolution is therefore controlled deliberately (1400 px generation + explicit `-r`).
9. **Physical camera translation is required.** Rotation-only panorama capture cannot reconstruct geometry.
10. **COLMAP 3.13 renamed option groups:** `SiftExtraction`/`SiftMatching` → `FeatureExtraction`/`FeatureMatching`. Old scripts break quietly.
11. **pycolmap APIs vary by version.** Camera pose access (`cam_from_world` attribute vs callable) and post-processing helpers are resolved through fallback chains rather than assumed.
12. **`cv2.setNumThreads(0)` before Celery forks.** OpenCV's internal thread pool + Celery's prefork `os.fork()` produce intermittent broken-pipe errors; disabling cv2 threading is the standard fix.
13. **Raw 3DGS geometry is noisy and non-metric.** Object positions are triangulated from COLMAP poses and multi-view detections, never from splats; metric scale comes from the ArUco marker.
14. **Celery workers don't inherit CUDA visibility by default.** `tasks.py` injects `CUDA_HOME`/`PATH`/`LD_LIBRARY_PATH` for the FastGS subprocess; COLMAP runs CPU-mode by default (`colmap_use_gpu: false`) as the safe fallback. Kubernetes + NVIDIA container runtime is the production fix.
15. **`database.db` lives outside `images/`.** It fills progressively during a run; deleting it is the clean reset.
16. **SuperSplat + local `.ply`:** browsers block local file loads (CORS) — serve the folder with `python -m http.server 8000`.
17. **Rejected frames are logged, never silently deleted** — unreadable files and subsampled panoramas are tracked, so every processing decision stays traceable.

## Troubleshooting

| Symptom | Cause / Fix |
|---------|-------------|
| `ModuleNotFoundError: No module named 'app'` | uvicorn launched from repo root — run it from `backend/` |
| `Failed: FastGS exited with code 1 … ModuleNotFoundError: diff_gaussian_rasterization_fastgs` | FastGS rasterizer not built — reinstall FastGS inside the env with the CUDA toolkit available |
| FastGS fails on an unrecognised flag | The build doesn't support the custom regularizer flags — run `python backend/fix_fastgs_flags.py` |
| COLMAP registers very few images | Sequential matching used on generated views — the pipeline uses exhaustive matching; check custom scripts |
| Fewer images registered than uploaded | Normal — near-duplicate / low-parallax frames add nothing and are dropped during registration; large uploads are also evenly subsampled to the panorama cap |
| Mapper produced several `sparse/*` folders | Handled automatically — the largest model is promoted to `sparse/0` |
| Sparse cloud thin on plain walls | Textureless surfaces + blur — improve capture overlap, tighten the Stage 3 blur threshold |
| Splat full of floaters / spikes | Ensure the cleaning stage promoted `points3D.ply`, and rely on the Stage 7 `3dgsconverter` pass |
| Splat looks soft / detail lost | `-r 2` preset trades resolution for speed — rerun with `-r 1` for maximum fidelity |
| Celery worker trains on CPU | CUDA not visible inside worker processes — check the `FASTGS_ENV` paths in `tasks.py`; Kubernetes + NVIDIA runtime is the production fix |
| Measurements are in arbitrary units | No ArUco marker was visible in ≥2 views — reshoot with the marker placed, or treat dimensions as relative |
| Splat viewer crashes over ngrok | Free-tier bandwidth exhausted — use LAN/SSH or a duckdns subdomain |
| Report stage fails | WeasyPrint needs its native libs (pango/cairo) — install them in the environment |

## Validation

- **Indoor:** a full classroom from 70 panoramas → 1050 generated views; dense, well-registered COLMAP model and a clear photorealistic splat (visibly superior to a 444-view run of the same room).
- **Outdoor:** the south-eastern campus building reconstructed and explorable in the in-browser splat viewer.
  
<img width="1637" height="857" alt="image" src="https://github.com/user-attachments/assets/393f5c3f-61dc-4c80-8303-76be1803561d" />  <img width="1647" height="861" alt="image" src="https://github.com/user-attachments/assets/63d142c9-fc0e-428e-989a-7cf0f59cdf76" />


## Future Scope

Scenix is functional end-to-end today, but several parts of the pipeline are deliberately first-pass implementations with clear room to grow. This section lays out what's planned next and why it matters, for anyone evaluating where the project is headed.

- **Richer, more reliable evidence (object) detection** *(Stage 8)* — Detection currently runs on a fixed set of text prompts through OwlViT. Planned work: a configurable prompt set so a user can tell the system what kinds of objects to look for per scene, and an upgrade path to stronger open-vocabulary detectors (Grounding DINO / SAM 2) for higher recall and tighter boxes. Each detected object would also carry a supporting-view count — how many camera angles independently confirmed it — as a built-in confidence signal. This is the core research contribution of the project and the area with the most active development.

- **A fuller evidence report** *(Stage 12)* — The report currently outputs a v1 PDF with room dimensions and a flat object table. The next version would attach a photo crop and supporting-view thumbnails to every object, include capture metadata (date, camera, number of panoramas, marker used), embed a render of the reconstructed scene, and offer a DOCX export alongside the PDF. The goal is a report that can stand on its own as a shareable summary of a scene, not just a table.

- **A measurable mesh, alongside the splat** — A Gaussian splat looks great but isn't a solid, closed surface — it can't easily tell you "this is a wall" for measurement purposes. The plan is a dual-output architecture: keep the splat for visual walkthroughs, and separately generate a proper mesh (via 2D Gaussian Splatting or classical multi-view stereo) to serve as the actual measurement surface. A direct SuGaR integration was tried and dropped — it conflicted with the FastGS build and the meshes it produced weren't good enough to justify keeping it.

- **Clickable objects in the final viewer** *(Stage 11)* — The in-browser splat viewer currently shows the raw reconstruction. Planned: clickable, labelled bounding boxes over each detected object directly in the 3D view, with toggle-able layers (e.g. show/hide all "furniture", show/hide low-confidence detections), likely built on PlayCanvas or WebGPU for better performance at scale.

- **More flexible scale calibration** — Measurements currently rely on a single ArUco marker being visible in at least two views. Future versions would support multiple markers for cross-validation, and optionally a LiDAR reference for scenes where placing a printed marker isn't practical.

- **GPU workers that scale** — Right now the Celery worker runs on whichever machine it's launched on, with CUDA visibility handled by manually injected environment variables. The production target is Docker containers orchestrated by Kubernetes with the NVIDIA container runtime, so multiple reconstruction jobs can run in parallel across a GPU cluster instead of one machine.

- **Hardened preprocessing** *(Stage 3)* — Blur and duplicate filtering exist but are only partially tuned. Future work includes making the blur/duplicate thresholds configurable per capture device and surfacing rejected-frame reasons directly in the UI (the backend already logs them).

## Research Direction

Gaussian splatting alone is not novel. The contribution of this project is the **automatic 3D object layer built on top of it**:

> *Automatic 3D Object Detection and Classification in Gaussian-Splatted Scenes* — detecting objects in 2D imagery, triangulating them into 3D scene coordinates using recovered camera poses, classifying them into categories, and surfacing them as an interactive, measurable layer inside a walkable 3D rendering.

The system sits at the intersection of photogrammetry (COLMAP), neural scene representation (3DGS), computer vision (detection/segmentation), 3D object localisation (multi-view triangulation), and XR (the walkable end product). Because the reconstruction can be made metric and every processing step is logged, the same pipeline extends naturally to domains that demand defensible accuracy — facility documentation, insurance assessment, heritage preservation, and scene documentation among them.


## Acknowledgements

Developed as a Summer 2026 internship project at CAVE Labs, PESU. Built on the open-source work of [COLMAP](https://colmap.github.io/), [FastGS](https://github.com/fastgs/FastGS), [py360convert](https://github.com/sunset1995/py360convert), [SuperSplat](https://playcanvas.com/supersplat/editor), [3dgsconverter](https://github.com/francescofugazzi/3dgsconverter), [OwlViT](https://huggingface.co/docs/transformers/model_doc/owlvit), and [OpenCLIP](https://github.com/mlfoundations/open_clip).
