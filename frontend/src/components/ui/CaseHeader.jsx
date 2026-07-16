/*
  CaseHeader — purely presentational persistent top bar. Pass in whatever
  metadata you already have from your existing job/scene state; this
  component does not fetch or derive anything.

  Usage:
    <CaseHeader
      caseId="FD-2026-0143"
      sceneName={job.scene_name}
      captureDate={job.created_at}
      status={job.status}
    />
*/
import StatusChip from "./StatusChip";

function MetaField({ label, value }) {
  if (!value) return null;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1px" }}>
      <span
        style={{
          fontSize: "10px",
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          color: "var(--text-dim)",
        }}
      >
        {label}
      </span>
      <span className="mono" style={{ fontSize: "12px", color: "var(--text-secondary)" }}>
        {value}
      </span>
    </div>
  );
}

export default function CaseHeader({
  caseId,
  sceneName,
  captureDate,
  status,
  logo,
  className = "",
}) {
  return (
    <header
      className={`hairline-bottom ${className}`}
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "10px var(--space-4)",
        background: "var(--bg-surface)",
        gap: "var(--space-4)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
        {logo}
        <div>
          <div style={{ fontSize: "13px", fontWeight: 600, color: "var(--text-primary)" }}>
            {sceneName || "Untitled scene"}
          </div>
          {caseId && (
            <div className="mono" style={{ fontSize: "11px", color: "var(--text-dim)" }}>
              {caseId}
            </div>
          )}
        </div>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-4)" }}>
        <MetaField label="Captured" value={captureDate} />
        {status && <StatusChip status={status} label={status} />}
      </div>
    </header>
  );
}