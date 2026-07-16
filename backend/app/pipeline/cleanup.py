# backend/app/pipeline/cleanup.py
import os
import subprocess


def run_cleanup(scene_out: str) -> str:
    pc_dir = os.path.join(scene_out, "gaussian_output", "point_cloud")
    iter_dirs = [d for d in os.listdir(pc_dir) if d.startswith("iteration_")]
    if not iter_dirs:
        raise RuntimeError(f"No iteration_* dir found in {pc_dir}")
    latest = sorted(iter_dirs, key=lambda d: int(d.split("_")[1]))[-1]

    raw_ply = os.path.join(pc_dir, latest, "point_cloud.ply")
    clean_ply = os.path.join(pc_dir, latest, "point_cloud_clean.ply")

    subprocess.run([
        "3dgsconverter", "-i", raw_ply, "-o", clean_ply, "-f", "3dgs",
        "--min_opacity", "5", "--sor_intensity", "8",
    ], check=True)

    return clean_ply