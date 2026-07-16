/*
  EmptyState — purely presentational. Use anywhere a panel would otherwise
  render blank: no scenes yet, no cubemaps yet, viewer with nothing loaded.

  Usage:
    <EmptyState
      title="No reconstruction yet"
      description="Upload 360° captures to begin the pipeline."
      icon={<UploadIcon />}
    />
*/
export function EmptyState({ title, description, icon, action, className = "" }) {
  return (
    <div
      className={className}
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        textAlign: "center",
        gap: "var(--space-2)",
        padding: "var(--space-6)",
        color: "var(--text-secondary)",
        height: "100%",
        minHeight: "180px",
      }}
    >
      {icon && (
        <div style={{ color: "var(--text-dim)", marginBottom: "var(--space-1)" }}>
          {icon}
        </div>
      )}
      <div style={{ color: "var(--text-primary)", fontSize: "14px", fontWeight: 500 }}>
        {title}
      </div>
      {description && (
        <div style={{ fontSize: "12px", color: "var(--text-dim)", maxWidth: "320px" }}>
          {description}
        </div>
      )}
      {action && <div style={{ marginTop: "var(--space-2)" }}>{action}</div>}
    </div>
  );
}

/*
  Skeleton — purely presentational shimmering placeholder.

  Usage:
    <Skeleton width="100%" height="120px" />
    <Skeleton width="60px" height="60px" radius="50%" />
*/
export function Skeleton({ width = "100%", height = "16px", radius, className = "" }) {
  return (
    <div
      className={`skeleton ${className}`}
      style={{ width, height, borderRadius: radius || "var(--radius-sm)" }}
      aria-hidden="true"
    />
  );
}

/* Prebuilt skeleton grid for the cubemap gallery loading state */
export function CubemapGallerySkeleton({ count = 6 }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))",
        gap: "var(--space-3)",
      }}
    >
      {Array.from({ length: count }).map((_, i) => (
        <Skeleton key={i} height="120px" radius="var(--radius-md)" />
      ))}
    </div>
  );
}