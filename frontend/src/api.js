const BASE = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");

export async function fetchDashboard() {
  const res = await fetch(`${BASE}/api/dashboard?history_hours=24`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `API error ${res.status}`);
  }
  return res.json();
}
