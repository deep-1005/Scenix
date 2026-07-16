# Scenix

**AI-Assisted 3D Scene Reconstruction using Gaussian Splatting and 3D Object Detection**

Scenix is an end-to-end platform that converts raw 360° captures of any scene — rooms, buildings, labs, heritage sites, facilities — into a navigable, measurable, photorealistic 3D gaussian splat, with automatically detected, classified, and labelled objects and an auto-generated summary report.

Upload 360° panoramas of a scene; the system slices them into pinhole-camera views, recovers camera poses and a sparse point cloud with COLMAP, trains a Gaussian splat with FastGS, cleans it, and serves the result through a web interface with per-stage progress tracking, an interactive splat viewer, and an object-analytics table.

> **The core research contribution:** The proposed framework presents an end-to-end automated pipeline for 3D scene reconstruction from 360° panoramic images. Unlike conventional Gaussian Splatting workflows that require manual preprocessing and prepared datasets, the proposed system integrates automatic cubemap generation, COLMAP-based Structure-from-Motion, adaptive point cloud cleaning using DBSCAN and RANSAC, FastGS-based Gaussian Splat training, and an interactive web-based visualization platform into a single unified framework. The pipeline further incorporates quality-enhancement techniques, including cleaned point cloud promotion and optimized Gaussian regularization, along with resumable execution and real-time progress monitoring, making it a scalable and deployment-ready solution for efficient 3D scene reconstruction.

---

## Table of Contents

- [Key Features](#key-features)
- [The 12-Stage Pipeline](#the-12-stage-pipeline)
- [Current Status](#current-status)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Installation](#installation)
- [Running the Platform](#running-the-platform)
- [Usage](#usage)
- [Training Configuration](#training-configuration)
- [Implementation Notes](#implementation-notes)
- [Troubleshooting](#troubleshooting)
- [Roadmap](#roadmap)
- [Research Framing](#research-framing)

---

## Key Features

- **One-click reconstruction** — upload 360° images and the full chain (cubemaps → COLMAP → FastGS → viewer) runs as a single tracked job with per-stage progress.
- **360° panorama support** — automatic equirectangular → cubemap (`e2c`) and perspective (`e2p`) conversion; raw Insta360 exports are handled directly.
- **Photorealistic Gaussian splatting** — FastGS training with quality-preserving defaults (full input resolution, tuned iteration count, floater/needle-artifact regularization).
- **Interactive web viewers** — cubemap gallery, sparse point cloud with camera-position markers, Gaussian splat preview, and a full in-browser splat viewer (Three.js), with `.ply` downloads at every step.
- **Point-cloud cleanup** — RANSAC + DBSCAN outlier removal with Optuna-tuned parameters.
- **Object analytics** — object detection and classification over the scene, producing a tabulated view with per-item dimensions and computed room dimensions.
- **Quality metrics** — PSNR / SSIM / LPIPS logged via TensorBoard for objective reconstruction-quality comparison across runs.
- **Scene management** — multiple scenes with progress bars, search, and stop controls per stage.

## The 12-Stage Pipeline

| # | Stage | What happens | Core tech |
|---|-------|--------------|-----------|
| 1 | **Capture & Ingestion** | 360° photos/video + metadata captured on site and uploaded | Insta360 X3/X4, FastAPI |
| 2 | **Image Generation (Cubemaps)** | Each panorama sliced into flat perspective images COLMAP can use | py360convert (`e2c`/`e2p`), OpenCV |
| 3 | **AI Preprocessing & QC** | Blurry / duplicate / low-quality frames removed (rejections logged) | OpenCV Laplacian, perceptual hash, SAM 2 |
| 4 | **Photogrammetry** | Camera poses + sparse 3D point cloud recovered | COLMAP / pycolmap (+ SuperPoint/SuperGlue) |
| 5 | **Gaussian Splatting** | Photorealistic 3D model trained from `sparse/0` | FastGS, PyTorch, CUDA |
| 6 | **AI Splat Cleanup** | Floating noise / stray splat clusters auto-removed | DBSCAN / Open3D, SuperSplat |
| 7 | **Mesh Conversion** | Splat → solid surface so the scene is *measurable* | SuGaR, Trimesh |
| 8 | **3D Object Detection** | Objects detected in 2D, triangulated to 3D coordinates via COLMAP poses | Grounding DINO, SAM 2, custom triangulation |
| 9 | **Classification & Tagging** | Detected items categorised and assigned IDs and confidence scores | Rule engine, PostgreSQL |
| 10 | **Measurement** | Distances, areas, room dimensions computed automatically | Trimesh + NumPy on scaled mesh |
| 11 | **Final Scene Viewer** | Walkable scene with clickable, labelled object boxes | Three.js (PlayCanvas/WebGPU target) |
| 12 | **Automated Report** | Summary document: detected objects, measurements, capture metadata | python-docx / ReportLab, Jinja2 |

Stages 2, 8, 9, and 11 constitute the core research contribution of the project.

**Data flow principle:** the splat is for *viewing*; the mesh is for *measuring*. Reliable measurements need both — plus scale calibration against a known reference before any distance is trusted.

## Current Status

| Stage | Status | Notes |
|-------|--------|-------|
| 1 — Capture & Ingestion | Complete | 360° upload, scene creation |
| 2 — Cubemaps | Complete | 420 faces from 70 panoramas via py360convert |
| 3 — Preprocessing | Partially implemented | Blur filtering + video frame extraction workflows established |
| 4 — COLMAP | Complete | Exhaustive matching; validated at 1050+ images |
| 5 — FastGS | Complete | Custom regularizers, QA metrics, tuned training preset |
| 6 — Splat Cleanup | Partially implemented | RANSAC/DBSCAN + Optuna implemented; SuperSplat manual path |
| 7 — SuGaR Mesh | Planned | Surface-aligned mesh for metric measurement |
| 8 — 3D Object Detection | In progress | 2D detection integrated; triangulation is the active research task |
| 9 — Classification | In progress | Detected items tabulated with labels, confidence, dimensions |
| 10 — Measurement | Partially implemented | Room dimensions computed (COLMAP units); scale calibration pending |
| 11 — Final Scene Viewer | Partially implemented | In-browser splat viewer working; object overlay pending |
| 12 — Report | Planned | Automated DOCX/PDF generation |

## Architecture

```
                        ┌─────────────────────────────┐
                        │   React + Vite + TypeScript │
                        │   Three.js viewers (5173)   │
                        └──────────────┬──────────────┘
                                       │ REST
                        ┌──────────────▼──────────────┐
                        │      FastAPI  (8000)        │
                        │      backend/app/main.py    │
                        └──────┬───────────────┬──────┘
                               │               │
                     job queue │               │ scene metadata
                        ┌──────▼──────┐  ┌─────▼────────┐
                        │    Redis    │  │  PostgreSQL  │
                        └──────┬──────┘  └──────────────┘
                               │
                        ┌──────▼──────────────────────┐
                        │  Celery workers (tasks.py)  │
                        │  cubemaps → COLMAP → FastGS │
                        │  → cleanup → detect → …     │
                        └─────────────────────────────┘
```

Long-running reconstruction jobs (COLMAP and FastGS runs take minutes to hours) execute asynchronously in Celery workers so the API and UI stay responsive; every stage reports progress back to the scene record.

**Standard scene folder layout** (enforced — downstream tools depend on it):

```
my_scene/
├── images/          # perspective frames from Stage 2
├── sparse/0/        # cameras.bin, images.bin, points3D.bin
└── database.db      # kept OUT of images/ — delete to reset COLMAP
```

Only `sparse/0/` matters downstream; the COLMAP `dense/` output is not used by FastGS.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Capture | Insta360 360° camera, Insta360 Studio |
| Conversion | py360convert (`e2c`, `e2p`), OpenCV, NumPy |
| Photogrammetry | COLMAP 3.13 (conda-forge, CUDA build), pycolmap, SuperPoint/SuperGlue |
| Splatting | FastGS (primary), SuGaR (mesh target), 3DGS (under evaluation) |
| AI / CV | Grounding DINO (open-vocabulary detection), SAM 2 (segmentation) |
| Backend | Python, FastAPI, Celery, Redis, PostgreSQL |
| Frontend | React, Vite, TypeScript, Three.js |
| Inspection | SuperSplat (browser splat cleanup), MeshLab |
| Reporting | python-docx / Node `docx` |
| Production target | Docker → Kubernetes + NVIDIA container runtime |

## Installation

The platform runs entirely user-space via conda — **no sudo required**. Developed on Ubuntu 24.04 with an NVIDIA GPU (CUDA required for COLMAP GPU features and FastGS training).

### 1. Clone

```bash
git clone https://github.com/deep-1005/Scenix.git
cd Scenix
```

### 2. Create the conda environment

```bash
conda create -n forensic python=3.10 -y
conda activate forensic

# COLMAP (CUDA build) + core services from conda-forge
conda install -c conda-forge colmap pycolmap postgresql redis-server -y

# Python dependencies
pip install -r backend/requirements.txt
# (fastapi, uvicorn, celery, redis, psycopg2, py360convert, opencv-python,
#  numpy, open3d, optuna, torch — see requirements.txt for pinned versions)
```

### 3. FastGS

```bash
git clone https://github.com/fastgs/FastGS.git
cd FastGS
pip install -e .          # builds diff_gaussian_rasterization_fastgs (needs CUDA toolkit)
cd ..
```

If training later fails with `ModuleNotFoundError: No module named 'diff_gaussian_rasterization_fastgs'`, the rasterizer extension didn't build — re-run the install inside the env with CUDA visible.

### 4. Initialise services

```bash
# PostgreSQL (user-space data directory)
initdb -D ~/pgdata
pg_ctl -D ~/pgdata -l ~/pgdata/logfile start
createdb scenix

# Redis
redis-server --daemonize yes
```

### 5. Frontend

```bash
cd frontend
npm install
```

## Running the Platform

Verify services first:

```bash
psql -c "SELECT 1"     # PostgreSQL up
redis-cli ping         # → PONG
```

Then open **three terminals**, each with `conda activate forensic`:

```bash
# Terminal 1 — API server
cd backend && uvicorn app.main:app --reload --port 8000

# Terminal 2 — Celery worker (runs the pipeline)
cd backend && celery -A app.workers.tasks worker --loglevel=info

# Terminal 3 — Frontend dev server
cd frontend && npm run dev
```

Open **http://localhost:5173**. The header shows `API connected` when the frontend can reach the backend.

> **Note:** Run uvicorn from `backend/`, not the repo root — `ModuleNotFoundError: No module named 'app'` always means it was launched from the wrong directory.

### Remote / LAN access

- **SSH tunnel** (recommended): `ssh -L 5173:localhost:5173 -L 8000:localhost:8000 user@<host>`
- **ngrok** works but free-tier bandwidth is exhausted quickly by splat streaming; prefer LAN hosting or a duckdns.org subdomain for demos.

## Usage

1. **Create a scene** — enter a name and drop the 360° equirectangular `.jpg` exports (Insta360 Studio: use the *360 photos* export, not reframed DNG).
2. **Start reconstruction** — the stage tracker runs Cubemaps → COLMAP → Cleaning → Gaussian → Cleanup → Mesh → Detection → Classify → Measure → Report.
3. **Inspect results** in the tabs:
   - **Cubemaps** — generated faces (6 per panorama), downloadable
   - **Point cloud** — sparse reconstruction with orange camera-position markers, `.ply` download
   - **Gaussian splat** — splat-centers preview, trained `.ply` download (open in SuperSplat for full-quality inspection)
   - **Splat viewer** — full photorealistic reconstruction, explorable in the browser
   - **Objects** — detected/classified items with confidence and dimensions, plus room dimensions
4. Every scene keeps its progress; jobs can be stopped per stage and scenes can be searched from the sidebar.

### Capture Protocol (Stage 1)

**The camera must physically move between shots.** Rotation-only capture gives zero depth and reconstruction *will* fail regardless of downstream settings. Capture 360° panoramas from many standing positions across the scene with generous overlap; ~70 positions reconstructed a full classroom well. Avoid motion blur — motion-blurred frames significantly degrade COLMAP feature matching.

## Training Configuration

The training preset (`train_forensic.sh`) wraps FastGS with defaults chosen for maximum-fidelity output:

```bash
python train.py -s <scene_path> \
    --iterations 30000 \
    -r 1 \
    --opacity_entropy_weight <w1> \      # suppresses floater artifacts
    --scale_anisotropy_weight <w2>       # suppresses needle/spike splats
```

| Setting | Value | Why |
|---------|-------|-----|
| `-r 1` | **always** | FastGS silently downscales inputs wider than 1600 px, throwing away detail. Full input resolution is enforced end-to-end. |
| `--iterations` | ~30 000 | Beyond ~30k FastGS overfits the training views rather than improving reconstruction. |
| Opacity entropy loss | custom | Drives ambiguous low-opacity Gaussians to transparent → fewer floaters. |
| Scale anisotropy loss | custom | Penalises extreme axis ratios → fewer needle/spike splats. |
| QA metrics | PSNR / SSIM / LPIPS | Logged to TensorBoard for objective quality comparison across runs. |

COLMAP is run with **exhaustive matching** — mandatory for unordered cubemap faces (see below).

## Implementation Notes

1. **Equirectangular images fed directly to COLMAP fail.** Conversion to pinhole views (Stage 2) is mandatory — this is the whole reason the cubemap stage exists.
2. **Exhaustive matching is mandatory for cubemap faces.** Consecutive filenames are not spatially adjacent, so sequential matching finds far too few correspondences.
3. **Always pass `-r 1`.** FastGS downscales anything >1600 px wide *silently*, which quietly destroys the detail you captured.
4. **More iterations do not improve quality.** Approximately 30,000 iterations is optimal; beyond that the model overfits the training views.
5. **Physical camera translation is required.** Rotation-only panorama capture cannot reconstruct geometry.
6. **COLMAP 3.13 renamed option groups:** `SiftExtraction`/`SiftMatching` → `FeatureExtraction`/`FeatureMatching`. Old scripts break quietly.
7. **pycolmap camera centers vary by version.** Use a fallback chain: `project_center()` → `projection_center()` → manual `-R.T @ t`.
8. **Raw 3DGS geometry is noisy and non-metric.** Triangulate object positions from COLMAP poses and points, not from splats; measure on the SuGaR mesh, view on the splat.
9. **`database.db` lives outside `images/`.** It fills progressively during a run; deleting it is the clean reset.
10. **SuperSplat + local `.ply`:** browsers block local file loads (CORS) — serve the folder with `python -m http.server 8000`.
11. **Rejected frames are logged, never silently deleted** — every processing decision stays traceable.

## Troubleshooting

| Symptom | Cause / Fix |
|---------|-------------|
| `ModuleNotFoundError: No module named 'app'` | uvicorn launched from repo root — run it from `backend/` |
| `ModuleNotFoundError: diff_gaussian_rasterization_fastgs` | FastGS rasterizer not built — reinstall FastGS inside the env with CUDA toolkit available |
| COLMAP registers very few images | Sequential matching used on cubemap faces — switch to exhaustive matching |
| Sparse cloud thin on plain walls | Textureless surfaces + blur — improve capture overlap, tighten Stage 3 blur threshold |
| Splat full of floaters / spikes | Use the training preset (regularizers) + Stage 6 DBSCAN cleanup |
| Splat looks soft / detail lost | `-r 1` missing — inputs were silently downscaled |
| Celery worker trains on CPU | CUDA not visible inside worker processes (known issue) — Kubernetes + NVIDIA container runtime is the production fix |
| Splat viewer crashes over ngrok | Free-tier bandwidth exhausted — use LAN/SSH or a duckdns subdomain |

## Roadmap

- **SuGaR integration (Stages 6–7):** surface-aligned mesh from the cleaned splat for metrically accurate geometry
- **Dual-output architecture:** 3DGS for visualization + 2DGS or MVS mesh as the measurement substrate
- **2D→3D object triangulation (Stage 8):** multi-view matching + ray intersection using COLMAP poses — the core research contribution
- **Object records:** per-item ID, category, 3D position, supporting-view count, confidence
- **Scale calibration:** anchor to a known in-scene reference (scale marker / LiDAR) before any measurement is trusted
- **Final Scene viewer (Stage 11):** clickable labelled object boxes, layer toggles (PlayCanvas / WebGPU)
- **Automated report (Stage 12):** DOCX/PDF export with object list, measurements, capture metadata, and full processing log
- **GPU workers at scale:** Docker → Kubernetes with NVIDIA container runtime

## Research Framing

Gaussian splatting alone is not novel. The contribution of this project is the **automatic 3D object layer built on top of it**:

> *Automatic 3D Object Detection and Classification in Gaussian-Splatted Scenes* — detecting objects in 2D imagery, triangulating them into 3D scene coordinates using recovered camera poses, classifying them into categories, and surfacing them as an interactive, measurable layer inside a walkable 3D rendering.

The system sits at the intersection of photogrammetry (COLMAP), neural scene representation (3DGS), computer vision (detection/segmentation), 3D object localisation (multi-view triangulation), and XR (the walkable end product). Because the reconstruction is metric and every processing step is logged, the same pipeline extends naturally to domains that demand defensible accuracy — facility documentation, insurance assessment, heritage preservation, and scene documentation among them.

## Acknowledgements

Developed as a Summer 2026 internship project at CAVE Labs, PESU. Built on the open-source work of [COLMAP](https://colmap.github.io/), [FastGS](https://github.com/fastgs/FastGS), [py360convert](https://github.com/sunset1995/py360convert), [SuperSplat](https://playcanvas.com/supersplat/editor), [SuGaR](https://anttwo.github.io/sugar/) and [SAM].
