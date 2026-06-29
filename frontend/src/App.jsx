import { useState, useEffect, useRef } from "react";
import { createJob, getJob, listJobs, plyUrl } from "./api";
import CubemapGallery from "./components/CubemapGallery";
import PointCloudViewer from "./components/PointCloudViewer";
import "./App.css";

const API = "http://localhost:8000";

const STAGE_LABELS = {
  cubemaps: "Generating cubemaps", preprocess: "AI quality check",
  colmap: "Reconstructing camera poses (COLMAP)", gaussian_splat: "Training Gaussian Splat",
  cleanup: "Cleaning splat artifacts", mesh: "Converting to mesh",
  detection: "Detecting evidence", classify: "Classifying evidence",
  measure: "Computing measurements", report: "Generating report", complete: "Complete",
};

function GaussianSplatSection({ jobId }) {
  const [status, setStatus] = useState("checking");
  const [errorMsg, setErrorMsg] = useState("");
  const pollRef = useRef(null);

  useEffect(() => {
    if (!jobId) return;
    checkStatus();
    return () => clearInterval(pollRef.current);
  }, [jobId]);

  async function checkStatus() {
    try {
      const res = await fetch(`${API}/jobs/${jobId}/gaussian-splat/status`);
      const data = await res.json();
      if (data.status === "done") {
        setStatus("done");
      } else if (data.status === "running") {
        setStatus("running");
        startPolling();
      } else {
        setStatus("not_started");
      }
    } catch {
      setStatus("not_started");
    }
  }

  function startPolling() {
    clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`${API}/jobs/${jobId}/gaussian-splat/status`);
        const data = await res.json();
        if (data.status === "done") {
          setStatus("done");
          clearInterval(pollRef.current);
        }
      } catch {}
    }, 5000);
  }

  async function handleStart() {
    setStatus("running");
    setErrorMsg("");
    try {
      const res = await fetch(`${API}/jobs/${jobId}/gaussian-splat`, { method: "POST" });
      if (!res.ok) {
        const err = await res.json();
        setStatus("error");
        setErrorMsg(err.detail || "Failed to start Gaussian Splatting");
        return;
      }
      startPolling();
    } catch (e) {
      setStatus("error");
      setErrorMsg(e.message);
    }
  }

  function handleDownload() {
    window.open(`${API}/jobs/${jobId}/gaussian-splat/download`, "_blank");
  }

  if (status === "checking") return null;

  return (
    <div style={{
      background: "#f0f0ff", border: "1px solid #c0b8f8",
      borderRadius: 10, padding: "20px 24px", marginTop: 16,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
        <span style={{ fontSize: 18, color: "#7c6af7" }}>✦</span>
        <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600, color: "#333" }}>
          Gaussian Splatting
        </h3>
        <span style={{
          marginLeft: "auto", fontSize: 11, fontWeight: 600,
          padding: "2px 10px", borderRadius: 20,
          background:
            status === "done" ? "#e6f4ea" :
            status === "running" ? "#e8f0fe" :
            status === "error" ? "#fce8e6" : "#f1f3f4",
          color:
            status === "done" ? "#2e7d32" :
            status === "running" ? "#1a73e8" :
            status === "error" ? "#c62828" : "#666",
        }}>
          {{ not_started: "Not started", running: "Running", done: "Complete", error: "Failed" }[status]}
        </span>
      </div>

      <p style={{ fontSize: 13, color: "#666", marginBottom: 16, lineHeight: 1.5 }}>
        Generates a photorealistic 3D Gaussian Splat from your COLMAP reconstruction.
      </p>

      {status === "not_started" && (
        <button onClick={handleStart} style={{
          background: "#7c6af7", color: "#fff", border: "none",
          borderRadius: 6, padding: "8px 20px", fontSize: 13, fontWeight: 600, cursor: "pointer",
        }}>
          Run Gaussian Splatting
        </button>
      )}

      {status === "running" && (
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{
            width: 16, height: 16,
            border: "2px solid #ddd", borderTop: "2px solid #7c6af7",
            borderRadius: "50%", animation: "spin 1s linear infinite",
          }} />
          <span style={{ fontSize: 13, color: "#666" }}>
            Training in progress — this takes a few minutes…
          </span>
        </div>
      )}

      {status === "done" && (
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ color: "#2e7d32", fontSize: 18 }}>✓</span>
          <span style={{ fontSize: 13, color: "#2e7d32", marginRight: "auto" }}>Splat ready</span>
          <button onClick={handleDownload} style={{
            background: "transparent", color: "#7c6af7", border: "1px solid #7c6af7",
            borderRadius: 6, padding: "8px 16px", fontSize: 13, fontWeight: 600, cursor: "pointer",
          }}>
            Download .ply
          </button>
          <button onClick={handleStart} style={{
            background: "#7c6af7", color: "#fff", border: "none",
            borderRadius: 6, padding: "8px 16px", fontSize: 13, fontWeight: 600,
            cursor: "pointer", marginLeft: 8,
          }}>
            Re-run
          </button>
        </div>
      )}

      {status === "error" && (
        <div style={{
          display: "flex", alignItems: "center", gap: 8,
          background: "#fce8e6", borderRadius: 6, padding: "10px 14px",
        }}>
          <span style={{ color: "#c62828" }}>⚠</span>
          <span style={{ fontSize: 13, color: "#c62828", flex: 1 }}>{errorMsg || "Unknown error"}</span>
          <button onClick={handleStart} style={{
            background: "transparent", color: "#c62828", border: "1px solid #c62828",
            borderRadius: 6, padding: "6px 14px", fontSize: 12, cursor: "pointer",
          }}>Retry</button>
        </div>
      )}
    </div>
  );
}

export default function App() {
  const [sceneName, setSceneName] = useState("");
  const [files, setFiles] = useState([]);
  const [activeJob, setActiveJob] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [dragOver, setDragOver] = useState(false);
  const [tab, setTab] = useState("cubemaps");
  const pollRef = useRef(null);

  const refreshJobs = async () => setJobs(await listJobs());
  useEffect(() => { refreshJobs(); }, []);

  useEffect(() => {
    if (!activeJob) return;
    if (["done", "failed"].includes(activeJob.status)) { refreshJobs(); return; }
    pollRef.current = setTimeout(async () =>
      setActiveJob(await getJob(activeJob.job_id)), 1000);
    return () => clearTimeout(pollRef.current);
  }, [activeJob]);

  const handleSubmit = async () => {
    if (!sceneName || files.length === 0) return;
    const { job_id } = await createJob(sceneName, files);
    setActiveJob(await getJob(job_id));
    setSceneName(""); setFiles([]); setTab("cubemaps");
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
          <h2>{activeJob.scene_name}</h2>
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

          {colmapDone && <GaussianSplatSection jobId={activeJob.job_id} />}
        </section>
      )}

      <section className="card">
        <h2>All scenes</h2>
        {jobs.length === 0 && <p className="muted">No scenes yet.</p>}
        <table><tbody>
          {jobs.map((j) => (
            <tr key={j.job_id} onClick={() => getJob(j.job_id).then(setActiveJob)}>
              <td>{j.scene_name || "(unnamed)"}</td>
              <td><span className={`badge ${j.status}`}>{j.status}</span></td>
              <td className="muted">{j.stage}</td>
            </tr>
          ))}
        </tbody></table>
      </section>
    </div>
  );
}