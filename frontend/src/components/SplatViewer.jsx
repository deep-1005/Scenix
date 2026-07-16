import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { PLYLoader } from "three/addons/loaders/PLYLoader.js";
import { splatPlyUrl } from "../api";

export default function SplatViewer({ jobId }) {
  const mountRef = useRef(null);
  const [loadError, setLoadError] = useState(null);

  useEffect(() => {
    if (!jobId || !mountRef.current) return;
    const mount = mountRef.current;
    const width = mount.clientWidth;
    const height = 460;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xece2cc);

    const camera = new THREE.PerspectiveCamera(60, width / height, 0.01, 1000);
    camera.position.set(0, 0, 4);

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.domElement.style.touchAction = "none";
    mount.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping  = true;
    controls.enableZoom     = true;
    controls.enablePan      = true;
    controls.zoomSpeed      = 1.0;

    // FIX: same 180° lock as PointCloudViewer — remove polar angle cap
    controls.minPolarAngle  = 0;
    controls.maxPolarAngle  = Math.PI;

    // Stop wheel events from scrolling the page
    const stopWheel = (e) => e.stopPropagation();
    renderer.domElement.addEventListener("wheel", stopWheel, { passive: true });

    const loader = new PLYLoader();
    loader.setRequestHeader({ "ngrok-skip-browser-warning": "true" });
    loader.load(
      splatPlyUrl(jobId),
      (geometry) => {
        geometry.center();
        const hasColor = geometry.hasAttribute("color");
        const material = new THREE.PointsMaterial({
          size: 0.012,
          vertexColors: hasColor,
          color: hasColor ? 0xffffff : 0xb38fff,
          sizeAttenuation: true,
        });
        const points = new THREE.Points(geometry, material);
        scene.add(points);

        geometry.computeBoundingSphere();
        const r = geometry.boundingSphere.radius || 2;
        camera.position.set(0, 0, r * 2.2);
        controls.minDistance = r * 0.05;
        controls.maxDistance = r * 10;
        controls.update();
      },
      undefined,
      (err) => {
        console.error("Splat PLY load failed", err);
        setLoadError("Could not load Gaussian splat output.");
      }
    );

    let raf;
    const animate = () => {
      raf = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    return () => {
      cancelAnimationFrame(raf);
      renderer.domElement.removeEventListener("wheel", stopWheel);
      controls.dispose();
      renderer.dispose();
      if (renderer.domElement.parentNode)
        renderer.domElement.parentNode.removeChild(renderer.domElement);
    };
  }, [jobId]);

  return (
    <div>
      <div className="viewer-meta">
        <span className="viewer-stat" style={{ color: "#b38fff" }}>
          ● Gaussian splat preview (point cloud of splat centers)
        </span>
      </div>
      <div className="viewer" ref={mountRef} style={{ isolation: "isolate" }} />
      {loadError && (
        <div className="error-box" style={{ marginTop: 10 }}>
          <span>⚠</span><span>{loadError}</span>
        </div>
      )}
      <p className="muted" style={{ marginTop: 8, fontSize: 11 }}>
        Drag to orbit (full 360°), scroll to zoom, right-drag to pan.
      </p>
    </div>
  );
}