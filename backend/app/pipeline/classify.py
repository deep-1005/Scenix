# backend/app/pipeline/classify.py
import json
import os
import open_clip
import torch
from PIL import Image

LABELS = ["a knife", "a blood stain", "a shell casing", "broken glass", "a footprint"]


def run_classify(scene_out: str, images_dir: str, evidence_json_path: str) -> list[dict]:
    model, _, preprocess = open_clip.create_model_and_transforms("ViT-B-32", pretrained="openai")
    tokenizer = open_clip.get_tokenizer("ViT-B-32")
    model.eval()

    text_tokens = tokenizer(LABELS)
    with torch.no_grad():
        text_features = model.encode_text(text_tokens)
        text_features /= text_features.norm(dim=-1, keepdim=True)

    with open(evidence_json_path) as f:
        evidence_list = json.load(f)

    # NOTE: this assumes detection.py also saves a representative crop per evidence
    # item (e.g. evidence_crops/{id}.jpg) from the best-view bbox — add that in
    # detection.py's loop if not already present.
    for item in evidence_list:
        crop_path = os.path.join(scene_out, "evidence_crops", f"{item['id']}.jpg")
        if not os.path.exists(crop_path):
            item["classification"] = None
            continue

        image = preprocess(Image.open(crop_path)).unsqueeze(0)
        with torch.no_grad():
            image_features = model.encode_image(image)
            image_features /= image_features.norm(dim=-1, keepdim=True)
            similarity = (image_features @ text_features.T).squeeze(0)
            best_idx = similarity.argmax().item()

        item["classification"] = LABELS[best_idx]
        item["classification_confidence"] = float(similarity[best_idx])

    out_path = os.path.join(scene_out, "evidence_classified.json")
    with open(out_path, "w") as f:
        json.dump(evidence_list, f, indent=2)

    return evidence_list