import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { PLYLoader } from "three/addons/loaders/PLYLoader.js";
import { plyUrl } from "../api";

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
    mount.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;

    // Load the COLMAP point cloud
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

        // frame the cloud
        geometry.computeBoundingSphere();
        const r = geometry.boundingSphere.radius || 2;
        camera.position.set(0, 0, r * 2.4);
        controls.update();
      },
      undefined,
      (err) => console.error("PLY load failed", err)
    );

    // Camera position markers (where each photo was taken)
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
      controls.dispose();
      renderer.dispose();
      if (renderer.domElement.parentNode)
        renderer.domElement.parentNode.removeChild(renderer.domElement);
    };
  }, [jobId, cameraPositions]);

  return <div className="viewer" ref={mountRef} />;
}
