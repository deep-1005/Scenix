# Forensic Digital Twin

Crime-scene 3D reconstruction from 360° images: upload Insta360 equirectangular
stills, and the app automatically generates cube faces, runs COLMAP
Structure-from-Motion, and produces a viewable point cloud (with Gaussian
Splatting and evidence detection as later stages). Runs entirely in user space —
no Docker, no sudo.

## What works today

- Stage 2 — Cubemaps: equirectangular 360° → 6 perspective faces (py360convert)
- Stage 3 — COLMAP: camera poses + sparse point cloud, exported to PLY
- UI: upload, live progress, cubemap gallery, interactive 3D point-cloud viewer
  (Three.js) with camera-position markers, PLY download
- Remaining stages (Gaussian Splatting, cleanup, mesh, evidence detection,
  classification, measurement, reporting) are stubbed and run instantly.

## Architecture

```
Browser/Electron UI  ──>  FastAPI  ──>  Redis queue  ──>  Celery worker (pipeline)
       ^                     |                                   |
       └──── polls status ───┘            Postgres (jobs)  <──────┘
                                          storage/outputs (images, ply)
```

## Prerequisites (one-time)

You need conda. Everything else installs into a conda env — no sudo.

```bash
# 1) create env + python deps
conda create -n forensic python=3.11 -y
conda activate forensic
conda install -c conda-forge postgresql redis-server colmap nodejs=22.13 -y
pip install -r backend/requirements.txt

# 2) initialize the local database (one time)
bash services.sh init
```

`services.sh init` assumes the project lives at
`~/Desktop/360_image_processing/DigitalTwin`. If it's elsewhere, edit the `ROOT`
line at the top of `services.sh` and `run.sh`.

```bash
# 3) install frontend + desktop deps
cd frontend && npm install && cd ..
cd desktop  && npm install && cd ..
```

## Running (every session)

Start the data services once:

```bash
conda activate forensic
bash services.sh start
bash services.sh status      # expect: "postgres ok" and "PONG"
```

Then three terminals (each: `conda activate forensic`):

```bash
# Terminal 1 — API
bash run.sh api

# Terminal 2 — worker
bash run.sh worker

# Terminal 3 — frontend (browser app at http://localhost:5173)
bash run.sh frontend
```

For the desktop window instead of the browser, add a 4th terminal:

```bash
cd desktop && npm start
```

## Using it

1. Open http://localhost:5173 (or the desktop window).
2. Enter a scene name, drop in several 360° equirectangular stills.
   IMPORTANT: capture from several positions — walk the camera around the room.
   Rotation-only panoramas cannot reconstruct depth and COLMAP will fail.
3. Click "Start reconstruction" and watch the progress bar.
4. When COLMAP finishes, open the "Point cloud" tab to view the 3D result
   (orange dots = where each photo was taken) and download the PLY.

## GPU vs CPU for COLMAP

COLMAP runs on CPU by default (`colmap_use_gpu = False` in
`backend/app/core/config.py`) because the worker process doesn't always see the
GPU. It works everywhere this way, just slower. If your COLMAP build sees CUDA
from the worker, set `colmap_use_gpu = True` for a big speedup.

## Project layout

```
DigitalTwin/
├── services.sh           # start/stop Postgres + Redis
├── run.sh                # launch api / worker / frontend
├── backend/
│   ├── requirements.txt
│   └── app/
│       ├── main.py             # FastAPI: jobs, images, ply endpoints
│       ├── core/config.py      # settings (db, redis, gpu flag)
│       ├── models/db.py        # Job table
│       ├── workers/
│       │   ├── celery_app.py
│       │   └── tasks.py        # the pipeline orchestrator
│       └── pipeline/
│           ├── cubemaps.py     # Stage 2
│           └── colmap_sfm.py   # Stage 3
├── frontend/
│   └── src/
│       ├── App.jsx
│       ├── api.js
│       └── components/
│           ├── CubemapGallery.jsx
│           └── PointCloudViewer.jsx   # Three.js PLY viewer
├── desktop/              # Electron wrapper
└── storage/             # uploads + outputs (gitignored)
```

## Adding the next stage

Each pipeline stage is one function in `backend/app/pipeline/` called from
`backend/app/workers/tasks.py`, replacing one stubbed stage. Next up:
Gaussian Splatting (FastGS) consuming `storage/outputs/<job>/sparse/0`.
