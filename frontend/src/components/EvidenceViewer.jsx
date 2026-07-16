import { useEffect, useState } from "react";
import { fetchEvidence } from "../api";
import EvidenceSplatViewer from "./EvidenceSplatViewer";

export default function EvidenceViewer({ jobId }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [selectedId, setSelectedId] = useState(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const result = await fetchEvidence(jobId);
        if (!cancelled) setData(result);
      } catch (e) {
        if (!cancelled) setError(e.message);
      }
    }
    load();
    const interval = setInterval(load, 5000);
    return () => { cancelled = true; clearInterval(interval); };
  }, [jobId]);

  if (error) return <div style={{ color: "#e05252", padding: 16 }}>Error: {error}</div>;
  if (!data) return <div style={{ padding: 16, color: "var(--text-dim)" }}>Loading evidence...</div>;
  if (data.status === "not_ready") {
    return <div style={{ padding: 16, color: "var(--text-dim)" }}>Evidence detection not yet complete for this scene.</div>;
  }

  return (
    <div style={{ padding: 16 }}>
      {data.room_dimensions && (
        <div style={{ fontSize: 13, color: "var(--text-dim)", marginBottom: 10 }}>
          Room dimensions ({data.unit}): x={data.room_dimensions.x.toFixed(2)}, y={data.room_dimensions.y.toFixed(2)}, z={data.room_dimensions.z.toFixed(2)}
        </div>
      )}

      <EvidenceSplatViewer
        jobId={jobId}
        evidence={data.evidence}
        selectedId={selectedId}
        onSelect={setSelectedId}
      />

      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13, marginTop: 16 }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "1px solid var(--border, #333)" }}>
            <th style={{ padding: "8px 12px" }}>ID</th>
            <th style={{ padding: "8px 12px" }}>Detected label</th>
            <th style={{ padding: "8px 12px" }}>Classification</th>
            <th style={{ padding: "8px 12px" }}>Confidence</th>
            <th style={{ padding: "8px 12px" }}>Dimensions</th>
          </tr>
        </thead>
        <tbody>
          {data.evidence.map((item) => (
            <tr
              key={item.id}
              onClick={() => setSelectedId(item.id)}
              style={{
                borderBottom: "1px solid var(--border, #2a2a2a)",
                cursor: "pointer",
                background: selectedId === item.id ? "rgba(90,160,255,0.12)" : "transparent",
              }}
            >
              <td style={{ padding: "8px 12px" }}>{item.id}</td>
              <td style={{ padding: "8px 12px" }}>{item.label}</td>
              <td style={{ padding: "8px 12px" }}>{item.classification ?? "—"}</td>
              <td style={{ padding: "8px 12px" }}>{item.classification_confidence ? item.classification_confidence.toFixed(2) : "—"}</td>
              <td style={{ padding: "8px 12px" }}>
                {item.dimensions ? `${item.dimensions.x.toFixed(2)} × ${item.dimensions.y.toFixed(2)} × ${item.dimensions.z.toFixed(2)}` : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {data.evidence.length === 0 && (
        <div style={{ color: "var(--text-dim)", marginTop: 12 }}>No evidence items detected in this scene.</div>
      )}
    </div>
  );
}