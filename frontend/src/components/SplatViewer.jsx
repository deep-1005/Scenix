import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { PLYLoader } from "three/addons/loaders/PLYLoader.js";
import { splatPlyUrl } from "../api";

// Renders the FastGS-trained .ply as a colored point cloud.
// Note: this is a point-cloud preview of the splat centers — true
// Gaussian splat (ellipsoid + SH) rendering needs a dedicated splat
// renderer (e.g. SuperSplat / antimatter15 viewer); for an in-app
// quick look, the point cloud is the right tradeoff.
export default function SplatViewer({ jobId }) {
  const mountRef = useRef(null);
  const [loadError, setLoadError] = useState(null);

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

    const loader = new PLYLoader();
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
      <div className="viewer" ref={mountRef} />
      {loadError && (
        <div className="error-box" style={{ marginTop: 10 }}>
          <span>⚠</span><span>{loadError}</span>
        </div>
      )}
      <p className="muted" style={{ marginTop: 8, fontSize: 11 }}>
        For full splat-quality rendering (ellipsoids + lighting), download the .ply
        and open it in SuperSplat or another Gaussian splat viewer.
      </p>
    </div>
  );
}