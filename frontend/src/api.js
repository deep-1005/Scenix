import axios from "axios";

export const API = "http://localhost:8001";

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