# new: app/pipeline/gaussian_grouping_extract.py (name TBD)
def extract_evidence_from_groups(scene_out, gg_model, query_labels: list[str]) -> list[dict]:
    results = []
    for label in query_labels:
        mask = gg_model.query(label)          # boolean mask over Gaussians
        gaussians = gg_model.gaussians[mask]
        centroid = gaussians.xyz.mean(axis=0)  # already splat-space
        bbox_dims = gaussians.xyz.max(0) - gaussians.xyz.min(0)
        results.append({
            "id": f"{label}_{i}",
            "label": label,
            "classification": label,   # or run CLIP on it if you keep that step
            "confidence": mask_confidence,   # from GG's query score
            "position": {"x": centroid[0], "y": centroid[1], "z": centroid[2]},
            "dimensions": {"w": bbox_dims[0], "h": bbox_dims[1], "d": bbox_dims[2]},
        })
    return results