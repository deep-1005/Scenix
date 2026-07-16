import os
import subprocess
from pathlib import Path

# [FORENSIC FIX] This module used to keep its own copy of the FastGS
# command-line flags in `_build_cmd`, separate from tasks.py's inline
# `cmd` list — and the two had already drifted apart (this file had
# the anti-needle-splat regularization flags, tasks.py didn't). Since
# tasks.py is what the live Celery pipeline actually runs, it's now the
# single source of truth: `_build_fastgs_cmd` lives there and this file
# just imports it, so there is exactly one place to edit going forward.
from app.workers.tasks import _build_fastgs_cmd, FASTGS_DIR as _TASKS_FASTGS_DIR


def _validate_and_setup(scene_dir: str, work_dir: str):
    """Shared validation + path resolution for both entry points below."""
    scene_dir = Path(scene_dir)
    work_dir = Path(work_dir)

    images_dir = scene_dir / "images"
    sparse_dir = scene_dir / "sparse" / "0"
    output_dir = work_dir / "gaussian_output"

    if not images_dir.exists():
        raise FileNotFoundError(f"images/ not found at {images_dir}")

    for required in ["cameras.bin", "images.bin", "points3D.bin"]:
        if not (sparse_dir / required).exists():
            txt = required.replace(".bin", ".txt")
            if not (sparse_dir / txt).exists():
                raise FileNotFoundError(
                    f"COLMAP output missing: {required} (and no .txt fallback) in {sparse_dir}"
                )

    output_dir.mkdir(parents=True, exist_ok=True)

    fastgs_dir = Path(os.environ.get("FASTGS_DIR", _TASKS_FASTGS_DIR))
    train_script = fastgs_dir / "train.py"

    if not train_script.exists():
        raise FileNotFoundError(
            f"FastGS train.py not found at {train_script}. "
            "Set FASTGS_DIR env var or update the path in fastgs.py"
        )

    return scene_dir, work_dir, output_dir, fastgs_dir, train_script


def run_fastgs(scene_dir: str, work_dir: str) -> str:
    """
    Run FastGS gaussian splatting on a scene that already has COLMAP output,
    blocking until it finishes. Returns the path to the trained PLY.

    [FORENSIC FIX] This used to be a single function with an `if stream`
    branch — but because the function body contained a `yield` anywhere
    in it (in the streaming branch), Python made the ENTIRE function a
    generator, always, regardless of the stream flag. Calling
    run_fastgs(..., stream=False) never executed a single line of code —
    it just returned a generator object instantly, with FastGS silently
    never running. Split into two real functions instead: this one for
    blocking calls, run_fastgs_streaming() below for line-by-line output.

    Expects:
        scene_dir/images/       - cubemap tile images
        scene_dir/sparse/0/     - cameras.bin, images.bin, points3D.bin

    Produces:
        work_dir/gaussian_output/point_cloud/iteration_30000/point_cloud.ply
    """
    scene_dir, work_dir, output_dir, fastgs_dir, train_script = _validate_and_setup(scene_dir, work_dir)
    cmd = _build_fastgs_cmd(str(scene_dir), str(output_dir))

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(fastgs_dir),
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"FastGS failed:\n{result.stdout}\nSTDERR:\n{result.stderr[-2000:]}"
        )

    ply_path = output_dir / "point_cloud" / "iteration_30000" / "point_cloud.ply"
    if not ply_path.exists():
        raise RuntimeError(
            f"FastGS exited successfully but no PLY found at {ply_path}. "
            f"Last stdout: {result.stdout[-500:]}"
        )
    return str(ply_path)


def run_fastgs_streaming(scene_dir: str, work_dir: str):
    """
    Same as run_fastgs(), but yields output line by line as FastGS trains —
    for real-time progress in the UI. This is a real generator (correctly,
    this time) — callers must iterate it, e.g.:

        for line in run_fastgs_streaming(scene_dir, work_dir):
            print(line)

    Note this does NOT return the final PLY path via `return` — generators
    can't mix `yield` and a meaningful `return <value>` the way a normal
    function does. If the caller needs the final path, check for it
    directly after the loop completes:

        output_dir = Path(work_dir) / "gaussian_output"
        ply_path = output_dir / "point_cloud" / "iteration_30000" / "point_cloud.ply"
    """
    scene_dir, work_dir, output_dir, fastgs_dir, train_script = _validate_and_setup(scene_dir, work_dir)
    cmd = _build_fastgs_cmd(str(scene_dir), str(output_dir))

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(fastgs_dir),
    )
    output_lines = []
    for line in process.stdout:
        line = line.rstrip()
        output_lines.append(line)
        yield line

    process.wait()
    if process.returncode != 0:
        raise RuntimeError(
            f"FastGS failed (exit {process.returncode}):\n" + "\n".join(output_lines[-30:])
        )