import { useEffect, useRef, useState, Component } from "react";
import * as GaussianSplats3D from "@mkkellogg/gaussian-splats-3d";
import { splatPlyUrl, apiFetch } from "../api";
import { resolveViewerInternals, createEvidenceMarkers, clearEvidenceMarkers, setupPicking } from "./EvidenceOverlay";

class EvidenceBoundary extends Component {
  constructor(props) { super(props); this.state = { hasError: false }; }
  static getDerivedStateFromError() { return { hasError: true }; }
  componentDidCatch(error, info) {
    console.error("[EvidenceSplatViewer] boundary caught:", error, info);
    this.props.onCrash?.(error?.message || "Unknown error in evidence splat viewer");
  }
  render() { return this.state.hasError ? null : this.props.children; }
}

function InnerEvidenceSplatViewer({ jobId, evidence, selectedId, onSelect, onError }) {
  const containerRef = useRef(null);
  const viewerRef = useRef(null);
  const internalsRef = useRef(null); // { scene, camera, renderer }
  const markersRef = useRef({});
  const cleanupPickingRef = useRef(null);
  const [status, setStatus] = useState("loading");
  const [errorMsg, setErrorMsg] = useState("");
  const [hoveredId, setHoveredId] = useState(null);

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

        // Resolve internals + attach markers once the viewer is actually running
        const internals = resolveViewerInternals(viewer);
        internalsRef.current = internals;
        markersRef.current = createEvidenceMarkers(internals.scene, evidence || [], selectedId);

        cleanupPickingRef.current = setupPicking(
          internals.renderer, internals.camera, () => markersRef.current,
          { onHover: setHoveredId, onClick: onSelect }
        );

        setStatus("ready");
      })
      .catch((err) => {
        if (cancelled) return;
        console.error("[EvidenceSplatViewer] failed to load:", err);
        const msg = err?.message || "Failed to load splat";
        setErrorMsg(msg);
        setStatus("error");
        onError?.(msg);
      });

    return () => {
      cancelled = true;
      cleanupPickingRef.current?.();
      if (internalsRef.current) {
        clearEvidenceMarkers(internalsRef.current.scene, markersRef.current);
      }
      try { viewer.dispose(); } catch (e) { /* already torn down */ }
      viewerRef.current = null;
      if (containerRef.current) containerRef.current.innerHTML = "";
      if (blobUrl) URL.revokeObjectURL(blobUrl);
    };
  }, [jobId]);

  // Update markers when evidence data or selection changes, without reloading the splat
  useEffect(() => {
    if (status !== "ready" || !internalsRef.current) return;
    clearEvidenceMarkers(internalsRef.current.scene, markersRef.current);
    markersRef.current = createEvidenceMarkers(internalsRef.current.scene, evidence || [], selectedId);
  }, [evidence, selectedId, status]);

  const hoveredItem = hoveredId ? evidence?.find((e) => e.id === hoveredId) : null;

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
          <span>Loading splat with evidence markers…</span>
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
          width: "100%", height: 480, borderRadius: 8, overflow: "hidden",
          background: "#000", display: status === "error" ? "none" : "block",
        }}
      />

      {hoveredItem && (
        <div style={{
          position: "absolute", bottom: 12, left: 12, background: "rgba(20,23,28,0.9)",
          color: "#fff", padding: "8px 12px", borderRadius: 6, fontSize: 12, pointerEvents: "none",
        }}>
          <strong>{hoveredItem.label}</strong>
          {hoveredItem.classification && <> — {hoveredItem.classification} ({(hoveredItem.classification_confidence ?? 0).toFixed(2)})</>}
        </div>
      )}

      {status === "ready" && (
        <p className="muted" style={{ fontSize: 11, marginTop: 8 }}>
          Drag to orbit, scroll to zoom, right-drag to pan. Click a marker or table row below to highlight it.
        </p>
      )}
    </div>
  );
}

export default function EvidenceSplatViewer({ jobId, evidence, selectedId, onSelect }) {
  const [crashed, setCrashed] = useState(false);
  const [crashMsg, setCrashMsg] = useState("");

  const handleCrash = (msg) => { setCrashed(true); setCrashMsg(msg); };

  if (crashed) {
    return (
      <div className="error-box">
        <span style={{ fontSize: 16 }}>⚠</span>
        <div>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>Evidence splat viewer crashed</div>
          <div style={{ fontSize: 12, opacity: 0.85 }}>{crashMsg}</div>
        </div>
      </div>
    );
  }

  return (
    <EvidenceBoundary onCrash={handleCrash}>
      <InnerEvidenceSplatViewer jobId={jobId} evidence={evidence} selectedId={selectedId} onSelect={onSelect} onError={handleCrash} />
    </EvidenceBoundary>
  );
}