import { useState, useEffect, useRef } from "react";
import { createJob, getJob, listJobs, plyUrl, splatPlyUrl, resumeJob, API } from "./api";
import CubemapGallery from "./components/CubemapGallery";
import PointCloudViewer from "./components/PointCloudViewer";
import SplatViewer from "./components/SplatViewer";
import GaussianSplatSection from "./components/GaussianSplatViewer";
import StorageManager from "./components/StorageManager";
import Toast from "./components/Toast";
import "./App.css";

// Matches the ACTUAL stages tasks.py reports — no more fake "AI check".
const STAGES = [
  { key: "cubemaps",       label: "Cubemaps" },
  { key: "colmap",         label: "COLMAP" },
  { key: "cleaning",       label: "Cleaning" },
  { key: "gaussian_splat", label: "Gaussian" },
  { key: "cleanup",        label: "Cleanup" },
  { key: "mesh",           label: "Mesh" },
  { key: "detection",      label: "Detection" },
  { key: "classify",       label: "Classify" },
  { key: "measure",        label: "Measure" },
  { key: "report",         label: "Report" },
  { key: "complete",       label: "Done" },
];

const STAGE_LABELS = {
  cubemaps:       "Generating perspective views",
  colmap:         "Reconstructing camera poses",
  cleaning:       "Cleaning point cloud",
  gaussian_splat: "Training Gaussian Splat",
  cleanup:        "Cleaning splat artifacts",
  mesh:           "Converting to mesh",
  detection:      "Detecting evidence",
  classify:       "Classifying evidence",
  measure:        "Computing measurements",
  report:         "Generating report",
  complete:       "Complete",
};

function stageState(job, stageKey) {
  if (!job) return "pending";
  const currentIdx = STAGES.findIndex(s => s.key === job.stage);
  const thisIdx = STAGES.findIndex(s => s.key === stageKey);
  if (job.status === "failed" && job.stage === stageKey) return "error";
  if (thisIdx < currentIdx) return "done";
  if (thisIdx === currentIdx) return job.status === "done" ? "done" : "active";
  return "pending";
}

function StatusDot({ status }) {
  const color = {
    running: "var(--accent)",
    done: "var(--success)",
    complete: "var(--success)",
    failed: "var(--danger)",
    pending: "var(--text-dim)",
  }[status] || "var(--text-dim)";
  return (
    <div style={{
      width: 7, height: 7, borderRadius: "50%",
      background: color, flexShrink: 0,
      animation: status === "running" ? "pulse 1.5s ease-in-out infinite" : "none",
    }} />
  );
}

export default function App() {
  const [sceneName, setSceneName] = useState("");
  const [files, setFiles] = useState([]);
  const [activeJob, setActiveJob] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [dragOver, setDragOver] = useState(false);
  const [tab, setTab] = useState("cubemaps");
  const [view, setView] = useState("reconstruction");
  const [submitting, setSubmitting] = useState(false);
  const [resuming, setResuming] = useState(false);
  const [toasts, setToasts] = useState([]);
  const pollRef = useRef(null);

  // Track which milestone notifications have already fired for this job,
  // so we don't spam the same toast every poll tick.
  const notifiedRef = useRef({});

  const pushToast = (message, kind = "info") => {
    const id = Date.now() + Math.random();
    setToasts(t => [...t, { id, message, kind }]);
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), 5000);
  };

  const refreshJobs = async () => setJobs(await listJobs());
  useEffect(() => { refreshJobs(); }, []);

  useEffect(() => {
    if (!activeJob) return;
    if (["done", "failed"].includes(activeJob.status)) { refreshJobs(); return; }
    pollRef.current = setTimeout(async () =>
      setActiveJob(await getJob(activeJob.job_id)), 1000);
    return () => clearTimeout(pollRef.current);
  }, [activeJob]);

  // ── Milestone notifications ──
  useEffect(() => {
    if (!activeJob) return;
    const key = activeJob.job_id;
    if (!notifiedRef.current[key]) notifiedRef.current[key] = {};
    const fired = notifiedRef.current[key];

    const stageIdx = STAGES.findIndex(s => s.key === activeJob.stage);
    const cubemapsIdx = STAGES.findIndex(s => s.key === "cubemaps");
    const colmapIdx = STAGES.findIndex(s => s.key === "colmap");
    const gaussianIdx = STAGES.findIndex(s => s.key === "gaussian_splat");

    if (!fired.cubemapsDone && stageIdx > cubemapsIdx) {
      fired.cubemapsDone = true;
      pushToast(`"${activeJob.scene_name}" — perspective views generated`, "success");
    }
    if (!fired.colmapStarted && activeJob.stage === "colmap") {
      fired.colmapStarted = true;
      pushToast(`"${activeJob.scene_name}" — point cloud generation started`, "info");
    }
    if (!fired.colmapDone && stageIdx > colmapIdx) {
      fired.colmapDone = true;
      pushToast(`"${activeJob.scene_name}" — point cloud ready`, "success");
    }
    if (!fired.gaussianStarted && activeJob.stage === "gaussian_splat") {
      fired.gaussianStarted = true;
      pushToast(`"${activeJob.scene_name}" — Gaussian Splat training started`, "info");
    }
    if (!fired.gaussianDone && stageIdx > gaussianIdx) {
      fired.gaussianDone = true;
      pushToast(`"${activeJob.scene_name}" — Gaussian Splat ready`, "success");
    }
    if (!fired.allDone && activeJob.status === "done") {
      fired.allDone = true;
      pushToast(`"${activeJob.scene_name}" — pipeline complete`, "success");
    }
    if (!fired.failedNotified && activeJob.status === "failed") {
      fired.failedNotified = true;
      pushToast(`"${activeJob.scene_name}" — pipeline failed`, "error");
    }
  }, [activeJob?.stage, activeJob?.status]);

  const handleSubmit = async () => {
    if (!sceneName || files.length === 0) return;
    setSubmitting(true);
    try {
      const { job_id } = await createJob(sceneName, files);
      const job = await getJob(job_id);
      setActiveJob(job);
      setSceneName(""); setFiles([]); setTab("cubemaps");
      setView("reconstruction");
      await refreshJobs();
    } finally {
      setSubmitting(false);
    }
  };

  const onDrop = (e) => {
    e.preventDefault(); setDragOver(false);
    setFiles([...e.dataTransfer.files]);
  };

  const handleSelectFromStorage = async (jobId) => {
    const job = await getJob(jobId);
    setActiveJob(job);
    setTab("cubemaps");
    setView("reconstruction");
  };

  const handleResume = async () => {
    if (!activeJob) return;
    setResuming(true);
    try {
      await resumeJob(activeJob.job_id);
      setActiveJob(await getJob(activeJob.job_id));
      await refreshJobs();
    } catch (e) {
      pushToast(`Resume failed: ${e.message}`, "error");
    } finally {
      setResuming(false);
    }
  };

  const colmap = activeJob?.summary?.colmap;
  const colmapDone = !!colmap?.points3D;

  // Cubemaps are "fully done" once the job has moved past the cubemaps stage
  // (progress >= 20, per tasks.py) — that's when "Download all" should unlock.
  const cubemapsFullyDone = activeJob
    ? STAGES.findIndex(s => s.key === activeJob.stage) > STAGES.findIndex(s => s.key === "cubemaps")
    : false;

  const gaussianStageIdx = STAGES.findIndex(s => s.key === "gaussian_splat");
  const currentStageIdx = activeJob ? STAGES.findIndex(s => s.key === activeJob.stage) : -1;
  const gaussianRunning = activeJob?.stage === "gaussian_splat";
  const gaussianDone = currentStageIdx > gaussianStageIdx || activeJob?.status === "done";

  const currentStageLabel = activeJob
    ? (STAGE_LABELS[activeJob.stage] || activeJob.stage || "Queued")
    : null;

  return (
    <div className="app">
      <div className="toast-stack">
        {toasts.map(t => <Toast key={t.id} {...t} />)}
      </div>

      {/* ── Header ── */}
      <header className="app-header">
        <div className="logo-mark">FD</div>
        <h1>Forensic Digital Twin</h1>
        <span className="sub">/ crime scene reconstruction</span>

        <div className="header-view-tabs">
          <button
            className={`header-view-tab ${view === "reconstruction" ? "on" : ""}`}
            onClick={() => setView("reconstruction")}
          >
            ⬡ Reconstruction
          </button>
          <button
            className={`header-view-tab ${view === "scenes" ? "on" : ""}`}
            onClick={() => setView("scenes")}
          >
            ☐ All scenes
          </button>
        </div>

        <div className="header-spacer" />
        <div className="header-status">
          <div className="header-dot" />
          API connected
        </div>
      </header>

      {/* ── Sidebar ── */}
      <aside className="sidebar">
        <div className="sidebar-section">
          <div className="sidebar-label">New scene</div>
          <input
            className="text-input"
            placeholder="Scene name, e.g. Apartment 4B"
            value={sceneName}
            onChange={(e) => setSceneName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
          />
          <div
            className={`dropzone ${dragOver ? "over" : ""}`}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
            onClick={() => document.getElementById("file-input").click()}
          >
            {files.length === 0
              ? <>Drop 360° images here<br /><span style={{ fontSize: 11 }}>or click to browse</span></>
              : <><strong style={{ color: "var(--accent)" }}>{files.length}</strong> file{files.length !== 1 ? "s" : ""} selected</>
            }
            <input id="file-input" type="file" multiple hidden accept="image/*"
              onChange={(e) => setFiles([...e.target.files])} />
          </div>
          <button
            className="primary"
            onClick={handleSubmit}
            disabled={!sceneName || files.length === 0 || submitting}
          >
            {submitting ? "Starting…" : "Start reconstruction"}
          </button>
        </div>

        <div style={{ padding: "12px 16px 8px" }}>
          <div className="sidebar-label">All scenes</div>
        </div>
        <div className="job-list">
          {jobs.length === 0 && (
            <div style={{ padding: "8px 4px", fontSize: 12, color: "var(--text-dim)" }}>
              No scenes yet.
            </div>
          )}
          {jobs.map((j) => (
            <div
              key={j.job_id}
              className={`job-item ${activeJob?.job_id === j.job_id ? "active" : ""}`}
              onClick={() => { getJob(j.job_id).then(setActiveJob); setView("reconstruction"); }}
            >
              <div className="job-item-name">{j.scene_name || "(unnamed)"}</div>
              <div className="job-item-meta">
                <StatusDot status={j.status} />
                <div className="job-progress-bar">
                  <div
                    className="job-progress-fill"
                    style={{
                      width: `${j.progress || 0}%`,
                      background: j.status === "done" || j.status === "complete"
                        ? "var(--success)"
                        : j.status === "failed"
                          ? "var(--danger)"
                          : "var(--accent)",
                    }}
                  />
                </div>
                <span style={{ fontSize: 10, color: "var(--text-dim)", fontFamily: "var(--mono)", minWidth: 28 }}>
                  {j.progress || 0}%
                </span>
              </div>
            </div>
          ))}
        </div>
      </aside>

      {/* ── Main ── */}
      <main className="main">
        {view === "scenes" ? (
          <div className="tab-content">
            <StorageManager onSelectJob={handleSelectFromStorage} />
          </div>
        ) : !activeJob ? (
          <div className="main-empty">
            <div className="main-empty-icon">⬡</div>
            <div>Select a scene or start a new reconstruction</div>
          </div>
        ) : (
          <>
            <div className="scene-header">
              <div>
                <div className="scene-name">{activeJob.scene_name}</div>
                <div className="scene-stage">
                  {activeJob.status === "failed"
                    ? <span className="err">Failed</span>
                    : currentStageLabel
                  }
                </div>
              </div>
              <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 10, marginLeft: 16 }}>
                <div className="progress-track">
                  <div
                    className={`progress-fill ${activeJob.status === "done" || activeJob.status === "complete" ? "done" : activeJob.status === "failed" ? "error" : ""}`}
                    style={{ width: `${activeJob.progress || 0}%` }}
                  />
                </div>
                <span className="progress-pct">{activeJob.progress || 0}%</span>
              </div>
              <span className={`badge ${activeJob.status}`}>{activeJob.status}</span>
            </div>

            <div className="pipeline-steps">
              {STAGES.map((s, i) => {
                const state = stageState(activeJob, s.key);
                return (
                  <div key={s.key} className="pipeline-step">
                    <div className="step-node">
                      <div className={`step-dot ${state}`} />
                      <span className={`step-label ${state}`}>{s.label}</span>
                    </div>
                    {i < STAGES.length - 1 && (
                      <div className={`step-connector ${state === "done" ? "done" : ""}`} />
                    )}
                  </div>
                );
              })}
            </div>

            <div className="tabs">
              <button className={tab === "cubemaps" ? "on" : ""} onClick={() => setTab("cubemaps")}>Cubemaps</button>
              <button className={tab === "pointcloud" ? "on" : ""} onClick={() => setTab("pointcloud")}>Point cloud</button>
              <button className={tab === "splat" ? "on" : ""} onClick={() => setTab("splat")}>Gaussian splat</button>
            </div>

            <div className="tab-content">
              {tab === "cubemaps" && (
                <CubemapGallery jobId={activeJob.job_id} cubemapsFullyDone={cubemapsFullyDone} />
              )}

              {tab === "pointcloud" && (
                colmapDone ? (
                  <>
                    <div className="viewer-meta">
                      <span className="viewer-stat">
                        <strong>{colmap.registered_images}</strong> images registered
                      </span>
                      <span className="viewer-stat">
                        <strong>{colmap.points3D?.toLocaleString()}</strong> 3D points
                      </span>
                      <span className="viewer-stat" style={{ color: "#f5a623" }}>
                        ● camera positions
                      </span>
                    </div>
                    <PointCloudViewer
                      jobId={activeJob.job_id}
                      cameraPositions={colmap.camera_positions || []}
                    />
                    <a className="download-btn" href={plyUrl(activeJob.job_id)} download>
                      ↓ Download point cloud (.ply)
                    </a>
                  </>
                ) : (
                  <div style={{ display: "flex", alignItems: "center", gap: 10, color: "var(--text-secondary)", fontSize: 12 }}>
                    {activeJob.stage === "colmap" && <div className="spinner" />}
                    <span>
                      {activeJob.stage === "colmap"
                        ? "Point cloud generation is ongoing — this can take several minutes for large image sets…"
                        : "Point cloud appears after COLMAP finishes."}
                    </span>
                  </div>
                )
              )}

              {tab === "splat" && (
                <>
                  {gaussianDone ? (
                    <>
                      <SplatViewer jobId={activeJob.job_id} />
                      <a className="download-btn" href={splatPlyUrl(activeJob.job_id)} download>
                        ↓ Download Gaussian splat (.ply)
                      </a>
                    </>
                  ) : gaussianRunning ? (
                    <div style={{ display: "flex", alignItems: "center", gap: 10, color: "var(--text-secondary)", fontSize: 12 }}>
                      <div className="spinner" />
                      <span>Training Gaussian Splat — {activeJob.progress || 0}% — this takes a while…</span>
                    </div>
                  ) : (
                    <p className="muted">Gaussian splat appears after training completes.</p>
                  )}
                </>
              )}

              {/* Compact status card — kept for quick glance / manual re-run controls */}
              {colmapDone && (
                <GaussianSplatSection jobId={activeJob.job_id} />
              )}

              {activeJob.status === "failed" && activeJob.error && (
                <div className="error-box" style={{ marginTop: 16, display: "flex", alignItems: "flex-start", gap: 10 }}>
                  <span style={{ fontSize: 16 }}>⚠</span>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 600, marginBottom: 4 }}>Pipeline failed</div>
                    <div style={{ fontSize: 12, opacity: 0.85 }}>{activeJob.error}</div>
                  </div>
                  <button className="primary" onClick={handleResume} disabled={resuming}>
                    {resuming ? "Resuming…" : `Resume from ${activeJob.stage}`}
                  </button>
                </div>
              )}
            </div>
          </>
        )}
      </main>
    </div>
  );
}