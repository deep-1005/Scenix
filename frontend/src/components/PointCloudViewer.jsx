import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { PLYLoader } from "three/addons/loaders/PLYLoader.js";
import { plyUrl } from "../api";

export default function PointCloudViewer({ jobId, cameraPositions = [] }) {
  const mountRef = useRef(null);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [pointSize, setPointSize] = useState(3);
  const [showCameras, setShowCameras] = useState(false);
  const materialRef = useRef(null);
  const cameraGroupRef = useRef(null);

  useEffect(() => {
    if (!jobId || !mountRef.current) return;
    const mount = mountRef.current;
    const width = mount.clientWidth;
    const height = 520;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0a0f1a);
    scene.add(new THREE.GridHelper(20, 40, 0x1a2a3a, 0x1a2a3a));
    scene.add(new THREE.AxesHelper(1));

    const camera = new THREE.PerspectiveCamera(55, width / height, 0.001, 50000);
    camera.position.set(0, 2, 8);

    const renderer = new THREE.WebGLRenderer({ antialias: true, logarithmicDepthBuffer: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    mount.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.06;
    controls.screenSpacePanning = true;
    controls.zoomSpeed = 1.5;
    controls.rotateSpeed = 0.8;

    const camGroup = new THREE.Group();
    camGroup.visible = false;
    scene.add(camGroup);
    cameraGroupRef.current = camGroup;

    const loader = new PLYLoader();
    loader.load(
      plyUrl(jobId),
      (geometry) => {
        geometry.computeBoundingBox();
        const box = geometry.boundingBox;
        const center = new THREE.Vector3();
        box.getCenter(center);
        const size = new THREE.Vector3();
        box.getSize(size);
        geometry.translate(-center.x, -center.y, -center.z);
        geometry.computeBoundingSphere();

        const hasColor = geometry.hasAttribute("color");
        const mat = new THREE.PointsMaterial({
          size: 0.03, vertexColors: hasColor,
          color: hasColor ? 0xffffff : 0x4fc3f7,
          sizeAttenuation: true, transparent: true, opacity: 0.95,
        });
        materialRef.current = mat;
        scene.add(new THREE.Points(geometry, mat));

        const r = geometry.boundingSphere.radius || 5;
        camera.position.set(r * 0.5, r * 0.8, r * 2.2);
        camera.near = r * 0.0001;
        camera.far = r * 200;
        camera.updateProjectionMatrix();
        controls.target.set(0, 0, 0);
        controls.minDistance = r * 0.005;
        controls.maxDistance = r * 30;
        controls.update();

        const markerSize = Math.max(r * 0.006, 0.02);
        cameraPositions.forEach((c) => {
          const mesh = new THREE.Mesh(
            new THREE.SphereGeometry(markerSize, 6, 6),
            new THREE.MeshBasicMaterial({ color: 0xff7e00 })
          );
          mesh.position.set(
            c.position[0] - center.x,
            c.position[1] - center.y,
            c.position[2] - center.z
          );
          camGroup.add(mesh);
        });

        setStats({
          points: geometry.attributes.position.count.toLocaleString(),
          cameras: cameraPositions.length,
          hasColor,
        });
        setLoading(false);
      },
      (xhr) => { if (xhr.total) setLoading(`Loading ${Math.round(xhr.loaded / xhr.total * 100)}%`); },
      () => { setError("Failed to load point cloud"); setLoading(false); }
    );

    let raf;
    const animate = () => { raf = requestAnimationFrame(animate); controls.update(); renderer.render(scene, camera); };
    animate();

    const handleResize = () => {
      const w = mount.clientWidth;
      renderer.setSize(w, height);
      camera.aspect = w / height;
      camera.updateProjectionMatrix();
    };
    window.addEventListener("resize", handleResize);

    return () => {
      cancelAnimationFrame(raf);
      controls.dispose();
      renderer.dispose();
      window.removeEventListener("resize", handleResize);
      if (renderer.domElement.parentNode)
        renderer.domElement.parentNode.removeChild(renderer.domElement);
    };
  }, [jobId, cameraPositions]);

  useEffect(() => {
    if (materialRef.current) {
      materialRef.current.size = pointSize * 0.012;
      materialRef.current.needsUpdate = true;
    }
  }, [pointSize]);

  useEffect(() => {
    if (cameraGroupRef.current) cameraGroupRef.current.visible = showCameras;
  }, [showCameras]);

  return (
    <div style={{ position: "relative", borderRadius: "10px", overflow: "hidden", background: "#0a0f1a" }}>
      <div style={{
        position: "absolute", top: 10, left: 10, zIndex: 10,
        display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap",
        background: "rgba(0,0,0,0.6)", borderRadius: 8, padding: "6px 12px",
        backdropFilter: "blur(6px)", color: "#fff", fontSize: 12,
      }}>
        <span style={{ opacity: 0.7 }}>Point size</span>
        <input type="range" min={1} max={12} value={pointSize}
          onChange={e => setPointSize(Number(e.target.value))}
          style={{ width: 70, accentColor: "#4fc3f7" }} />
        <label style={{ display: "flex", alignItems: "center", gap: 5, cursor: "pointer", opacity: 0.85 }}>
          <input type="checkbox" checked={showCameras} onChange={e => setShowCameras(e.target.checked)} />
          📷 cameras
        </label>
        <span style={{ opacity: 0.45, fontSize: 11 }}>Drag=rotate · Scroll=zoom · Right=pan</span>
      </div>

      {stats && (
        <div style={{
          position: "absolute", top: 10, right: 10, zIndex: 10,
          background: "rgba(0,0,0,0.6)", borderRadius: 8, padding: "6px 12px",
          backdropFilter: "blur(6px)", color: "#fff", fontSize: 12,
          display: "flex", gap: 14,
        }}>
          <span>🔵 <b>{stats.points}</b> pts</span>
          <span>📷 <b>{stats.cameras}</b> cams</span>
          {stats.hasColor && <span style={{ color: "#4fc3f7" }}>● color</span>}
        </div>
      )}

      {loading && (
        <div style={{
          position: "absolute", inset: 0, zIndex: 20, display: "flex",
          alignItems: "center", justifyContent: "center",
          background: "rgba(10,15,26,0.85)", color: "#4fc3f7", fontSize: 16,
          flexDirection: "column", gap: 12,
        }}>
          <div style={{ width: 40, height: 40, border: "3px solid #4fc3f7", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
          <span>{typeof loading === "string" ? loading : "Loading point cloud…"}</span>
          <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        </div>
      )}

      {error && (
        <div style={{ position: "absolute", inset: 0, zIndex: 20, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(10,15,26,0.9)", color: "#ff6b6b" }}>
          ⚠ {error}
        </div>
      )}

      <div ref={mountRef} style={{ width: "100%" }} />
    </div>
  );
}