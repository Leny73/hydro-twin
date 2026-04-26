import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

/**
 * Unsubscribe.jsx — one-click unsubscribe landing page
 * ========================================================
 * Where every "Unsubscribe from this region" link in HydroTwin emails lands.
 *
 * Reads (e, r, t) from the query string and POSTs to /unsubscribe on the
 * backend. The token is HMAC-signed by notifications.make_unsubscribe_token —
 * a tampered URL is rejected with a 400.
 *
 * Standalone (no Layout chrome) so the page works on first load even before
 * any dashboard data is available. Matches the NotFound page's style.
 */

const API_ENDPOINT =
  import.meta.env.VITE_API_ENDPOINT ??
  'https://YOUR_API_ID.execute-api.us-east-1.amazonaws.com/prod/assess';

const UNSUBSCRIBE_URL = API_ENDPOINT.replace(/\/assess\/?$/, '/unsubscribe');

export default function Unsubscribe() {
  const [searchParams] = useSearchParams();
  const email     = searchParams.get('e') ?? '';
  const regionId  = searchParams.get('r') ?? '';
  const token     = searchParams.get('t') ?? '';

  const [state, setState] = useState({ status: 'pending', message: '' });

  useEffect(() => {
    if (!email || !regionId || !token) {
      setState({
        status:  'error',
        message: 'Missing parameters — open the link from your email exactly as it was sent.',
      });
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(UNSUBSCRIBE_URL, {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({ e: email, r: regionId, t: token }),
        });
        const data = await res.json().catch(() => ({}));
        if (cancelled) return;

        if (res.ok) {
          setState({
            status:  'success',
            message: `You won't receive HydroTwin alerts for ${regionId} anymore.`,
          });
        } else {
          setState({
            status:  'error',
            message: data?.error ?? `Unsubscribe failed (${res.status}).`,
          });
        }
      } catch (err) {
        if (cancelled) return;
        setState({
          status:  'error',
          message: 'Network error — please retry, or reply to any HydroTwin email and we\'ll remove you manually.',
        });
      }
    })();
    return () => { cancelled = true; };
  }, [email, regionId, token]);

  return (
    <div className="min-h-[100dvh] w-full bg-gray-950 text-white flex items-center justify-center px-6">
      <div className="max-w-md w-full text-center">
        <div className="text-6xl mb-6 select-none">💧</div>

        <p className="font-mono text-cyan-300 text-sm tracking-[0.3em] uppercase mb-3">
          {state.status === 'pending' ? 'Processing…'
           : state.status === 'success' ? 'Unsubscribed'
           : 'Error'}
        </p>

        <h1 className="text-3xl sm:text-4xl font-semibold mb-4">
          {state.status === 'pending'
            ? 'Removing you from this list…'
            : state.status === 'success'
              ? "You're unsubscribed"
              : "We couldn't unsubscribe you"}
        </h1>

        <p className="text-gray-400 leading-relaxed mb-8">
          {state.message || 'Working…'}
        </p>

        {state.status === 'success' && email && regionId && (
          <p className="text-xs font-mono text-gray-500 mb-8">
            <span className="text-gray-600">{email}</span>
            {' · '}
            <span className="text-gray-600">{regionId}</span>
          </p>
        )}

        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <Link
            to="/"
            className="inline-flex items-center justify-center px-5 py-3 rounded-lg
                       bg-cyan-500 hover:bg-cyan-400 text-gray-950 font-medium
                       transition-colors min-h-[44px]"
          >
            ← Back to dashboard
          </Link>
          {state.status === 'success' && regionId && (
            <Link
              to={`/?region=${encodeURIComponent(regionId)}`}
              className="inline-flex items-center justify-center px-5 py-3 rounded-lg
                         border border-gray-700 hover:border-cyan-500/50 hover:bg-gray-900
                         text-gray-300 font-medium transition-colors min-h-[44px]"
            >
              View {regionId} once more
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}
