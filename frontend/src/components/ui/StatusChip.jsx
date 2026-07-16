/*
  StatusChip — purely presentational. Renders a status pill with a colored dot.
  Drop-in for pipeline stage status, job status, etc.

  Usage:
    <StatusChip status="processing" label="Running COLMAP" />
    <StatusChip status="complete" label="Done" />
    <StatusChip status="failed" label="Failed" />
    <StatusChip status="pending" label="Queued" />

  `status` accepts: "complete" | "processing" | "failed" | "pending"
  Any other value falls back to "pending" styling so this never throws.
*/
export default function StatusChip({ status = "pending", label, className = "" }) {
  const validStatuses = ["complete", "processing", "failed", "pending"];
  const resolvedStatus = validStatuses.includes(status) ? status : "pending";

  return (
    <span className={`status-chip status-chip--${resolvedStatus} ${className}`}>
      <span className="status-chip__dot" />
      {label}
    </span>
  );
}