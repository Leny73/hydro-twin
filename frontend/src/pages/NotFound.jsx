import { Link } from 'react-router-dom';

/**
 * NotFound.jsx — catch-all 404 page
 * =====================================
 * Standalone (no Layout chrome) so it works for both public routes (/submit
 * and friends) and dashboard typos. Vercel's SPA rewrite sends every unknown
 * URL to index.html, so React Router's `path="*"` route lands here.
 */
export default function NotFound() {
  return (
    <div className="min-h-[100dvh] w-full bg-gray-950 text-white flex items-center justify-center px-6">
      <div className="max-w-md text-center">
        <div className="text-6xl mb-6 select-none">💧</div>

        <p className="font-mono text-cyan-300 text-sm tracking-[0.3em] uppercase mb-3">
          Error 404
        </p>

        <h1 className="text-3xl sm:text-4xl font-semibold mb-4">
          Page not found
        </h1>

        <p className="text-gray-400 leading-relaxed mb-8">
          The page you tried to reach isn't part of HydroTwin. It may have been
          moved, renamed, or never existed.
        </p>

        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <Link
            to="/"
            className="inline-flex items-center justify-center px-5 py-3 rounded-lg
                       bg-cyan-500 hover:bg-cyan-400 text-gray-950 font-medium
                       transition-colors min-h-[44px]"
          >
            ← Back to dashboard
          </Link>
          <Link
            to="/submit"
            className="inline-flex items-center justify-center px-5 py-3 rounded-lg
                       border border-gray-700 hover:border-cyan-500/50 hover:bg-gray-900
                       text-gray-300 font-medium transition-colors min-h-[44px]"
          >
            Submit an incident
          </Link>
        </div>
      </div>
    </div>
  );
}
