#!/usr/bin/env bash
# Convenience launcher. Run each block in its OWN terminal (3 terminals),
# OR run this once to launch all three in the background.
# All assume: conda activate forensic
ROOT="$HOME/Desktop/360_image_processing/DigitalTwin"

case "$1" in
  api)
    cd "$ROOT/backend" && uvicorn app.main:app --reload --port 8000 ;;
  worker)
    cd "$ROOT/backend" && celery -A app.workers.tasks worker --loglevel=info ;;
  frontend)
    cd "$ROOT/frontend" && npm run dev ;;
  *)
    echo "usage: bash run.sh {api|worker|frontend}"
    echo "Open three terminals, run one in each (after: conda activate forensic)." ;;
esac
