import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { PLYLoader } from "three/addons/loaders/PLYLoader.js";
import { plyUrl } from "../api";

// FIX: zoom/scroll wasn't working because the page itself could still
// scroll underneath the canvas — the mouse wheel event was bubbling up to
// the page scroll container instead of being fully captured by Three.js's
// OrbitControls. We now explicitly stop propagation on wheel events over
// the canvas, and make sure the mount div has its own isolated stacking
// context so nothing above it intercepts pointer/wheel events first.
export default function PointCloudViewer({ jobId, cameraPositions = [] }) {
  const mountRef = useRef(null);

  useEffect(() => {
    if (!jobId || !mountRef.current) return;
    const mount = mountRef.current;
    const width = mount.clientWidth;
    const height = 460;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0d1320);

    const camera = new THREE.PerspectiveCamera(60, width / height, 0.01, 1000);
    camera.position.set(0, 0, 4);

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.domElement.style.touchAction = "none";
    mount.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.enableZoom = true;
    controls.enablePan = true;
    controls.minDistance = 0.05;
    controls.maxDistance = 500;
    controls.zoomSpeed = 1.0;

    // Explicitly stop the wheel event from bubbling up to the page so
    // scrolling over the viewer always zooms the 3D scene, never the page.
    const stopWheelPropagation = (e) => { e.stopPropagation(); };
    renderer.domElement.addEventListener("wheel", stopWheelPropagation, { passive: true });

    const loader = new PLYLoader();
    loader.load(
      plyUrl(jobId),
      (geometry) => {
        geometry.center();
        const hasColor = geometry.hasAttribute("color");
        const material = new THREE.PointsMaterial({
          size: 0.01,
          vertexColors: hasColor,
          color: hasColor ? 0xffffff : 0x6fb0ff,
        });
        const points = new THREE.Points(geometry, material);
        scene.add(points);

        geometry.computeBoundingSphere();
        const r = geometry.boundingSphere.radius || 2;
        camera.position.set(0, 0, r * 2.4);
        controls.target.set(0, 0, 0);
        controls.minDistance = r * 0.05;
        controls.maxDistance = r * 10;
        controls.update();
      },
      undefined,
      (err) => console.error("PLY load failed", err)
    );

    cameraPositions.forEach((c) => {
      const g = new THREE.SphereGeometry(0.03, 8, 8);
      const m = new THREE.MeshBasicMaterial({ color: 0xffb020 });
      const s = new THREE.Mesh(g, m);
      s.position.set(c.position[0], c.position[1], c.position[2]);
      scene.add(s);
    });

    let raf;
    const animate = () => {
      raf = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    return () => {
      cancelAnimationFrame(raf);
      renderer.domElement.removeEventListener("wheel", stopWheelPropagation);
      controls.dispose();
      renderer.dispose();
      if (renderer.domElement.parentNode)
        renderer.domElement.parentNode.removeChild(renderer.domElement);
    };
  }, [jobId, cameraPositions]);

  return <div className="viewer" ref={mountRef} style={{ isolation: "isolate" }} />;
}