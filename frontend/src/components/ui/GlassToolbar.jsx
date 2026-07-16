/*
  GlassToolbar — purely presentational floating control bar, meant to sit
  on top of your existing Three.js canvas (SplatViewer / PointCloudViewer).

  It is a positioning + styling wrapper only. Pass your existing buttons/
  controls in as children — their onClick handlers, state, and logic are
  untouched.

  Usage (inside your existing viewer component's return, unchanged JSX
  just wrapped):

    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      <canvas ref={canvasRef} />  // existing Three.js canvas, untouched

      <GlassToolbar position="bottom-center">
        <ToolbarButton active={showCameras} onClick={toggleCameras} label="Cameras" />
        <ToolbarButton onClick={downloadPly} label="Download PLY" />
      </GlassToolbar>

      <HUDCorner stats={{ Points: pointCount, Cameras: cameraCount }} />
    </div>
*/

const POSITIONS = {
  "top-left": { top: "16px", left: "16px" },
  "top-right": { top: "16px", right: "16px" },
  "bottom-left": { bottom: "16px", left: "16px" },
  "bottom-right": { bottom: "16px", right: "16px" },
  "bottom-center": { bottom: "16px", left: "50%", transform: "translateX(-50%)" },
  "top-center": { top: "16px", left: "50%", transform: "translateX(-50%)" },
};

export function GlassToolbar({ position = "bottom-center", children, className = "" }) {
  const posStyle = POSITIONS[position] || POSITIONS["bottom-center"];

  return (
    <div
      className={`glass-panel ${className}`}
      style={{
        position: "absolute",
        ...posStyle,
        display: "flex",
        alignItems: "center",
        gap: "4px",
        padding: "6px",
        zIndex: 10,
      }}
    >
      {children}
    </div>
  );
}

export function ToolbarButton({ active = false, onClick, label, icon, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={label}
      aria-pressed={active}
      className={`btn-icon ${active ? "btn-icon--active" : ""}`}
    >
      {icon || children || label?.[0]}
    </button>
  );
}

/* Small stats overlay for the corner of the 3D viewer — point count,
   camera count, reconstruction stats, all monospace per the design spec. */
export function HUDCorner({ stats = {}, position = "top-right" }) {
  const posStyle = POSITIONS[position] || POSITIONS["top-right"];
  const entries = Object.entries(stats);

  if (!entries.length) return null;

  return (
    <div
      className="glass-panel"
      style={{
        position: "absolute",
        ...posStyle,
        padding: "10px 14px",
        display: "flex",
        gap: "16px",
        zIndex: 10,
      }}
    >
      {entries.map(([label, value]) => (
        <div className="hud-stat" key={label}>
          <span className="hud-stat__label">{label}</span>
          <span className="hud-stat__value">{value}</span>
        </div>
      ))}
    </div>
  );
}