// GaussianSplatViewer.jsx
// Embeds an interactive Gaussian Splat viewer using superspl.at/editor
// Usage: <GaussianSplatViewer jobId={jobId} />

import { useState, useEffect } from "react";

const API = "http://localhost:8000";

export default function GaussianSplatViewer({ jobId }) {
  const [status, setStatus] = useState("checking");
  const [viewerUrl, setViewerUrl] = useState(null);
  const pollRef = { current: null };

  useEffect(() => {
    if (!jobId) return;
    checkStatus();
    return () => clearInterval(pollRef.current);
  }, [jobId]);

  function buildViewerUrl() {
    const plyUrl = encodeURIComponent(`${API}/jobs/${jobId}/gaussian-splat/download`);
    return `https://superspl.at/editor?load=${plyUrl}`;
  }

  async function checkStatus() {
    try {
      const res = await fetch(`${API}/jobs/${jobId}/gaussian-splat/status`);
      const data = await res.json();
      if (data.status === "done") {
        setStatus("done");
        setViewerUrl(buildViewerUrl());
      } else if (data.status === "running") {
        setStatus("running");
        pollRef.current = setInterval(async () => {
          const r = await fetch(`${API}/jobs/${jobId}/gaussian-splat/status`);
          const d = await r.json();
          if (d.status === "done") {
            setStatus("done");
            setViewerUrl(buildViewerUrl());
            clearInterval(pollRef.current);
          }
        }, 5000);
      } else {
        setStatus("not_started");
      }
    } catch {
      setStatus("not_started");
    }
  }

  async function handleStart() {
    setStatus("running");
    try {
      await fetch(`${API}/jobs/${jobId}/gaussian-splat`, { method: "POST" });
      pollRef.current = setInterval(async () => {
        const r = await fetch(`${API}/jobs/${jobId}/gaussian-splat/status`);
        const d = await r.json();
        if (d.status === "done") {
          setStatus("done");
          setViewerUrl(buildViewerUrl());
          clearInterval(pollRef.current);
        }
      }, 5000);
    } catch {
      setStatus("error");
    }
  }

  function handleDownload() {
    window.open(`${API}/jobs/${jobId}/gaussian-splat/download`, "_blank");
  }

  if (status === "checking") return null;

  return (
    <div style={{ marginTop: 16 }}>
      <div style={{
        background: "#f0f0ff", border: "1px solid #c0b8f8",
        borderRadius: 10, padding: "16px 20px", marginBottom: 12,
        display: "flex", alignItems: "center", gap: 12,
      }}>
        <span style={{ fontSize: 18, color: "#7c6af7" }}>✦</span>
        <div style={{ flex: 1 }}>
          <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600, color: "#333" }}>
            Gaussian Splat
          </h3>
          <p style={{ margin: "2px 0 0", fontSize: 12, color: "#888" }}>
            {status === "not_started" && "Not started — click to train"}
            {status === "running"     && "Training in progress, this takes a few minutes…"}
            {status === "done"        && "Complete — interactive viewer below"}
            {status === "error"       && "Failed — check backend logs"}
          </p>
        </div>

        {status === "not_started" && (
          <button onClick={handleStart} style={{
            background: "#7c6af7", color: "#fff", border: "none",
            borderRadius: 6, padding: "8px 18px", fontSize: 13,
            fontWeight: 600, cursor: "pointer", whiteSpace: "nowrap",
          }}>Run Splat</button>
        )}
        {status === "running" && (
          <div style={{
            width: 18, height: 18, border: "2px solid #ddd",
            borderTop: "2px solid #7c6af7", borderRadius: "50%",
            animation: "spin 1s linear infinite", flexShrink: 0,
          }} />
        )}
        {status === "done" && (
          <button onClick={handleDownload} style={{
            background: "transparent", color: "#7c6af7",
            border: "1px solid #7c6af7", borderRadius: 6,
            padding: "7px 14px", fontSize: 12, fontWeight: 600,
            cursor: "pointer", whiteSpace: "nowrap",
          }}>Download .ply</button>
        )}
      </div>

      {/* Inline viewer — opens superspl.at/editor with your splat preloaded */}
      {status === "done" && viewerUrl && (
        <div style={{
          border: "1px solid #ddd", borderRadius: 10, overflow: "hidden",
          height: 500, background: "#000",
        }}>
          <iframe
            src={viewerUrl}
            style={{ width: "100%", height: "100%", border: "none" }}
            title="Gaussian Splat Viewer"
            allow="accelerometer; gyroscope"
          />
        </div>
      )}

      {/* Fallback: download and open manually */}
      {status === "done" && (
        <p style={{ fontSize: 11, color: "#aaa", marginTop: 8, textAlign: "center" }}>
          If the viewer doesn't load automatically, download the .ply and open it at{" "}
          <a href="https://superspl.at/editor" target="_blank" rel="noreferrer"
             style={{ color: "#7c6af7" }}>superspl.at/editor</a>
        </p>
      )}
    </div>
  );
}