import { useEffect, useRef, useState, Component } from "react";
import * as GaussianSplats3D from "@mkkellogg/gaussian-splats-3d";
import { splatPlyUrl, apiFetch } from "../api";

// Renders the ACTUAL trained Gaussian splat (ellipsoids, color, opacity) —
// not just a point cloud of centers. Auto-loads the job's .ply on mount.
//
// FIX 1: the library detects file format from the URL's extension. Our
// backend serves the file at /jobs/{id}/splat with no ".ply" anywhere in
// the path, so format auto-detection failed with "File format not
// supported" and threw inside a useEffect. Fixed by explicitly passing
// `format: GaussianSplats3D.SceneFormat.Ply`.
//
// FIX 2: addSplatScene() fetches the URL internally, with no way to attach
// custom headers. Since the backend is behind ngrok's free-tier warning
// page, that internal fetch was getting HTML back instead of the PLY
// binary. Fixed by fetching the PLY ourselves via apiFetch (which does
// carry the ngrok-skip-browser-warning header), turning it into a blob
// URL, and handing that local blob URL to addSplatScene instead of the
// raw ngrok URL.
//
// Also wrapped in a real React error boundary (SplatBoundary below) so any
// future failure here shows an inline error card instead of crashing the
// whole app.

class SplatBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }
  static getDerivedStateFromError() {
    return { hasError: true };
  }
  componentDidCatch(error, info) {
    console.error("[RealSplatViewer] boundary caught:", error, info);
    this.props.onCrash?.(error?.message || "Unknown error in splat viewer");
  }
  render() {
    if (this.state.hasError) return null; // parent renders the error card
    return this.props.children;
  }
}

function InnerSplatViewer({ jobId, onError }) {
  const containerRef = useRef(null);
  const viewerRef = useRef(null);
  const [status, setStatus] = useState("loading"); // loading | ready | error
  const [errorMsg, setErrorMsg] = useState("");

  useEffect(() => {
    if (!jobId || !containerRef.current) return;

    let cancelled = false;
    let blobUrl = null;
    setStatus("loading");
    setErrorMsg("");

    const viewer = new GaussianSplats3D.Viewer({
      cameraUp: [0, -1, 0],
      initialCameraPosition: [0, 0, 5],
      initialCameraLookAt: [0, 0, 0],
      rootElement: containerRef.current,
      selfDrivenMode: true,
      useBuiltInControls: true,
      sharedMemoryForWorkers: false,
    });
    viewerRef.current = viewer;

    apiFetch(splatPlyUrl(jobId))
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.blob();
      })
      .then((blob) => {
        if (cancelled) return Promise.reject(new Error("cancelled"));
        blobUrl = URL.createObjectURL(blob);
        return viewer.addSplatScene(blobUrl, {
          // Explicit format — the blob URL has no file extension for the
          // library to auto-detect from, same reason as the original fix.
          format: GaussianSplats3D.SceneFormat.Ply,
          splatAlphaRemovalThreshold: 5,
          showLoadingUI: true,
          position: [0, 0, 0],
          rotation: [0, 0, 0, 1],
          scale: [1, 1, 1],
        });
      })
      .then(() => {
        if (cancelled) return;
        viewer.start();
        setStatus("ready");
      })
      .catch((err) => {
        if (cancelled) return;
        console.error("[RealSplatViewer] failed to load splat:", err);
        const msg = err?.message || "Failed to load splat";
        setErrorMsg(msg);
        setStatus("error");
        onError?.(msg);
      });

    return () => {
      cancelled = true;
      try {
        viewer.dispose();
      } catch (e) {
        // viewer may already be torn down — safe to ignore
      }
      viewerRef.current = null;
      if (containerRef.current) containerRef.current.innerHTML = "";
      if (blobUrl) URL.revokeObjectURL(blobUrl);
    };
  }, [jobId]);

  return (
    <div style={{ position: "relative" }}>
      {status === "loading" && (
        <div style={{
          position: "absolute", top: 0, left: 0, right: 0, bottom: 0,
          display: "flex", alignItems: "center", justifyContent: "center",
          gap: 10, color: "var(--text-secondary)", fontSize: 12,
          background: "var(--bg-base, #0a0a0f)", zIndex: 5,
        }}>
          <div className="spinner" />
          <span>Loading splat — this may take a moment for large scenes…</span>
        </div>
      )}

      {status === "error" && (
        <div className="error-box" style={{ margin: "12px 0" }}>
          <span style={{ fontSize: 16 }}>⚠</span>
          <span>{errorMsg}</span>
        </div>
      )}

      <div
        ref={containerRef}
        style={{
          width: "100%",
          height: 560,
          borderRadius: 8,
          overflow: "hidden",
          background: "#000",
          display: status === "error" ? "none" : "block",
        }}
      />

      {status === "ready" && (
        <p className="muted" style={{ fontSize: 11, marginTop: 8 }}>
          Drag to orbit, scroll to zoom, right-drag to pan.
        </p>
      )}
    </div>
  );
}

export default function RealSplatViewer({ jobId }) {
  const [crashed, setCrashed] = useState(false);
  const [crashMsg, setCrashMsg] = useState("");

  const handleCrash = (msg) => {
    setCrashed(true);
    setCrashMsg(msg);
  };

  if (crashed) {
    return (
      <div className="error-box">
        <span style={{ fontSize: 16 }}>⚠</span>
        <div>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>Splat viewer crashed</div>
          <div style={{ fontSize: 12, opacity: 0.85 }}>{crashMsg}</div>
        </div>
      </div>
    );
  }

  return (
    <SplatBoundary onCrash={handleCrash}>
      <InnerSplatViewer jobId={jobId} onError={handleCrash} />
    </SplatBoundary>
  );
}