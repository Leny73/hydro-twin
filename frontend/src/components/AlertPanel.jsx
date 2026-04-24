/**
 * AlertPanel.jsx — AI Risk Assessment Panel
 * ==========================================
 *
 * Responsive layout:
 *   Mobile  (<640px) : full-width bottom sheet that slides up from the bottom,
 *                      covering ~65% of the screen with the map still visible.
 *   Desktop (≥640px) : fixed-width right sidebar (original design).
 *
 * Props:
 *   region     – currently selected region object (null = panel hidden)
 *   assessment – { status, confidence, reasoning, region_id } from Lambda
 *   isLoading  – bool, true while fetch is in-flight
 *   error      – string | null, non-fatal warning message
 *   onClose    – callback to dismiss the panel and return to the map
 */

// ── Status metadata: maps each alert code to display properties ───────────────
const STATUS_META = {
  SAFE:            { bg: 'bg-emerald-950/60', border: 'border-emerald-500', dot: 'bg-emerald-400', icon: '✅', label: 'Safe'            },
  DROUGHT_WATCH:   { bg: 'bg-yellow-950/60',  border: 'border-yellow-500',  dot: 'bg-yellow-400',  icon: '🟡', label: 'Drought Watch'   },
  DROUGHT_WARNING: { bg: 'bg-orange-950/60',  border: 'border-orange-500',  dot: 'bg-orange-500',  icon: '🔴', label: 'Drought Warning' },
  FLOOD_WATCH:     { bg: 'bg-blue-950/60',    border: 'border-blue-400',    dot: 'bg-blue-400',    icon: '🌊', label: 'Flood Watch'     },
  FLOOD_WARNING:   { bg: 'bg-red-950/60',     border: 'border-red-500',     dot: 'bg-red-500',     icon: '🔴', label: 'Flood Warning'   },
};

const DEFAULT_META = STATUS_META['SAFE'];

// Confidence bar colour: red if high (high confidence in a bad event), else
// amber / green. This intentionally inverts the "green = good" heuristic so
// the user reads it as "how certain is the AI of this threat?".
function confidenceColor(pct) {
  if (pct > 70) return '#EF4444'; // red   — high confidence in an alert
  if (pct > 40) return '#F59E0B'; // amber — moderate confidence
  return '#10B981';               // green — low confidence / likely safe
}

// ─────────────────────────────────────────────────────────────────────────────
export default function AlertPanel({ region, assessment, isLoading, error, onClose }) {
  // Panel is invisible until a region has been selected (or a load is in-flight)
  if (!region && !isLoading) return null;

  const meta    = STATUS_META[assessment?.status] ?? DEFAULT_META;
  const pct     = assessment ? Math.round((assessment.confidence ?? 0) * 100) : 0;
  const isAlert = ['DROUGHT_WARNING', 'FLOOD_WARNING'].includes(assessment?.status);

  // ── Subscribe button handler — DEMO STUB ──────────────────────────────────
  // TODO: Replace alert() with a real API call that registers the user's
  //       webhook/channel ID in a DynamoDB subscription table, then triggers
  //       a confirmation DM via the existing trigger_webhook() Lambda path.
  const handleSubscribe = () => {
    window.alert(
      `[DEMO] You would now be subscribed to alerts for:\n\n` +
      `  ${region?.name}\n\n` +
      `In production this call:\n` +
      `  1. POSTs your handle to a /subscribe Lambda endpoint\n` +
      `  2. Registers a Discord/Telegram webhook via SNS\n` +
      `  3. Sends a confirmation DM with opt-out instructions`
    );
  };

  return (
    <aside
      className={`
        fixed z-30
        flex flex-col gap-4 p-5 border backdrop-blur-md
        bg-gray-900/95 text-white overflow-y-auto
        transition-all duration-300 ease-in-out

        /* ── Mobile: bottom sheet ───────────────────────────────── */
        bottom-0 left-0 right-0 rounded-t-2xl
        max-h-[68vh]

        /* ── Desktop: right sidebar ─────────────────────────────── */
        sm:bottom-4 sm:left-auto sm:right-4 sm:top-14
        sm:w-80 sm:rounded-xl sm:max-h-none

        ${assessment ? meta.border : 'border-gray-700'}
      `}
      aria-label="AI Risk Assessment Panel"
    >

      {/* ── Drag handle — visible on mobile only ────────────────────────── */}
      <div className="sm:hidden flex justify-center -mt-1 mb-1" aria-hidden="true">
        <div className="w-10 h-1 bg-gray-600 rounded-full" />
      </div>

      {/* ── Region Header + close button ─────────────────────────────────── */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[10px] uppercase tracking-widest text-gray-500 mb-0.5">
            Monitoring Zone
          </p>
          <h2 className="text-base font-bold leading-snug text-white">
            {region?.name ?? '…'}
          </h2>
          {region?.description && (
            <p className="text-xs text-gray-400 mt-1 leading-relaxed">
              {region.description}
            </p>
          )}
        </div>
        {/* Close / back-to-map button */}
        <button
          onClick={onClose}
          className="flex-shrink-0 w-8 h-8 flex items-center justify-center
                     rounded-full bg-gray-800 hover:bg-gray-700 active:scale-90
                     text-gray-400 hover:text-white transition-all duration-150
                     cursor-pointer"
          aria-label="Close panel and return to map"
        >
          ✕
        </button>
      </div>

      <hr className="border-gray-700/60" />

      {/* ── Loading Skeleton ──────────────────────────────────────────────── */}
      {isLoading && (
        <div className="flex flex-col gap-3 animate-pulse" aria-busy="true" aria-label="Loading assessment">
          <div className="h-7  w-2/3 bg-gray-700 rounded" />
          <div className="h-2  w-full bg-gray-700 rounded mt-1" />
          <div className="h-2  w-5/6 bg-gray-700 rounded" />
          <div className="h-2  w-4/6 bg-gray-700 rounded" />
          <div className="h-20 w-full bg-gray-700 rounded mt-2" />
          <p className="text-xs text-cyan-400 text-center pt-1">
            Querying AWS Bedrock (Claude 3)…
          </p>
        </div>
      )}

      {/* ── Assessment Results ────────────────────────────────────────────── */}
      {!isLoading && assessment && (
        <>
          {/* ── Status Badge ──────────────────────────────────────────────── */}
          <div className={`p-3 rounded-lg border ${meta.bg} ${meta.border}`}>
            <p className="text-[10px] uppercase tracking-widest text-gray-400 mb-1.5">
              Current Status
            </p>
            <div className="flex items-center gap-2.5">
              <span
                className={`w-3 h-3 rounded-full flex-shrink-0 ${meta.dot} ${isAlert ? 'animate-pulse' : ''}`}
                aria-hidden="true"
              />
              <span className="text-sm font-bold tracking-wide">
                {meta.label}
              </span>
              <span className="ml-auto text-base" role="img" aria-label={meta.label}>
                {meta.icon}
              </span>
            </div>
          </div>

          {/* ── Confidence Score ──────────────────────────────────────────── */}
          <div>
            <div className="flex justify-between text-[10px] uppercase tracking-widest text-gray-400 mb-2">
              <span>AI Confidence</span>
              <span className="text-white font-bold">{pct}%</span>
            </div>
            {/* Progress bar */}
            <div className="w-full h-1.5 bg-gray-700 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-700 ease-out"
                style={{
                  width:           `${pct}%`,
                  backgroundColor: confidenceColor(pct),
                }}
                role="progressbar"
                aria-valuenow={pct}
                aria-valuemin={0}
                aria-valuemax={100}
              />
            </div>
          </div>

          {/* ── AI Reasoning ──────────────────────────────────────────────── */}
          <div>
            <p className="text-[10px] uppercase tracking-widest text-gray-400 mb-1.5">
              AI Reasoning{' '}
              <span className="text-cyan-500 normal-case tracking-normal font-normal">
                — Claude 3 · Bedrock
              </span>
            </p>
            <blockquote className="text-xs text-gray-200 leading-relaxed bg-gray-800/60 p-3 rounded-lg border border-gray-700/60 italic">
              {assessment.reasoning}
            </blockquote>
          </div>

          {/* ── Metadata Footer ───────────────────────────────────────────── */}
          <div className="text-[10px] text-gray-500 bg-gray-800/30 rounded-md p-2.5 border border-gray-800/60 leading-relaxed">
            <span className="text-gray-400">Data:</span>{' '}
            Copernicus EO (Sentinel-1/2) + OpenMeteo
            <br />
            <span className="text-gray-400">Assessed:</span>{' '}
            {new Date().toUTCString()}
          </div>

          {/* ── Subscribe CTA ─────────────────────────────────────────────── */}
          <button
            onClick={handleSubscribe}
            className={`
              mt-auto w-full py-3 rounded-lg text-xs font-bold tracking-widest uppercase
              transition-all duration-200 active:scale-95 cursor-pointer
              ${isAlert
                ? 'bg-red-600 hover:bg-red-500 text-white'
                : 'bg-cyan-800 hover:bg-cyan-700 text-white'}
            `}
            aria-label={`Subscribe to push alerts for ${region?.name}`}
          >
            {isAlert ? '🔔 Subscribe to Alerts — URGENT' : '🔔 Subscribe to Push Alerts'}
          </button>
        </>
      )}

      {/* ── Non-fatal API warning ─────────────────────────────────────────── */}
      {error && (
        <p
          className="text-[10px] text-yellow-400 border border-yellow-800/60
                     bg-yellow-950/40 px-3 py-2 rounded-md text-center leading-relaxed"
          role="alert"
        >
          ⚠️ {error}
        </p>
      )}
    </aside>
  );
}
