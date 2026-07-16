// frontend/src/components/EvidenceOverlay.js
import * as THREE from "three";

const LABEL_COLORS = {
  "a knife": 0xff5555,
  "a blood stain": 0xcc2222,
  "a shell casing": 0xffcc00,
  "broken glass": 0x66ccff,
  "a footprint": 0x88ff88,
};
const DEFAULT_COLOR = 0xffffff;

/**
 * Finds the underlying THREE.Scene/Camera/Renderer on a
 * @mkkellogg/gaussian-splats-3d Viewer instance. Property names vary by
 * version, so we try the known candidates in order and fail loudly with
 * a diagnostic list if none match — same pattern used for the OWL-ViT
 * post-process-method resolution.
 */
export function resolveViewerInternals(viewer) {
  const sceneCandidates = ["threeScene", "scene", "splatScene"];
  const cameraCandidates = ["camera", "threeCamera"];
  const rendererCandidates = ["renderer", "threeRenderer"];

  const pick = (obj, names) => {
    for (const name of names) {
      if (obj[name] && (obj[name].isScene || obj[name].isCamera || obj[name].isWebGLRenderer || obj[name].domElement)) {
        return { name, value: obj[name] };
      }
    }
    return null;
  };

  const scene = pick(viewer, sceneCandidates);
  const camera = pick(viewer, cameraCandidates);
  const renderer = pick(viewer, rendererCandidates);

  if (!scene || !camera || !renderer) {
    const allProps = Object.keys(viewer).filter((k) => !k.startsWith("_"));
    throw new Error(
      `Could not find scene/camera/renderer on GaussianSplats3D.Viewer. ` +
      `Found scene=${scene?.name || "none"}, camera=${camera?.name || "none"}, renderer=${renderer?.name || "none"}. ` +
      `All viewer properties: ${allProps.join(", ")}`
    );
  }

  console.log(`[EvidenceOverlay] Resolved: scene=${scene.name}, camera=${camera.name}, renderer=${renderer.name}`);
  return { scene: scene.value, camera: camera.value, renderer: renderer.value };
}

export function createEvidenceMarkers(scene, evidence, selectedId) {
  const markers = {};
  evidence.forEach((item) => {
    if (!item.centroid) return;
    const color = LABEL_COLORS[item.label] || DEFAULT_COLOR;
    const isSelected = item.id === selectedId;

    const geo = new THREE.SphereGeometry(isSelected ? 0.04 : 0.03, 16, 16);
    const mat = new THREE.MeshStandardMaterial({
      color, emissive: color, emissiveIntensity: isSelected ? 1.0 : 0.5,
      transparent: true, opacity: 0.85,
    });
    const marker = new THREE.Mesh(geo, mat);
    marker.position.set(item.centroid[0], item.centroid[1], item.centroid[2]);
    marker.userData.id = item.id;
    marker.userData.evidence = item;
    scene.add(marker);
    markers[item.id] = marker;
  });

  if (!scene.userData.evidenceLight) {
    const light = new THREE.AmbientLight(0xffffff, 0.6);
    scene.add(light);
    scene.userData.evidenceLight = light;
  }

  return markers;
}

export function clearEvidenceMarkers(scene, markers) {
  Object.values(markers).forEach((m) => {
    scene.remove(m);
    m.geometry.dispose();
    m.material.dispose();
  });
}

export function setupPicking(renderer, camera, getMarkers, { onHover, onClick }) {
  const raycaster = new THREE.Raycaster();
  const mouse = new THREE.Vector2();

  function updateMouse(e) {
    const rect = renderer.domElement.getBoundingClientRect();
    mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
  }

  function pick(e) {
    updateMouse(e);
    raycaster.setFromCamera(mouse, camera);
    const markers = Object.values(getMarkers());
    const hits = raycaster.intersectObjects(markers);
    return hits.length > 0 ? hits[0].object.userData : null;
  }

  const onPointerMove = (e) => onHover?.(pick(e)?.id ?? null);
  const onPointerClick = (e) => {
    const hit = pick(e);
    if (hit) onClick?.(hit.id);
  };

  renderer.domElement.addEventListener("pointermove", onPointerMove);
  renderer.domElement.addEventListener("click", onPointerClick);

  return () => {
    renderer.domElement.removeEventListener("pointermove", onPointerMove);
    renderer.domElement.removeEventListener("click", onPointerClick);
  };
}