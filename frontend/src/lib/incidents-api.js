/**
 * incidents-api.js — frontend client for citizen-incident endpoints
 * ====================================================================
 *
 * The backend route is still mounted at `/reports` on API Gateway (kept
 * stable so we don't have to redeploy the Lambda + DynamoDB plumbing
 * mid-hackathon). Only the frontend vocabulary moved to "incidents".
 */

const API_ENDPOINT =
  import.meta.env.VITE_API_ENDPOINT ??
  'https://YOUR_API_ID.execute-api.us-east-1.amazonaws.com/prod/assess';

const INCIDENTS_ENDPOINT = API_ENDPOINT.replace('/assess', '/reports');

export async function submitIncident(payload) {
  const res = await fetch(INCIDENTS_ENDPOINT, {
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

export async function listIncidents() {
  const res = await fetch(INCIDENTS_ENDPOINT);
  if (!res.ok) {
    throw new Error(`GET /reports HTTP ${res.status}: ${res.statusText}`);
  }
  return res.json();
}
