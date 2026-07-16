import { useState, useEffect, useRef } from "react";
import { getJob, plyUrl, splatPlyUrl } from "../api";

export default function GaussianSplatSection({ jobId }) {
  const [status, setStatus] = useState("idle");
  const [ply, setPly] = useState(null);
  const [errorMsg, setErrorMsg] = useState("");
  const pollRef = useRef(null);

  useEffect(() => {
    if (!jobId) return;

    syncFromJob();

    return () => {
      clearInterval(pollRef.current);
    };
  }, [jobId]);

  async function syncFromJob() {
    try {
      const job = await getJob(jobId);
      applyJobState(job);
    } catch {
      // Silently ignore sync errors
    }
  }

  function applyJobState(job) {
    const stage = job.stage ?? "";
    const jobStatus = job.status ?? "pending";
    const progress = job.progress ?? 0;

    if (jobStatus === "failed") {
      setStatus("error");
      setErrorMsg(job.error || "Pipeline failed");

      clearInterval(pollRef.current);
      return;
    }

    // FastGS training is complete when pipeline progress reaches 80.
    // tasks.py sets summary.splat_ply = true when the trained
    // Gaussian Splat PLY file is ready.
    const gsComplete = progress >= 80;

    if (jobStatus === "done" || gsComplete) {
      setStatus("done");

      try {
        const summary =
          typeof job.summary === "string"
            ? JSON.parse(job.summary)
            : job.summary ?? {};

        setPly(
          summary.splat_ply
            ? splatPlyUrl(jobId)
            : plyUrl(jobId)
        );
      } catch {
        setPly(splatPlyUrl(jobId));
      }

      clearInterval(pollRef.current);
      return;
    }

    if (
      jobStatus === "running" &&
      stage === "gaussian_splat"
    ) {
      setStatus("running");
      startPolling();
      return;
    }

    setStatus("idle");
  }

  function startPolling() {
    clearInterval(pollRef.current);

    pollRef.current = setInterval(async () => {
      try {
        const job = await getJob(jobId);
        applyJobState(job);
      } catch {
        // Silently ignore polling errors
      }
    }, 3000);
  }

  const statusMeta =
    {
      idle: {
        label: "Not started",
        badgeClass: "badge pending",
      },
      running: {
        label: "Running",
        badgeClass: "badge running",
      },
      done: {
        label: "Complete",
        badgeClass: "badge done",
      },
      error: {
        label: "Failed",
        badgeClass: "badge failed",
      },
    }[status] ?? {
      label: status,
      badgeClass: "badge pending",
    };

  return (
    <div className="splat-section">
      <div className="splat-header">
        <div className="splat-icon">✦</div>

        <span className="splat-title">
          Gaussian Splatting
        </span>

        <span
          className={statusMeta.badgeClass}
          style={{ marginLeft: "auto" }}
        >
          {statusMeta.label}
        </span>
      </div>

      <p className="splat-desc">
        Generates a photorealistic 3D Gaussian Splat from the COLMAP
        reconstruction. FastGS trains on the sparse point cloud and
        cubemap images.
      </p>

      {status === "idle" && (
        <p
          className="muted"
          style={{ fontSize: 12 }}
        >
          Waiting for pipeline to reach Gaussian Splatting stage…
        </p>
      )}

      {status === "running" && (
        <div className="splat-actions">
          <div className="spinner" />

          <span
            className="muted"
            style={{ fontSize: 12 }}
          >
            Training in progress — this takes 1–2 minutes…
          </span>
        </div>
      )}

      {status === "done" && (
        <div className="splat-actions">
          <span
            style={{
              color: "var(--success)",
              fontSize: 14,
            }}
          >
            ✓
          </span>

          <span
            style={{
              fontSize: 13,
              color: "var(--success)",
            }}
          >
            Splat ready
          </span>

          {ply && (
            <a
              href={ply}
              target="_blank"
              rel="noreferrer"
              className="download-btn"
              style={{ marginLeft: "auto" }}
            >
              ↓ Download .ply
            </a>
          )}
        </div>
      )}

      {status === "error" && (
        <div className="error-box">
          <span style={{ fontSize: 16 }}>
            ⚠
          </span>

          <span>
            {errorMsg || "Unknown error"}
          </span>
        </div>
      )}
    </div>
  );
}