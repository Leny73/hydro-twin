/**
 * reports-api.js — frontend client for /reports endpoints
 * ==========================================================
 *
 * The /reports route lives on the same API Gateway as /assess + /status.
 * We derive its URL from VITE_API_ENDPOINT to avoid a third env var.
 */

const API_ENDPOINT =
  import.meta.env.VITE_API_ENDPOINT ??
  'https://YOUR_API_ID.execute-api.us-east-1.amazonaws.com/prod/assess';

const REPORTS_ENDPOINT = API_ENDPOINT.replace('/assess', '/reports');

export async function submitReport(payload) {
  const res = await fetch(REPORTS_ENDPOINT, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify(payload),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`POST /reports HTTP ${res.status}: ${text || res.statusText}`);
  }
  return res.json();
}

export async function listReports() {
  const res = await fetch(REPORTS_ENDPOINT);
  if (!res.ok) {
    throw new Error(`GET /reports HTTP ${res.status}: ${res.statusText}`);
  }
  return res.json();
}
