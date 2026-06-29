// StorageManager.jsx
// Shows all jobs organized by scene name with storage usage and delete buttons
// Usage: <StorageManager onSelectJob={(job) => ...} />

import { useState, useEffect } from "react";

const API = "http://localhost:8000";

function fmt(mb) {
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
  return `${mb} MB`;
}

function statusColor(s) {
  return {
    done: "#2e7d32", failed: "#c62828", running: "#1a73e8",
    queued: "#e65100", complete: "#2e7d32",
  }[s] || "#666";
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
    } catch {}
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

  if (loading) return <p className="muted">Loading storage info…</p>;

  return (
    <div>
      <div style={{
        display: "flex", justifyContent: "space-between",
        alignItems: "center", marginBottom: 12,
      }}>
        <span style={{ fontSize: 12, color: "#888" }}>
          Total used: <strong>{fmt(totalMb)}</strong>
        </span>
        <button onClick={load} style={{
          background: "transparent", border: "1px solid #ddd",
          borderRadius: 6, padding: "4px 12px", fontSize: 12,
          cursor: "pointer", color: "#666",
        }}>↻ Refresh</button>
      </div>

      {Object.entries(grouped).map(([sceneName, sceneJobs]) => (
        <div key={sceneName} style={{
          border: "1px solid #e0e0e0", borderRadius: 8,
          marginBottom: 12, overflow: "hidden",
        }}>
          <div style={{
            background: "#f8f8f8", padding: "8px 14px",
            borderBottom: "1px solid #e0e0e0",
            display: "flex", alignItems: "center", gap: 8,
          }}>
            <span style={{ fontWeight: 600, fontSize: 14, flex: 1 }}>{sceneName}</span>
            <span style={{ fontSize: 11, color: "#888" }}>
              {sceneJobs.length} run{sceneJobs.length > 1 ? "s" : ""}
            </span>
          </div>

          {sceneJobs.map(j => (
            <div key={j.job_id} style={{
              display: "flex", alignItems: "center", gap: 8,
              padding: "8px 14px", borderBottom: "1px solid #f0f0f0",
              fontSize: 12,
            }}>
              <span style={{
                color: statusColor(j.status), fontWeight: 600,
                minWidth: 60,
              }}>{j.status}</span>

              <span style={{ color: "#888", flex: 1 }}>
                {j.created_at ? new Date(j.created_at).toLocaleString() : "—"}
              </span>

              <span style={{ color: "#888", minWidth: 90, textAlign: "right" }}>
                ↑{fmt(j.upload_mb)} / ↓{fmt(j.output_mb)}
              </span>

              <button
                onClick={() => onSelectJob && onSelectJob(j.job_id)}
                style={{
                  background: "transparent", color: "#7c6af7",
                  border: "1px solid #7c6af7", borderRadius: 5,
                  padding: "3px 10px", fontSize: 11, cursor: "pointer",
                }}>View</button>

              <button
                onClick={() => handleDelete(j.job_id, sceneName)}
                disabled={deleting === j.job_id}
                style={{
                  background: "transparent", color: "#c62828",
                  border: "1px solid #c62828", borderRadius: 5,
                  padding: "3px 10px", fontSize: 11, cursor: "pointer",
                  opacity: deleting === j.job_id ? 0.5 : 1,
                }}>
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