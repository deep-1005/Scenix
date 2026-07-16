import { useState } from "react";
import StatusChip from "./StatusChip";

/*
  PipelineStepper — purely presentational vertical timeline for the
  12-stage reconstruction pipeline. It renders whatever `stages` you pass
  in; it does not fetch data, poll status, or know about your job model.

  Wire it up from existing logic like this, without changing that logic:

    const stages = [
      { id: "cubemap", label: "Cubemap Generation", status: "complete", elapsedMs: 4200 },
      { id: "colmap_features", label: "Feature Extraction", status: "complete", elapsedMs: 18400 },
      { id: "colmap_matching", label: "Feature Matching", status: "processing", elapsedMs: 9100 },
      { id: "colmap_sfm", label: "Sparse Reconstruction", status: "pending" },
      { id: "gaussian_splat", label: "Gaussian Splatting", status: "pending" },
      { id: "evidence_detection", label: "Evidence Detection", status: "pending" },
      { id: "report", label: "Report Generation", status: "pending" },
      // ...remaining stages from your existing pipeline state
    ];

    <PipelineStepper stages={stages} />

  Each stage object:
    id        (string, required, unique)
    label     (string, required)
    status    ("complete" | "processing" | "failed" | "pending")
    elapsedMs (number, optional) — shown as mono duration
    logs      (string | string[], optional) — shown in expandable panel
*/

function formatDuration(ms) {
  if (ms == null) return null;
  const totalSeconds = Math.round(ms / 1000);
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

function StageIcon({ status }) {
  if (status === "complete") {
    return (
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
        <path
          d="M2.5 7.2L5.5 10.2L11.5 3.8"
          stroke="var(--status-complete)"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    );
  }
  if (status === "failed") {
    return (
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
        <path
          d="M3.5 3.5L10.5 10.5M10.5 3.5L3.5 10.5"
          stroke="var(--status-failed)"
          strokeWidth="1.6"
          strokeLinecap="round"
        />
      </svg>
    );
  }
  if (status === "processing") {
    return <span className="status-chip__dot" style={{ background: "var(--status-processing)", animation: "pulse-dot 1.4s ease-in-out infinite" }} />;
  }
  return <span className="status-chip__dot" style={{ background: "var(--status-pending)" }} />;
}

function StageRow({ stage, isLast }) {
  const [expanded, setExpanded] = useState(false);
  const hasLogs = Boolean(stage.logs && stage.logs.length);
  const duration = formatDuration(stage.elapsedMs);

  return (
    <li style={{ display: "flex", gap: "12px", position: "relative" }}>
      {/* Rail */}
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", width: "20px", flexShrink: 0 }}>
        <div
          style={{
            width: "20px",
            height: "20px",
            borderRadius: "50%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "var(--bg-elevated)",
            border: "1px solid var(--border-hairline-strong)",
            zIndex: 1,
          }}
        >
          <StageIcon status={stage.status} />
        </div>
        {!isLast && (
          <div
            style={{
              width: "1px",
              flex: 1,
              minHeight: "24px",
              background: "var(--border-hairline)",
              marginTop: "2px",
            }}
          />
        )}
      </div>

      {/* Content */}
      <div style={{ paddingBottom: "20px", flex: 1, minWidth: 0 }}>
        <button
          type="button"
          onClick={() => hasLogs && setExpanded((v) => !v)}
          className="btn-icon"
          style={{
            width: "auto",
            height: "auto",
            padding: "6px 8px",
            marginLeft: "-8px",
            display: "flex",
            alignItems: "center",
            gap: "10px",
            cursor: hasLogs ? "pointer" : "default",
            justifyContent: "flex-start",
          }}
          disabled={!hasLogs}
          aria-expanded={expanded}
        >
          <span style={{ color: "var(--text-primary)", fontSize: "13px", fontWeight: 500 }}>
            {stage.label}
          </span>
          <StatusChip status={stage.status} label={stage.status} />
          {duration && <span className="mono" style={{ fontSize: "11px", color: "var(--text-dim)" }}>{duration}</span>}
          {hasLogs && (
            <svg
              width="10"
              height="10"
              viewBox="0 0 10 10"
              style={{ transform: expanded ? "rotate(180deg)" : "none", transition: "transform var(--transition-fast)" }}
            >
              <path d="M2 3.5L5 6.5L8 3.5" stroke="var(--text-dim)" strokeWidth="1.3" fill="none" strokeLinecap="round" />
            </svg>
          )}
        </button>

        {hasLogs && expanded && (
          <pre
            className="mono panel-elevated"
            style={{
              marginTop: "6px",
              padding: "10px 12px",
              fontSize: "11px",
              lineHeight: 1.6,
              color: "var(--text-secondary)",
              maxHeight: "180px",
              overflowY: "auto",
              whiteSpace: "pre-wrap",
            }}
          >
            {Array.isArray(stage.logs) ? stage.logs.join("\n") : stage.logs}
          </pre>
        )}
      </div>
    </li>
  );
}

export default function PipelineStepper({ stages = [], className = "" }) {
  if (!stages.length) {
    return (
      <div className="mono" style={{ color: "var(--text-dim)", fontSize: "12px", padding: "var(--space-4)" }}>
        No pipeline stages to display.
      </div>
    );
  }

  return (
    <ul
      className={className}
      style={{ listStyle: "none", margin: 0, padding: "var(--space-2) 0" }}
    >
      {stages.map((stage, i) => (
        <StageRow key={stage.id} stage={stage} isLast={i === stages.length - 1} />
      ))}
    </ul>
  );
}