import { useState, useEffect, useMemo } from "react";
import JSZip from "jszip";
import { API } from "../api";

function faceLabel(face) {
  if (face === "original") return "Original";
  const m = face.match(/^yaw(-?\d+)_pitch(-?\d+)$/);
  if (!m) return face;
  return `${m[1]}° / ${m[2]}°`;
}

export default function CubemapGallery({ jobId, cubemapsFullyDone = false }) {
  const [cubemaps, setCubemaps] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [zipping, setZipping] = useState(false);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);

    async function load() {
      try {
        const res = await fetch(`${API}/jobs/${jobId}/cubemaps`);
        if (res.status === 404) {
          if (!cancelled) { setCubemaps([]); setError(null); }
          return;
        }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (!cancelled) { setCubemaps(data.cubemaps ?? []); setError(null); }
      } catch (e) {
        if (!cancelled) setError(e.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();

    // Stop polling once cubemaps are fully done — no need to keep hitting
    // the endpoint after the stage has moved on.
    if (cubemapsFullyDone) return () => { cancelled = true; };

    const interval = setInterval(load, 2000);
    return () => { cancelled = true; clearInterval(interval); };
  }, [jobId, cubemapsFullyDone]);

  const grouped = useMemo(() => {
    const g = {};
    for (const cm of cubemaps) {
      const src = cm.source_image ?? "unknown";
      if (!g[src]) g[src] = [];
      g[src].push(cm);
    }
    return g;
  }, [cubemaps]);

  async function handleDownloadAll() {
    if (cubemaps.length === 0 || !cubemapsFullyDone) return;
    setZipping(true);
    try {
      const zip = new JSZip();
      await Promise.all(
        cubemaps.map(async (cm) => {
          const res = await fetch(`${API}${cm.url}`);
          const blob = await res.blob();
          const src = (cm.source_image ?? "unknown").replace(/\.[^/.]+$/, "");
          const ext = cm.url.split(".").pop();
          zip.file(`${src}/${cm.face}.${ext}`, blob);
        })
      );
      const content = await zip.generateAsync({ type: "blob" });
      const url = URL.createObjectURL(content);
      const a = document.createElement("a");
      a.href = url;
      a.download = `cubemaps-${jobId}.zip`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error("Zip failed", e);
    } finally {
      setZipping(false);
    }
  }

  if (loading) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "16px 0", color: "var(--text-secondary)", fontSize: 12 }}>
        <div className="spinner" />
        Loading…
      </div>
    );
  }

  if (error) {
    return (
      <div className="error-box">
        <span>⚠</span>
        <span>Could not load cubemaps: {error}</span>
      </div>
    );
  }

  if (cubemaps.length === 0) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "16px 0", color: "var(--text-secondary)", fontSize: 12 }}>
        <div className="spinner" />
        Generating perspective views from panoramas…
      </div>
    );
  }

  const sourceCount = Object.keys(grouped).length;
  const downloadDisabled = zipping || !cubemapsFullyDone;

  return (
    <div>
      <div className="cubemap-toolbar">
        <span className="cubemap-count">
          {cubemaps.length} view{cubemaps.length !== 1 ? "s" : ""} ·{" "}
          {sourceCount} source image{sourceCount !== 1 ? "s" : ""}
          {!cubemapsFullyDone && (
            <span style={{ marginLeft: 8, color: "var(--accent)" }}>· generating…</span>
          )}
        </span>
        <button
          className="btn btn-ghost"
          onClick={handleDownloadAll}
          disabled={downloadDisabled}
          title={!cubemapsFullyDone ? "Wait until all views finish generating" : undefined}
        >
          {zipping ? (<><div className="spinner" /> Zipping…</>) : (<>↓ Download all</>)}
        </button>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {Object.entries(grouped).map(([src, views]) => (
          <div key={src}>
            <div className="cubemap-source-label">
              {src} <span style={{ opacity: 0.6 }}>· {views.length} views</span>
            </div>
            <div className="cubemap-grid">
              {views.map((cm) => (
                <div key={cm.face} className="cubemap-tile">
                  <img
                    src={`${API}${cm.url}`}
                    alt={faceLabel(cm.face)}
                    loading="lazy"
                    onError={(e) => { e.target.style.display = "none"; }}
                  />
                  <div className="cubemap-tile-label">{faceLabel(cm.face)}</div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}