import { useState, useEffect, useRef } from "react";
import { getJob, plyUrl, splatPlyUrl } from "../api";

export default function GaussianSplatSection({ jobId }) {
  const [status, setStatus]   = useState("idle");
  const [ply, setPly]         = useState(null);
  const [errorMsg, setErrorMsg] = useState("");
  const pollRef = useRef(null);

  // On mount / jobId change — read current job state immediately
  useEffect(() => {
    if (!jobId) return;
    syncFromJob();
    return () => clearInterval(pollRef.current);
  }, [jobId]);

  async function syncFromJob() {
    try {
      const job = await getJob(jobId);
      applyJobState(job);
    } catch (e) {
      // silently ignore — job may not exist yet
    }
  }

  function applyJobState(job) {
    const stage    = job.stage    ?? "";
    const jobStatus = job.status  ?? "pending";

    if (jobStatus === "failed") {
      setStatus("error");
      setErrorMsg(job.error || "Pipeline failed");
      clearInterval(pollRef.current);
      return;
    }

    // Stages before gaussian_splat → still waiting
    const gsStages = ["gaussian_splat", "cleanup", "mesh", "detection",
                      "classify", "measure", "report", "complete"];
    const inGS = gsStages.includes(stage);

    if (jobStatus === "done" || (inGS && stage !== "gaussian_splat")) {
      // Job finished — find the splat ply url
      setStatus("done");
      try {
        const summary = typeof job.summary === "string"
          ? JSON.parse(job.summary) : (job.summary ?? {});
        if (summary.splat_ply) {
          // splat_ply is an absolute path; serve it via /jobs/{id}/splat
          setPly(splatPlyUrl(jobId));
        } else {
          // Fallback: backend may serve it at the standard ply endpoint
          setPly(plyUrl(jobId));
        }
      } catch {
        setPly(splatPlyUrl(jobId));
      }
      clearInterval(pollRef.current);
      return;
    }

    if (jobStatus === "running" && stage === "gaussian_splat") {
      setStatus("running");
      startPolling();
      return;
    }

    // Not yet reached gaussian_splat stage
    setStatus("idle");
  }

  function startPolling() {
    clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const job = await getJob(jobId);
        applyJobState(job);
      } catch (e) {
        // keep polling
      }
    }, 3000);
  }

  function handleDownload() {
    window.open(ply, "_blank");
  }

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <span style={styles.icon}>✦</span>
        <h3 style={styles.title}>Gaussian Splatting</h3>
        <span style={styles.badge(status)}>{statusLabel(status)}</span>
      </div>

      <p style={styles.desc}>
        Generates a photorealistic 3D Gaussian Splat from your COLMAP reconstruction.
        Training runs FastGS on the sparse point cloud and cubemap images.
      </p>

      {status === "idle" && (
        <p style={{ fontSize: 13, color: "#666" }}>
          Waiting for pipeline to reach Gaussian Splatting stage…
        </p>
      )}

      {status === "running" && (
        <div style={styles.runningRow}>
          <div style={styles.spinner} />
          <span style={styles.runningText}>
            Training in progress — this takes 1–2 minutes…
          </span>
        </div>
      )}

      {status === "done" && (
        <div style={styles.doneRow}>
          <span style={styles.checkmark}>✓</span>
          <span style={styles.doneText}>Splat ready</span>
          {ply && (
            <button style={styles.btnSecondary} onClick={handleDownload}>
              Download .ply
            </button>
          )}
        </div>
      )}

      {status === "error" && (
        <div style={styles.errorBox}>
          <span style={styles.errorIcon}>⚠</span>
          <span style={styles.errorText}>{errorMsg || "Unknown error"}</span>
        </div>
      )}
    </div>
  );
}

function statusLabel(s) {
  return {
    idle: "Not started",
    running: "Running",
    done: "Complete",
    error: "Failed",
  }[s] ?? s;
}

const styles = {
  container: {
    background: "#1a1a2e",
    border: "1px solid #2d2d4e",
    borderRadius: 10,
    padding: "20px 24px",
    marginTop: 16,
  },
  header: { display: "flex", alignItems: "center", gap: 10, marginBottom: 8 },
  icon:  { fontSize: 18, color: "#7c6af7" },
  title: { margin: 0, fontSize: 16, fontWeight: 600, color: "#e0e0ff" },
  badge: (status) => ({
    marginLeft: "auto",
    fontSize: 11,
    fontWeight: 600,
    padding: "2px 10px",
    borderRadius: 20,
    background:
      status === "done"    ? "#1a3a1a" :
      status === "running" ? "#1a2a3a" :
      status === "error"   ? "#3a1a1a" : "#2a2a3a",
    color:
      status === "done"    ? "#4caf50" :
      status === "running" ? "#64b5f6" :
      status === "error"   ? "#ef5350" : "#888",
  }),
  desc: { fontSize: 13, color: "#888", marginBottom: 16, lineHeight: 1.5 },
  btn: {
    background: "#7c6af7", color: "#fff", border: "none",
    borderRadius: 6, padding: "8px 20px",
    fontSize: 13, fontWeight: 600, cursor: "pointer",
  },
  btnSecondary: {
    background: "transparent", color: "#7c6af7",
    border: "1px solid #7c6af7", borderRadius: 6,
    padding: "8px 16px", fontSize: 13, fontWeight: 600,
    cursor: "pointer", marginLeft: 8,
  },
  runningRow: { display: "flex", alignItems: "center", gap: 10 },
  spinner: {
    width: 16, height: 16,
    border: "2px solid #2d2d4e",
    borderTop: "2px solid #7c6af7",
    borderRadius: "50%",
    animation: "spin 1s linear infinite",
  },
  runningText: { fontSize: 13, color: "#888" },
  doneRow:   { display: "flex", alignItems: "center" },
  checkmark: { color: "#4caf50", fontSize: 18, marginRight: 8 },
  doneText:  { fontSize: 13, color: "#4caf50", marginRight: "auto" },
  errorBox: {
    display: "flex", alignItems: "center", gap: 8,
    background: "#2a1a1a", borderRadius: 6, padding: "10px 14px",
  },
  errorIcon: { color: "#ef5350" },
  errorText: { fontSize: 13, color: "#ef5350", flex: 1 },
};