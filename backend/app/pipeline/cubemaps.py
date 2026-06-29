import os
import cv2
import numpy as np
import py360convert 

# Cube faces in COLMAP-friendly order
FACE_ORDER = ["front", "right", "back", "left", "up", "down"]
HORIZONTAL_ONLY = ["front", "right", "back", "left"]


def is_equirectangular(img) -> bool:
    """A 360 equirectangular image has a ~2:1 aspect ratio."""
    h, w = img.shape[:2]
    return 1.8 <= (w / h) <= 2.2


def generate_cubemaps(input_dir: str, output_dir: str, face_size: int = 1536) -> dict:
    """
    Read every image in input_dir. Equirectangular images are sliced into 6
    cube faces written to output_dir. Flat images are passed through unchanged.

    Returns a summary dict.
    """
    os.makedirs(output_dir, exist_ok=True)
    exts = (".jpg", ".jpeg", ".png")
    images = sorted(f for f in os.listdir(input_dir) if f.lower().endswith(exts))

    if not images:
        raise RuntimeError(f"No images found in {input_dir}")

    panoramas = 0
    faces_written = 0
    passthrough = 0
    face_files = []

    for fname in images:
        path = os.path.join(input_dir, fname)
        img = cv2.imread(path)
        if img is None:
            continue
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        stem = os.path.splitext(fname)[0]

        if is_equirectangular(img):
            panoramas += 1
            faces = py360convert.e2c(
                img, face_w=face_size, mode="bilinear", cube_format="list"
            )
            for face_name, face in zip(FACE_ORDER, faces):
                out_name = f"{stem}_{face_name}.jpg"
                out_path = os.path.join(output_dir, out_name)
                cv2.imwrite(out_path, cv2.cvtColor(face, cv2.COLOR_RGB2BGR))
                faces_written += 1
                face_files.append(out_name)
        else:
            out_path = os.path.join(output_dir, fname)
            cv2.imwrite(out_path, cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
            passthrough += 1
            face_files.append(fname)

    if faces_written == 0 and passthrough == 0:
        raise RuntimeError("No usable images after cubemap stage")

    return {
        "input_images": len(images),
        "panoramas": panoramas,
        "faces_written": faces_written,
        "passthrough": passthrough,
        "total_output": faces_written + passthrough,
        "files": face_files,
    }