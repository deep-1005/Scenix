export default function Toast({ message, kind = "info" }) {
  const icon = { info: "ℹ", success: "✓", error: "⚠" }[kind] || "ℹ";
  return (
    <div className={`toast toast-${kind}`}>
      <span className="toast-icon">{icon}</span>
      <span className="toast-message">{message}</span>
    </div>
  );
}