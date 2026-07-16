import os
import numpy as np
import pycolmap


def load_reconstruction(scene_out: str) -> pycolmap.Reconstruction:
    sparse0 = os.path.join(scene_out, "sparse", "0")
    if not os.path.isdir(sparse0):
        raise RuntimeError(f"No COLMAP reconstruction at {sparse0}")
    return pycolmap.Reconstruction(sparse0)


def get_projection_matrix(recon: pycolmap.Reconstruction, image_name: str) -> tuple[np.ndarray, np.ndarray]:
    image = None
    for img in recon.images.values():
        if img.name == image_name:
            image = img
            break
    if image is None:
        raise KeyError(f"Image '{image_name}' not found in reconstruction")

    camera = recon.cameras[image.camera_id]
    K = camera.calibration_matrix()

    cam_from_world = image.cam_from_world
    if callable(cam_from_world):
        cam_from_world = cam_from_world()

    R = cam_from_world.rotation.matrix()
    t = cam_from_world.translation
    Rt = np.hstack([R, t.reshape(3, 1)])

    return K, Rt


def triangulate_multiview(observations: list[tuple[np.ndarray, np.ndarray, np.ndarray]]) -> np.ndarray:
    if len(observations) < 2:
        raise ValueError("Need at least 2 views to triangulate a 3D point")

    A_rows = []
    for K, Rt, (px, py) in observations:
        P = K @ Rt
        A_rows.append(px * P[2, :] - P[0, :])
        A_rows.append(py * P[2, :] - P[1, :])

    A = np.stack(A_rows)
    _, _, Vt = np.linalg.svd(A)
    X = Vt[-1]
    X = X[:3] / X[3]
    return X


def project_points_to_image(points_3d: np.ndarray, K: np.ndarray, Rt: np.ndarray) -> np.ndarray:
    P = K @ Rt
    ones = np.ones((points_3d.shape[0], 1))
    homog = np.hstack([points_3d, ones])
    proj = (P @ homog.T).T
    behind = proj[:, 2] <= 0
    pixels = proj[:, :2] / proj[:, 2:3]
    pixels[behind] = np.nan
    return pixels
