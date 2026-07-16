# backend/app/pipeline/detection.py
import json
import os
import numpy as np
import open3d as o3d
import torch
from PIL import Image
from sklearn.cluster import DBSCAN
from transformers import OwlViTProcessor, OwlViTForObjectDetection

from app.pipeline.colmap_geometry import load_reconstruction, get_projection_matrix, project_points_to_image

EVIDENCE_PROMPTS = ["a knife", "a blood stain", "a shell casing", "broken glass", "a footprint"]
DETECTION_THRESHOLD = 0.1

_processor = None
_model = None
_postprocess_fn = None


def _resolve_postprocess_fn(processor, model):
    """transformers' post_process_object_detection has moved across versions —
    check known locations in order and use whichever exists on this install."""
    candidates = [
        ("processor.post_process_object_detection", getattr(processor, "post_process_object_detection", None)),
        ("processor.image_processor.post_process_object_detection",
         getattr(getattr(processor, "image_processor", None), "post_process_object_detection", None)),
        ("processor.image_processor.post_process_grounded_object_detection",
         getattr(getattr(processor, "image_processor", None), "post_process_grounded_object_detection", None)),
        ("model.post_process_object_detection", getattr(model, "post_process_object_detection", None)),
    ]
    for name, fn in candidates:
        if fn is not None:
            print(f"[detection] Using post-process method: {name}")
            return fn

    # Nothing matched — dump what's actually available so we can fix this in one shot
    proc_attrs = [a for a in dir(processor) if "post_process" in a.lower() or "process" in a.lower()]
    img_proc = getattr(processor, "image_processor", None)
    img_proc_attrs = [a for a in dir(img_proc) if "post_process" in a.lower()] if img_proc else []
    model_attrs = [a for a in dir(model) if "post_process" in a.lower()]
    raise AttributeError(
        f"Could not find a post_process_object_detection method on this transformers install. "
        f"processor candidates: {proc_attrs} | "
        f"processor.image_processor candidates: {img_proc_attrs} | "
        f"model candidates: {model_attrs}"
    )


def _load_model():
    global _processor, _model, _postprocess_fn
    if _model is None:
        print("[detection] Loading OWL-ViT model...")
        _processor = OwlViTProcessor.from_pretrained("google/owlvit-base-patch32")
        _model = OwlViTForObjectDetection.from_pretrained("google/owlvit-base-patch32")
        _model.eval()
        _postprocess_fn = _resolve_postprocess_fn(_processor, _model)
    return _processor, _model, _postprocess_fn


def _run_owlvit_on_image(image_path: str, prompts: list[str]) -> list[dict]:
    processor, model, postprocess_fn = _load_model()
    image = Image.open(image_path).convert("RGB")

    inputs = processor(text=[prompts], images=image, return_tensors="pt")
    with torch.no_grad():
        outputs = model(**inputs)

    target_sizes = torch.tensor([image.size[::-1]])
    results = postprocess_fn(outputs=outputs, threshold=DETECTION_THRESHOLD, target_sizes=target_sizes)[0]

    detections = []
    for box, score, label_idx in zip(results["boxes"], results["scores"], results["labels"]):
        detections.append({
            "label": prompts[label_idx],
            "bbox_xyxy": box.tolist(),
            "confidence": float(score),
        })
    return detections


def run_detection(scene_out: str, images_dir: str) -> list[dict]:
    recon = load_reconstruction(scene_out)
    pcd_path = os.path.join(scene_out, "sparse", "0", "points3D_cleaned.ply")
    pcd = o3d.io.read_point_cloud(pcd_path)
    points = np.asarray(pcd.points)

    candidate_points = []

    image_files = [f for f in os.listdir(images_dir) if f.lower().endswith((".jpg", ".jpeg", ".png"))]
    print(f"[detection] Running OWL-ViT across {len(image_files)} images...")

    for i, fname in enumerate(image_files):
        img_path = os.path.join(images_dir, fname)

        try:
            K, Rt = get_projection_matrix(recon, fname)
        except KeyError:
            continue

        detections = _run_owlvit_on_image(img_path, EVIDENCE_PROMPTS)
        if not detections:
            continue

        pixels = project_points_to_image(points, K, Rt)

        for det in detections:
            x1, y1, x2, y2 = det["bbox_xyxy"]
            in_box = (
                (pixels[:, 0] >= x1) & (pixels[:, 0] <= x2) &
                (pixels[:, 1] >= y1) & (pixels[:, 1] <= y2)
            )
            matched = points[in_box]
            for p in matched:
                candidate_points.append((p, det["label"]))

        if (i + 1) % 10 == 0:
            print(f"[detection] Processed {i + 1}/{len(image_files)} images")

    evidence_list = []
    for label in EVIDENCE_PROMPTS:
        label_points = np.array([p for p, l in candidate_points if l == label])
        if len(label_points) < 5:
            continue
        clustering = DBSCAN(eps=0.05, min_samples=5).fit(label_points)
        for cluster_id in set(clustering.labels_) - {-1}:
            cluster_pts = label_points[clustering.labels_ == cluster_id]
            evidence_list.append({
                "id": f"{label.replace(' ', '_')}_{cluster_id}",
                "label": label,
                "points": cluster_pts.tolist(),
            })

    out_path = os.path.join(scene_out, "evidence.json")
    with open(out_path, "w") as f:
        json.dump(evidence_list, f, indent=2)

    print(f"[detection] Found {len(evidence_list)} evidence clusters")
    return evidence_list


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--scene-out", required=True)
    parser.add_argument("--images-dir", required=True)
    args = parser.parse_args()

    try:
        evidence = run_detection(args.scene_out, args.images_dir)
        print(f"[detection] Wrote {len(evidence)} evidence items to evidence.json")
    except Exception as e:
        print(f"[detection] FAILED: {e}")
        raise SystemExit(1)
