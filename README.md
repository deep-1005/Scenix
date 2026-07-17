# Scenix

**AI-Assisted 3D Scene Reconstruction using Gaussian Splatting and 3D Object Detection**

*A Summer 2026 research internship project — CAVE Labs, PESU*

Scenix is an end-to-end platform that converts raw 360° captures of any scene — rooms, buildings, labs, heritage sites, facilities — into a navigable, measurable, photorealistic 3D Gaussian splat, with automatically detected, classified, and labelled objects and an auto-generated PDF summary report.

Upload 360° panoramas of a scene; the system slices each one into pinhole perspective views, recovers camera poses and a sparse point cloud with COLMAP, statistically cleans the cloud, trains a Gaussian splat with FastGS, de-noises the splat, and serves the result through a web interface with per-stage progress tracking, resumable jobs, an interactive splat viewer, and an object-analytics table.

> **The core research contribution:** The proposed framework presents an end-to-end automated pipeline for 3D scene reconstruction from 360° panoramic images. Unlike conventional Gaussian Splatting workflows that require manual preprocessing and prepared datasets, the proposed system integrates automatic perspective-view generation, COLMAP-based Structure-from-Motion, adaptive point cloud cleaning using DBSCAN and RANSAC, FastGS-based Gaussian Splat training, and an interactive web-based visualization platform into a single unified framework. The pipeline further incorporates quality-enhancement techniques, including cleaned point cloud promotion and tuned densification, along with resumable execution and real-time progress monitoring, making it a scalable and deployment-ready solution for efficient 3D scene reconstruction.

<p align="center">
  <img src="./assets/ui-scene-dashboard.png" width="80%" alt="Scenix scene management dashboard" />
  <br/>
  <em>The Scenix web dashboard — scenes, per-stage progress, and storage usage at a glance</em>
</p>

---

## Table of Contents

- [Why Scenix](#why-scenix)
- [Key Features](#key-features)
- [Gallery](#gallery)
- [The 12-Stage Pipeline](#the-12-stage-pipeline)
- [Current Status](#current-status)
- [Architecture](#architecture)
- [Repository Layout](#repository-layout)
- [Tech Stack](#tech-stack)
- [Development Journey](#development-journey)
- [Tools We Evaluated (and Why We Moved On)](#tools-we-evaluated-and-why-we-moved-on)
- [Installation](#installation)
- [Running the Platform](#running-the-platform)
- [Usage](#usage)
- [Training Configuration](#training-configuration)
- [Implementation Notes](#implementation-notes)
- [Troubleshooting](#troubleshooting)
- [Validation](#validation)
- [Roadmap](#roadmap)
- [Research Framing](#research-framing)
- [Acknowledgements](#acknowledgements)

---

## Why Scenix

3D Gaussian Splatting produces stunning photorealistic scene renders, but on its own it's just a pretty picture: a raw splat has no object semantics, no metric scale, and no automated way to go from "here's a scene" to "here's a labelled inventory of what's in it, with dimensions." Every existing open-source workflow we found (Brush, Postshot, RealityScan, Nerfstudio, etc.) assumes a human is manually curating input images, running each stage by hand, and inspecting the output in a separate desktop tool.

Scenix's premise is that this entire chain — from a folder of 360° photos to a walkable, measurable, object-tagged 3D scene and a PDF report — can be automated, monitored, and made resumable, and that a genuinely useful "digital twin" pipeline needs an **object layer on top of the splat**, not just the splat itself. That object layer (open-vocabulary detection → multi-view 3D triangulation → clustering → classification → measurement) is the part of this project that doesn't already exist elsewhere, and it's what turns a pretty render into a usable record of a physical space — useful for facility documentation, insurance assessment, heritage preservation, and forensic-style scene capture.

## Key Features

- **One-click reconstruction** — upload 360° images and the full chain (perspective views → COLMAP → cleaning → FastGS → cleanup → analytics → report) runs as a single tracked Celery job with per-stage progress and live log tail.
- **Resumable jobs** — every stage has an on-disk completion check; a failed or stopped job can be resumed from the last completed stage instead of restarting from scratch.
- **360° panorama support** — automatic equirectangular → perspective (`e2p`) conversion: 15 pinhole views per panorama (5 yaw × 3 pitch, 90° FOV, 1400×1400). Raw Insta360 exports are handled directly; JPG, PNG, WebP, BMP, TIFF and iPhone HEIC/HEIF are all accepted (via pillow-heif).
- **Cleaned point cloud promotion** — RANSAC + DBSCAN + statistical outlier removal (Open3D, auto-tuned from average point spacing) runs on the sparse cloud *before* training, and the cleaned cloud is promoted into `sparse/0/points3D.ply` so FastGS provably trains on cleaned points.
- **Photorealistic Gaussian splatting** — FastGS training with a tuned densification preset and mid-training checkpoints (see [Training Configuration](#training-configuration)).
- **Splat cleanup** — floaters and low-opacity noise removed from the trained splat with `3dgsconverter` (opacity threshold + statistical outlier removal).
- **Object analytics** — open-vocabulary 2D detection (OwlViT) with prompts, multi-view triangulation of detections into 3D scene coordinates using recovered COLMAP poses, DBSCAN clustering into distinct objects, and OpenCLIP classification of per-item crops — surfaced as a tabulated Evidence view with dimensions and room dimensions.
- **Marker-based scale calibration** — an ArUco marker (4×4_50, default 10 cm) visible in ≥2 views is triangulated from real camera poses to convert COLMAP units to metres; without a marker, measurements fall back to relative units.
- **Automated PDF report** — Jinja2 + WeasyPrint render the room dimensions and object table to `report.pdf` as the final pipeline stage.
- **Interactive web viewers** — generated-view gallery, sparse point cloud with camera-position markers, Gaussian splat preview, and a full in-browser splat viewer (`@mkkellogg/gaussian-splats-3d` + Three.js), with `.ply` downloads at every step.
- **Scene management** — multiple scenes with progress bars, search, per-stage stop, resume, delete, and a storage-usage summary.
- **Desktop wrapper** — an Electron shell (`desktop/`) for running the UI as a native app.

## Gallery

<table>
<tr>
<td width="50%">
<img src="./assets/ui-pipeline-progress.png" width="100%" alt="Pipeline progress tracking UI" />
<p align="center"><em>Per-stage progress with live log tail</em></p>
</td>
<td width="50%">
<img src="./assets/ui-viewer-2.png" width="100%" alt="In-browser splat viewer" />
<p align="center"><em>In-browser Gaussian splat viewer</em></p>
</td>
</tr>
<tr>
<td width="50%">
<img src="./assets/colmap-sparse-room.png" width="100%" alt="COLMAP sparse reconstruction of a room" />
<p align="center"><em>COLMAP sparse point cloud with recovered camera poses, from 1050 generated perspective views</em></p>
</td>
<td width="50%">
<img src="./assets/gaussian-splat-supersplat.png" width="100%" alt="Trained Gaussian splat inspected in SuperSplat" />
<p align="center"><em>Trained Gaussian splat, inspected in SuperSplat</em></p>
</td>
</tr>
<tr>
<td width="50%">
<img src="./assets/meshlab-pointcloud.png" width="100%" alt="Point cloud viewed in MeshLab" />
<p align="center"><em>Cleaned point cloud, cross-checked in MeshLab</em></p>
</td>
<td width="50%">
<img src="./assets/object-detection.png" width="100%" alt="Early object detection experiments" />
<p align="center"><em>Early object-detection / classification experiments feeding the Evidence view</em></p>
</td>
</tr>
</table>

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
| 8 | **3D Object Detection** | Objects detected in 2D with text prompts, triangulated to 3D via COLMAP poses, clustered | OwlViT, DBSCAN, custom triangulation |
| 9 | **Classification & Tagging** | Detected items classified from crops, assigned IDs and confidence scores | OpenCLIP (ViT-B-32) |
| 10 | **Measurement** | Room dimensions + per-item dimensions; metric scale from an ArUco marker when present | OpenCV ArUco, Open3D, NumPy |
| 11 | **Final Scene Viewer** | Walkable scene; labelled object overlay in progress | Three.js + gaussian-splats-3d |
| 12 | **Automated Report** | PDF summary: room dimensions, object table with classifications and dimensions | Jinja2, WeasyPrint |

Stages 2, 8, 9, and 11 constitute the core research contribution of the project.

**Data flow principle:** the splat is for *viewing*; measurement relies on COLMAP poses and cleaned point clouds — plus scale calibration against a known reference before any distance is trusted.

## Current Status

| Stage | Status | Notes |
|-------|--------|-------|
| 1 — Capture & Ingestion | Complete | 360° upload, scene creation, broad format support (incl. HEIC) |
| 2 — View Generation | Complete | 15 perspective views per panorama via `e2p`; 70 panoramas → 1050 views |
| 3 — Preprocessing | Partially implemented | Blur filtering + video frame extraction workflows established |
| 4 — COLMAP | Complete | Exhaustive matching; validated at 1050+ images; multi-model + undistortion handling |
| 5 — Point-Cloud Cleaning | Complete | Auto-tuned RANSAC/DBSCAN/SOR with cleaned-cloud promotion |
| 6 — FastGS | Complete | Tuned densification preset, mid-training saves, live progress parsing |
| 7 — Splat Cleanup | Complete | 3dgsconverter opacity + SOR pass; SuperSplat manual path for inspection |
| 8 — 3D Object Detection | In progress | OwlViT detection + triangulation + clustering integrated; prompt set and robustness under active work |
| 9 — Classification | In progress | OpenCLIP crop classification wired; depends on detection crops |
| 10 — Measurement | Partially implemented | Room + item dimensions computed; ArUco scale calibration implemented (marker must be visible in ≥2 views) |
| 11 — Final Scene Viewer | Partially implemented | In-browser splat viewer working; clickable object overlay pending |
| 12 — Report | Complete (v1) | PDF generated as final stage (room dimensions + object table) |
| — SuGaR mesh | Removed | Trialled 15 July: conflicted with the FastGS build and produced weak meshes; meshing moved to the dual-output roadmap |

The pipeline has been validated end-to-end on our own indoor/outdoor captures and on external public datasets (Mendeley faculty-of-arts and parking-lot image sets) — see [Validation](#validation).

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
| AI / CV | OwlViT (open-vocabulary detection, via transformers), OpenCLIP ViT-B-32 (classification), scikit-learn DBSCAN; Grounding DINO / Ultralytics available in the environment for the detection upgrade path |
| Cleaning | Open3D (RANSAC / DBSCAN / SOR), auto-tuned parameters |
| Measurement | OpenCV ArUco (scale marker), Open3D, NumPy |
| Backend | Python, FastAPI, Celery, Redis, SQLAlchemy (SQLite default / PostgreSQL optional) |
| Frontend | React 18, Vite, Three.js, @mkkellogg/gaussian-splats-3d, axios |
| Desktop | Electron |
| Inspection | SuperSplat (browser splat cleanup), MeshLab |
| Reporting | Jinja2 + WeasyPrint (PDF) |
| Production target | Docker → Kubernetes + NVIDIA container runtime |

## Development Journey

Scenix was built over roughly four weeks as a Summer 2026 internship project, and the architecture reflects a lot of dead ends that shaped which decisions were deliberate rather than defaults. The short version: **most existing 3D reconstruction tools assume clean, pre-processed, non-panoramic input** — getting from "a folder of 360° photos" to "something COLMAP and a Gaussian splatter will accept" was the first real problem, and automating that conversion is the reason Stage 2 (view generation) exists at all.

**Week 1 — Foundations.** Started from photogrammetry and 3D Gaussian Splatting theory, then hands-on with COLMAP using the official sample dataset, cross-checked in MeshLab and Brush + SuperSplat. Early photo tests (a bottle shot on a phone, a book shot on the 360 camera) were used to compare COLMAP against RealityScan — RealityScan reconstructed faster and exported directly to `.obj`/Unity, while COLMAP's own exports needed more massaging, but COLMAP's pose/point-cloud outputs turned out to be the more useful foundation for later stages (dense metadata, full control over parameters).

**Week 2 — The panorama problem.** Feeding raw equirectangular 360° images straight into COLMAP or RealityScan simply didn't work — no pinhole camera model, no usable feature matching. Pano2VR's free tier only converts 4 photos at a time, ruling it out for anything at scale. The fix was writing a Python conversion script to slice each panorama into cubemap/perspective faces before reconstruction — the direct predecessor of today's Stage 2. In parallel, half a dozen commercial/alternative pipelines were trialled — Hunyuan, LeChatFeld Studio, Polycam, Luma AI, PostShot, Metashape, Meshroom, Nerfstudio, LixelStudio — to see whether any of them solved panorama ingestion or Gaussian splatting out of the box (see the [comparison table](#tools-we-evaluated-and-why-we-moved-on) below for why none of them stuck).

**Week 3 — Scaling up and automating.** Perspective-view generation moved from 6 cubemap faces to **15 views per panorama (5 yaw × 3 pitch, 90° FOV)** after testing showed it gave COLMAP meaningfully better inter-view overlap and registration. COLMAP was pushed from a few hundred images up to runs of 1000–5000+ generated views (hitting real infrastructure limits — a few systems ran out of storage entirely), while FastGS was integrated as the splat trainer of choice after Self-Organizing Gaussians (SOG) was evaluated and found not to be a drop-in replacement. A side-by-side FastGS run on the same room — 444 images vs. 1050 images — made the case for generating more perspective views per panorama rather than fewer: the 1050-view splat was visibly cleaner. This is also when the project moved from "run each stage by hand from the terminal" to "a real web application" — cubemap generation, COLMAP, and FastGS were wired into a single tracked pipeline with live progress percentages, and RANSAC + DBSCAN point-cloud cleaning (tuned with Optuna) was integrated.

**Week 4 — Hosting, hardening, and the object layer.** With the core pipeline working end-to-end, effort shifted to (a) making it reachable outside a single machine — SSH tunnelling turned out to be the reliable option, after LAN/nginx hosting and Docker both stalled and ngrok's free-tier bandwidth cap kept killing splat streaming mid-demo — and (b) the object-detection layer that differentiates Scenix from "just another Gaussian splatting demo." A SuGaR mesh integration was attempted and dropped (it conflicted with the FastGS build and its mesh quality didn't justify the added complexity), and the roadmap now separates meshing from splatting entirely (see [Roadmap](#roadmap)). Object detection, classification, measurement, and report generation were built out and validated against both original captures and public Mendeley datasets to confirm the pipeline generalizes.

## Tools We Evaluated (and Why We Moved On)

Reconstructing a scene from 360° photos touches several distinct problems — SfM/photogrammetry, Gaussian splat training, and viewing/export — and a lot of the early project time went into figuring out which tool actually solves which problem well, rather than assuming one tool does everything.

| Tool | Category | Verdict |
|------|----------|---------|
| **COLMAP** | Photogrammetry (SfM) | Adopted. Slower to set up than alternatives, but gives full parameter control, reliable camera poses, and a sparse point cloud that everything downstream (cleaning, training, measurement) depends on. |
| **RealityScan** | Photogrammetry | Faster than COLMAP and exports directly to `.obj`/Unity, but weaker for inside-out (room-interior) captures and doesn't expose the pose/point-cloud data the rest of the pipeline needs. Used only for early comparison tests. |
| **Pano2VR** | Equirect → cubemap conversion | Free tier caps at 4 images — unusable at any real scale. Replaced by a custom `e2p` Python conversion step (Stage 2). |
| **Hugin** | Panorama stitching | Evaluated for the same conversion problem; not adopted into the pipeline. |
| **Brush** | Gaussian splatting (browser-based) | Accepts 360° images fairly directly and gave promising early results, but wasn't practical to fully automate/generate at scale within the project's constraints. |
| **FastGS** | Gaussian splatting | Adopted as the primary trainer — open, scriptable, and tunable (see [Training Configuration](#training-configuration)). |
| **Self-Organizing Gaussians (SOG)** | Gaussian splatting | Evaluated as a possible alternative/replacement for FastGS; concluded it isn't a drop-in substitute for this pipeline's needs. |
| **Hunyuan / LeChatFeld Studio** | Gaussian splatting (commercial) | Paid, closed pipelines; not adopted. |
| **Polycam / Luma AI** | 3D capture apps | Produce 3D models from 2D photos, not true Gaussian splats — didn't fit the project's requirements. |
| **PostShot** | Gaussian splatting | Worked well, but exports its own `.psht` format rather than standard `.ply`, breaking compatibility with the rest of the toolchain. |
| **Metashape / Meshroom** | Photogrammetry | Evaluated as COLMAP alternatives; not adopted. |
| **Nerfstudio** | NeRF / splatting framework | Tried across multiple environments (local PCs, Google Colab) and repeatedly hit storage/compute limits; not adopted. |
| **LixelStudio / Splatforge** | End-to-end splatting UIs | Promising interfaces, but COLMAP integration issues in Splatforge and unresolved setup friction in LixelStudio kept both out of the final pipeline. |
| **SuGaR** | Gaussian-to-mesh conversion | Trialled for a mesh export layer; conflicted with the FastGS build and produced weak meshes. Removed — meshing is now planned as a separate dual-output path (see [Roadmap](#roadmap)). |
| **SuperSplat** | Splat inspection/cleanup (browser) | Kept as a manual inspection tool for `.ply` outputs alongside the automated Stage 7 cleanup — useful for visually verifying cleanup results. |
| **MeshLab** | Point cloud/mesh inspection | Kept as a cross-check tool for point clouds outside the main web UI. |

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

### Remote / LAN access

<p align="center">
  <img src="./assets/remote-access-ssh.png" width="70%" alt="Remote access over SSH" />
  <br/>
  <em>Running the pipeline on the lab's ISFCR machine and reaching it remotely over SSH</em>
</p>

Several hosting approaches were tried before settling on SSH tunnelling:

- **SSH tunnel** (recommended, what we actually use): `ssh -L 5173:localhost:5173 -L 8000:localhost:8000 user@<host>`
- **LAN + nginx** — attempted on the campus network but never got reliably working.
- **Docker** — attempted for a portable deployment; hit persistent build errors and was shelved.
- **ngrok** — works, but free-tier bandwidth is exhausted quickly by splat streaming (repeatedly crashed the splat viewer mid-demo); fine for a quick one-off share, not for a working session.
- **duckdns.org** — recommended as a free subdomain option for LAN-hosted demos, as a lighter alternative to ngrok.

## Usage

1. **Create a scene** — enter a name and drop the 360° equirectangular exports (Insta360 Studio: use the *360 photos* export, not reframed DNG). JPG/PNG/WebP/BMP/TIFF/HEIC accepted; up to 100 panoramas per scene (larger sets are evenly subsampled).
2. **Start reconstruction** — the stage tracker runs Views → COLMAP → Cleaning → Gaussian → Cleanup → Detection → Classify → Measure → Report, with live progress and log tail per stage.
3. **Inspect results** in the tabs:
   - **Cubemaps** — the generated perspective views (15 per panorama), downloadable
   - **Point cloud** — sparse reconstruction with camera-position markers, `.ply` download
   - **Gaussian splat** — splat-centers preview, trained `.ply` download (open in SuperSplat for full-quality inspection)
   - **Splat viewer** — full photorealistic reconstruction, explorable in the browser
   - **Evidence** — detected/classified items with confidence and dimensions, plus room dimensions
4. **Manage scenes** — every scene keeps its progress; failed or stopped jobs can be **resumed** from the last completed stage; scenes can be searched, stopped, and deleted from the sidebar, and disk usage is visible in the storage summary.

### Capture Protocol (Stage 1)

**The camera must physically move between shots.** Rotation-only capture gives zero depth and reconstruction *will* fail regardless of downstream settings. Capture 360° panoramas from many standing positions across the scene with generous overlap; ~70 positions reconstructed a full classroom well. Avoid motion blur — motion-blurred frames significantly degrade COLMAP feature matching. For metric measurements, place a printed ArUco marker (4×4_50 dictionary, known size — default 10 cm) where at least two capture positions can see it.

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
- **External datasets:** public Mendeley image sets (a faculty-of-arts building and a parking lot) reconstructed well end-to-end through the platform with no dataset-specific tuning — confirming the pipeline generalises beyond our own captures.

## Roadmap

- **Mesh layer via dual-output architecture:** 3DGS for visualization + 2DGS or MVS mesh as the measurement substrate. (A direct SuGaR integration was trialled and removed — it conflicted with the FastGS build and its meshes didn't justify the complexity.)
- **Detection hardening (Stage 8):** configurable prompt sets, stronger open-vocabulary models (Grounding DINO / SAM 2 upgrade path), per-object records with supporting-view counts — the core research contribution.
- **Final Scene viewer (Stage 11):** clickable labelled object boxes and layer toggles over the splat (PlayCanvas / WebGPU target).
- **Report v2 (Stage 12):** richer PDF/DOCX export with capture metadata, renders, and the full processing log.
- **Scale calibration extensions:** LiDAR / multi-marker references beyond the single ArUco marker.
- **GPU workers at scale:** Docker → Kubernetes with NVIDIA container runtime to give Celery workers reliable CUDA visibility.

## Research Framing

Gaussian splatting alone is not novel. The contribution of this project is the **automatic 3D object layer built on top of it**:

> *Automatic 3D Object Detection and Classification in Gaussian-Splatted Scenes* — detecting objects in 2D imagery, triangulating them into 3D scene coordinates using recovered camera poses, classifying them into categories, and surfacing them as an interactive, measurable layer inside a walkable 3D rendering.

The system sits at the intersection of photogrammetry (COLMAP), neural scene representation (3DGS), computer vision (detection/segmentation), 3D object localisation (multi-view triangulation), and XR (the walkable end product). Because the reconstruction can be made metric and every processing step is logged, the same pipeline extends naturally to domains that demand defensible accuracy — facility documentation, insurance assessment, heritage preservation, and scene documentation among them.

## Acknowledgements

Developed as a Summer 2026 internship project at CAVE Labs, PESU. Built on the open-source work of [COLMAP](https://colmap.github.io/), [FastGS](https://github.com/fastgs/FastGS), [py360convert](https://github.com/sunset1995/py360convert), [SuperSplat](https://playcanvas.com/supersplat/editor), [3dgsconverter](https://github.com/francescofugazzi/3dgsconverter), [OwlViT](https://huggingface.co/docs/transformers/model_doc/owlvit), and [OpenCLIP](https://github.com/mlfoundations/open_clip).
