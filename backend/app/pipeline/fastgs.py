import os
import subprocess
import shutil
from pathlib import Path


def run_fastgs(scene_dir: str, work_dir: str, stream=False):
    """
    Run FastGS gaussian splatting on a scene that already has COLMAP output.

    Expects:
        scene_dir/images/       - cubemap tile images
        scene_dir/sparse/0/     - cameras.bin, images.bin, points3D.bin

    Produces:
        work_dir/gaussian_output/point_cloud/iteration_7000/point_cloud.ply
    """
    scene_dir = Path(scene_dir)
    work_dir = Path(work_dir)

    images_dir = scene_dir / "images"
    sparse_dir = scene_dir / "sparse" / "0"
    output_dir = work_dir / "gaussian_output"

    # --- Validate inputs ---
    if not images_dir.exists():
        raise FileNotFoundError(f"images/ not found at {images_dir}")

    for required in ["cameras.bin", "images.bin", "points3D.bin"]:
        if not (sparse_dir / required).exists():
            # Try .txt variants (COLMAP can output either)
            txt = required.replace(".bin", ".txt")
            if not (sparse_dir / txt).exists():
                raise FileNotFoundError(
                    f"COLMAP output missing: {required} (and no .txt fallback) in {sparse_dir}"
                )

    output_dir.mkdir(parents=True, exist_ok=True)

    # --- Locate FastGS ---
    fastgs_dir = Path(os.environ.get("FASTGS_DIR", os.path.expanduser("~/Desktop/360_image_processing/FastGS")))
    train_script = fastgs_dir / "train.py"

    if not train_script.exists():
        raise FileNotFoundError(
            f"FastGS train.py not found at {train_script}. "
            "Set FASTGS_DIR env var or update the path in fastgs.py"
        )

    cmd = [
        "python", str(train_script),
        "-s", str(scene_dir),
        "--model_path", str(output_dir),
        "--iterations", "7000",          # fast default; bump to 30000 for final quality
        "--densify_until_iter", "5000",
    ]

    if stream:
        # Stream output line by line (for real-time progress in UI)
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
    else:
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
        return result.stdout

    # Return path to the output ply
    ply_path = output_dir / "point_cloud" / "iteration_7000" / "point_cloud.ply"
    return str(ply_path) if ply_path.exists() else str(output_dir)