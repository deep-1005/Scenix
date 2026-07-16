import axios from "axios";

export const API = "http://localhost:8000";

// Every request to the backend must skip ngrok's free-tier browser warning
// page, or ngrok intercepts it and returns HTML instead of JSON — which
// shows up as a CORS error since the interstitial has no CORS headers.
axios.defaults.headers.common["ngrok-skip-browser-warning"] = "true";

// Wrapper so every fetch() call also gets the header automatically.
export async function apiFetch(url, options = {}) {
  return fetch(url, {
    ...options,
    headers: {
      ...(options.headers || {}),
      "ngrok-skip-browser-warning": "true",
    },
  });
}

export async function createJob(sceneName, files) {
  const form = new FormData();
  form.append("scene_name", sceneName);
  for (const f of files) form.append("files", f);
  return (await axios.post(`${API}/jobs`, form)).data;
}

export async function getJob(id)    { return (await axios.get(`${API}/jobs/${id}`)).data; }
export async function listJobs()    { return (await axios.get(`${API}/jobs`)).data; }
export async function listImages(id){ return (await axios.get(`${API}/jobs/${id}/images`)).data; }

// COLMAP sparse point cloud (shown in the Point Cloud tab)
export function plyUrl(id)      { return `${API}/jobs/${id}/ply`; }
// Gaussian Splat .ply (the FastGS output)
export function splatPlyUrl(id) { return `${API}/jobs/${id}/splat`; }
export async function resumeJob(id) { return (await axios.post(`${API}/jobs/${id}/resume`)).data; }

export async function cancelJob(jobId) {
  const res = await apiFetch(`${API}/jobs/${jobId}/cancel`, {
    method: "POST",
  });
  if (!res.ok) {
    throw new Error(`Failed to cancel job: ${res.status}`);
  }
  return res.json();
}

// frontend/src/api.js
export async function fetchEvidence(id) { return (await axios.get(`${API}/jobs/${id}/evidence`)).data; }