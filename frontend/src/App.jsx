import { useState, useEffect, useRef } from "react";
import { createJob, getJob, listJobs, plyUrl } from "./api";
import CubemapGallery from "./components/CubemapGallery";
import PointCloudViewer from "./components/PointCloudViewer";
import GaussianSplatViewer from "./components/GaussianSplatViewer";
import StorageManager from "./components/StorageManager";
import "./App.css";

const STAGE_LABELS = {
  cubemaps: "Generating cubemaps", preprocess: "AI quality check",
  colmap: "Reconstructing camera poses (COLMAP)", gaussian_splat: "Training Gaussian Splat",
  cleanup: "Cleaning splat artifacts", mesh: "Converting to mesh",
  detection: "Detecting evidence", classify: "Classifying evidence",
  measure: "Computing measurements", report: "Generating report", complete: "Complete",
};

export default function App() {
  const [sceneName, setSceneName] = useState("");
  const [files, setFiles] = useState([]);
  const [activeJob, setActiveJob] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const [tab, setTab] = useState("cubemaps");
  const [mainTab, setMainTab] = useState("scene"); // "scene" | "storage"
  const pollRef = useRef(null);

  useEffect(() => {
    if (!activeJob) return;
    if (["done", "failed"].includes(activeJob.status)) return;
    pollRef.current = setTimeout(async () =>
      setActiveJob(await getJob(activeJob.job_id)), 1000);
    return () => clearTimeout(pollRef.current);
  }, [activeJob]);

  const handleSubmit = async () => {
    if (!sceneName || files.length === 0) return;
    const { job_id } = await createJob(sceneName, files);
    setActiveJob(await getJob(job_id));
    setSceneName(""); setFiles([]); setTab("cubemaps");
    setMainTab("scene");
  };

  const onDrop = (e) => {
    e.preventDefault(); setDragOver(false);
    setFiles([...e.dataTransfer.files]);
  };

  const colmap = activeJob?.summary?.colmap;
  const colmapDone = !!colmap?.points3D;

  return (
    <div className="app">
      <header>
        <h1>Forensic Digital Twin</h1>
        <p className="sub">Crime scene reconstruction &amp; evidence detection</p>
      </header>

      {/* Main nav tabs */}
      <div style={{ display: "flex", gap: 4, marginBottom: 16 }}>
        <button
          className={mainTab === "scene" ? "on" : ""}
          onClick={() => setMainTab("scene")}
          style={{
            padding: "8px 20px", borderRadius: 8, border: "1px solid #ddd",
            background: mainTab === "scene" ? "#7c6af7" : "#fff",
            color: mainTab === "scene" ? "#fff" : "#333",
            fontWeight: 600, fontSize: 13, cursor: "pointer",
          }}>
          🔬 Reconstruction
        </button>
        <button
          className={mainTab === "storage" ? "on" : ""}
          onClick={() => setMainTab("storage")}
          style={{
            padding: "8px 20px", borderRadius: 8, border: "1px solid #ddd",
            background: mainTab === "storage" ? "#7c6af7" : "#fff",
            color: mainTab === "storage" ? "#fff" : "#333",
            fontWeight: 600, fontSize: 13, cursor: "pointer",
          }}>
          🗂 All Scenes
        </button>
      </div>

      {mainTab === "scene" && (
        <>
          <section className="card">
            <h2>New scene</h2>
            <input className="text-input" placeholder="Scene name (e.g. Apartment 4B)"
                   value={sceneName} onChange={(e) => setSceneName(e.target.value)} />
            <div className={`dropzone ${dragOver ? "over" : ""}`}
                 onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                 onDragLeave={() => setDragOver(false)} onDrop={onDrop}
                 onClick={() => document.getElementById("file-input").click()}>
              {files.length === 0
                ? <p>Drag &amp; drop 360° images, or click to browse</p>
                : <p>{files.length} file(s) selected</p>}
              <input id="file-input" type="file" multiple hidden accept="image/*"
                     onChange={(e) => setFiles([...e.target.files])} />
            </div>
            <button className="primary" onClick={handleSubmit}
                    disabled={!sceneName || files.length === 0}>
              Start reconstruction
            </button>
          </section>

          {activeJob && (
            <section className="card">
              <div style={{ display: "flex", alignItems: "center", marginBottom: 8 }}>
                <h2 style={{ margin: 0, flex: 1 }}>{activeJob.scene_name}</h2>
                <span style={{ fontSize: 11, color: "#888" }}>
                  ID: {activeJob.job_id.slice(0, 8)}…
                </span>
              </div>

              <div className="progress-bar">
                <div className="progress-fill" style={{ width: `${activeJob.progress}%` }} />
              </div>
              <p className="stage">
                {activeJob.status === "failed"
                  ? <span className="err">Failed: {activeJob.error}</span>
                  : `${STAGE_LABELS[activeJob.stage] || activeJob.stage || "Queued"} — ${activeJob.progress}%`}
              </p>

              <div className="tabs">
                <button className={tab === "cubemaps" ? "on" : ""}
                        onClick={() => setTab("cubemaps")}>Cubemaps</button>
                <button className={tab === "pointcloud" ? "on" : ""}
                        onClick={() => setTab("pointcloud")}>Point cloud</button>
              </div>

              {tab === "cubemaps" && <CubemapGallery jobId={activeJob.job_id} />}

              {tab === "pointcloud" && (
                colmapDone
                  ? <>
                      <p className="muted">
                        {colmap.registered_images} images registered ·{" "}
                        {colmap.points3D} 3D points ·{" "}
                        orange dots = camera positions
                      </p>
                      <PointCloudViewer jobId={activeJob.job_id}
                                        cameraPositions={colmap.camera_positions || []} />
                      <a className="download" href={plyUrl(activeJob.job_id)}>
                        Download point cloud (.ply)
                      </a>
                    </>
                  : <p className="muted">Point cloud appears after COLMAP finishes.</p>
              )}

              {colmapDone && <GaussianSplatViewer jobId={activeJob.job_id} />}
            </section>
          )}
        </>
      )}

      {mainTab === "storage" && (
        <section className="card">
          <h2>All Scenes</h2>
          <StorageManager onSelectJob={async (jobId) => {
            const job = await getJob(jobId);
            setActiveJob(job);
            setMainTab("scene");
            setTab("pointcloud");
          }} />
        </section>
      )}
    </div>
  );
}