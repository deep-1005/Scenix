// StorageManager.jsx
// Shows all jobs organized by scene name with storage usage and delete buttons
// Logic is unchanged from the original — only styling/markup updated to match the dark theme.

import { useState, useEffect } from "react";
import { API } from "../api";

function fmt(mb) {
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
  return `${mb} MB`;
}

function statusBadgeClass(s) {
  return {
    done: "badge done",
    complete: "badge complete",
    failed: "badge failed",
    running: "badge running",
    queued: "badge pending",
  }[s] || "badge pending";
}

export default function StorageManager({ onSelectJob }) {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(null);

  useEffect(() => { load(); }, []);

  async function load() {
    setLoading(true);
    try {
      const res = await fetch(`${API}/storage/summary`);
      setJobs(await res.json());
    } catch { }
    setLoading(false);
  }

  async function handleDelete(jobId, sceneName) {
    if (!confirm(`Delete "${sceneName}" and all its files? This cannot be undone.`)) return;
    setDeleting(jobId);
    try {
      await fetch(`${API}/jobs/${jobId}`, { method: "DELETE" });
      setJobs(j => j.filter(x => x.job_id !== jobId));
    } catch (e) {
      alert("Delete failed: " + e.message);
    }
    setDeleting(null);
  }

  // Group by scene name
  const grouped = jobs.reduce((acc, j) => {
    const key = j.scene_name || "(unnamed)";
    if (!acc[key]) acc[key] = [];
    acc[key].push(j);
    return acc;
  }, {});

  const totalMb = jobs.reduce((s, j) => s + j.upload_mb + j.output_mb, 0);

  if (loading) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "16px 0", color: "var(--text-secondary)", fontSize: 12 }}>
        <div className="spinner" />
        Loading storage info…
      </div>
    );
  }

  return (
    <div className="storage-manager">
      <div className="storage-toolbar">
        <span className="storage-total">
          Total used: <strong>{fmt(totalMb)}</strong>
        </span>
        <button className="btn btn-ghost" onClick={load}>↻ Refresh</button>
      </div>

      {Object.entries(grouped).map(([sceneName, sceneJobs]) => (
        <div key={sceneName} className="storage-group">
          <div className="storage-group-header">
            <span className="storage-group-name">{sceneName}</span>
            <span className="storage-group-count">
              {sceneJobs.length} run{sceneJobs.length > 1 ? "s" : ""}
            </span>
          </div>

          {sceneJobs.map(j => (
            <div key={j.job_id} className="storage-row">
              <span className={statusBadgeClass(j.status)}>{j.status}</span>

              <span className="storage-row-date">
                {j.created_at ? new Date(j.created_at).toLocaleString() : "—"}
              </span>

              <span className="storage-row-size">
                ↑{fmt(j.upload_mb)} / ↓{fmt(j.output_mb)}
              </span>

              <button
                className="btn btn-ghost btn-sm"
                onClick={() => onSelectJob && onSelectJob(j.job_id)}
              >
                View
              </button>

              <button
                className="btn btn-danger-ghost btn-sm"
                onClick={() => handleDelete(j.job_id, sceneName)}
                disabled={deleting === j.job_id}
              >
                {deleting === j.job_id ? "…" : "Delete"}
              </button>
            </div>
          ))}
        </div>
      ))}

      {jobs.length === 0 && <p className="muted">No scenes yet.</p>}
    </div>
  );
}