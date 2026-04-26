import { useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import PrecipitationChart from './PrecipitationChart';
import ForecastOutlook    from './ForecastOutlook';
import CycloneChart       from './CycloneChart';
import RegionReports      from './RegionReports';
import DatePicker         from './DatePicker';
import CuratedEventChips  from './CuratedEventChips';

/**
 * AlertPanel.jsx — AI Risk Assessment Panel (v3 + BF1-4 hierarchy)
 * ==================================================================
 *
 * Layout (top → bottom):
 *   1. Header (sticky)  — region name + status tag + close
 *   2. Replay banner    — only when in replay mode (compact)
 *   3. Current status   — colored badge with icon (top of fold)
 *   4. AI Confidence    — labelled progress bar
 *   5. Subscribe CTA    — hidden in replay mode
 *   6. AI Reasoning     — structured (4 sections) or markdown blob
 *   7a. Precipitation   — 14-day OpenMeteo history chart
 *   7b. Forecast        — next 7 days outlook (precip + temp), live-only
 *   7c. Synoptic field  — ECMWF Z500/T850 chart, live-only
 *   7d. Citizen reports — last 3 reports for THIS oblast, live-only
 *   8. Replay & past events — collapsible (DatePicker + CuratedEventChips),
 *                             closed by default, auto-opens when in replay
 *   9. Metadata footer  — compact provenance line (data source, timestamp)
 *
 * Removed (BF1-4 + BF1-5):
 *   - 3-cell Status/Confidence/Region footer grid (duplicated everything above)
 *   - Per-region "Data Sources" collapsible block (sources live on /sources)
 *
 * Responsive layout:
 *   Mobile  (<640px) : full-width bottom sheet
 *   Desktop (≥640px) : right sidebar, sized to fit between TopBar + DataSourcesBar
 */

// ── Markdown renderer overrides ──────────────────────────────────────────────
const MD_COMPONENTS = {
  p:      ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
  strong: ({ children }) => <strong className="text-white font-semibold">{children}</strong>,
  em:     ({ children }) => <em className="italic text-gray-300">{children}</em>,
  ul:     ({ children }) => <ul className="list-disc list-inside space-y-1 my-1.5 marker:text-cyan-500">{children}</ul>,
  ol:     ({ children }) => <ol className="list-decimal list-inside space-y-1 my-1.5 marker:text-cyan-500">{children}</ol>,
  li:     ({ children }) => <li className="ml-1">{children}</li>,
  code:   ({ children }) => <code className="px-1 py-0.5 bg-gray-900 rounded text-cyan-300 text-[11px]">{children}</code>,
  a:      ({ children, href }) => <a href={href} target="_blank" rel="noreferrer" className="text-cyan-400 underline">{children}</a>,
};

// ── Status metadata: maps each alert code to display properties ──────────────
const STATUS_META = {
  SAFE:            { bg: 'bg-emerald-950/60', border: 'border-emerald-500', dot: 'bg-emerald-400', icon: '✅', label: 'Safe',            tag: 'NORMAL'   },
  DROUGHT_WATCH:   { bg: 'bg-yellow-950/60',  border: 'border-yellow-500',  dot: 'bg-yellow-400',  icon: '🟡', label: 'Drought Watch',   tag: 'WATCH'    },
  DROUGHT_WARNING: { bg: 'bg-orange-950/60',  border: 'border-orange-500',  dot: 'bg-orange-500',  icon: '🔴', label: 'Drought Warning', tag: 'WARNING'  },
  FLOOD_WATCH:     { bg: 'bg-blue-950/60',    border: 'border-blue-400',    dot: 'bg-blue-400',    icon: '🌊', label: 'Flood Watch',     tag: 'WATCH'    },
  FLOOD_WARNING:   { bg: 'bg-red-950/60',     border: 'border-red-500',     dot: 'bg-red-500',     icon: '🔴', label: 'Flood Warning',   tag: 'CRITICAL' },
};
const DEFAULT_META = STATUS_META.SAFE;

const SECTIONS = [
  { key: 'whats_happening', icon: '📈', label: 'What is happening' },
  { key: 'why_it_matters',  icon: '💧', label: 'Why it matters'    },
  { key: 'current_context', icon: '🌱', label: 'Current context'   },
  { key: 'next_step',       icon: '📋', label: 'Suggested next step' },
];

function confidenceColor(pct) {
  if (pct > 70) return '#EF4444';
  if (pct > 40) return '#F59E0B';
  return '#10B981';
}

function tagColor(tag) {
  switch (tag) {
    case 'NORMAL':   return '#10B981';
    case 'WATCH':    return '#F59E0B';
    case 'WARNING':  return '#F97316';
    case 'CRITICAL': return '#EF4444';
    case 'INFO':     return '#3B82F6';
    default:         return '#94A3B8';
  }
}

// ─────────────────────────────────────────────────────────────────────────────
export default function AlertPanel({
  region,
  assessment,
  isLoading,
  error,
  onClose,
  replayDate           = null,
  onReplayDateChange   = () => {},
  curatedEvents        = [],
  replayCuratedEvent   = null,
  onCuratedEventSelect = () => {},
}) {
  const [formOpen,    setFormOpen]    = useState(false);
  const [email,       setEmail]       = useState('');
  const [submitting,  setSubmitting]  = useState(false);
  const [toast,       setToast]       = useState(null);
  const [replayOpen,  setReplayOpen]  = useState(false);

  // Reset transient state when region changes
  useEffect(() => {
    setFormOpen(false);
    setEmail('');
    setSubmitting(false);
    setToast(null);
    setReplayOpen(false);
  }, [region?.id]);

  // Auto-expand replay section whenever the user is actually in replay mode
  const isReplay = Boolean(replayDate || replayCuratedEvent);
  useEffect(() => {
    if (isReplay) setReplayOpen(true);
  }, [isReplay]);

  if (!region && !isLoading) return null;

  const meta       = STATUS_META[assessment?.status] ?? DEFAULT_META;
  const pct        = assessment ? Math.round((assessment.confidence ?? 0) * 100) : 0;
  const isAlert    = ['DROUGHT_WARNING', 'FLOOD_WARNING'].includes(assessment?.status);
  const replayKind = assessment?.replay_kind ?? null;
  const isCurated  = replayKind === 'curated';

  // V3-3: prefer structured payload when present + non-empty.
  const structured = assessment?.reasoning_structured;
  const hasStructured =
    !isReplay && structured && Object.values(structured).some(
      v => typeof v === 'string' && v.trim().length > 0
    );
  const visibleSections = hasStructured
    ? SECTIONS.filter(s => (structured[s.key] ?? '').trim().length > 0)
    : [];

  const closeForm = () => {
    setFormOpen(false);
    setEmail('');
    setToast(null);
  };

  const submitSubscribe = async (e) => {
    e.preventDefault();
    const trimmed = email.trim();
    if (!/^\S+@\S+\.\S+$/.test(trimmed)) {
      setToast({ kind: 'error', msg: 'Please enter a valid email address.' });
      return;
    }
    setToast(null);
    setSubmitting(true);
    try {
      const base = import.meta.env.VITE_API_ENDPOINT ?? '';
      const url  = base.replace('/assess', '/subscribe');
      const res  = await fetch(url, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ email: trimmed, region_id: region?.id }),
      });
      if (res.status === 409) {
        setToast({ kind: 'error', msg: 'You are already subscribed to alerts for this region.' });
      } else if (res.status === 400) {
        setToast({ kind: 'error', msg: 'That email was rejected — please double-check it.' });
      } else if (!res.ok) {
        setToast({ kind: 'error', msg: `Subscription failed (${res.status}). Please try again.` });
      } else {
        setToast({ kind: 'success', msg: `✅ You're subscribed for ${region?.name}` });
        setEmail('');
        setFormOpen(false);
        setTimeout(() => {
          setToast((t) => (t && t.kind === 'success' ? null : t));
        }, 4000);
      }
    } catch {
      setToast({ kind: 'error', msg: 'Network error — check your connection and retry.' });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <aside
      className={`
        fixed z-30
        flex flex-col border backdrop-blur-md
        bg-gray-900/95 text-white overflow-y-auto
        transition-all duration-300 ease-in-out

        /* Mobile: bottom sheet */
        bottom-0 left-0 right-0 rounded-t-2xl
        max-h-[68vh]

        /* Desktop: right sidebar — sits below TopBar (h-16) and above DataSourcesBar (h-14) */
        sm:bottom-[72px] sm:left-auto sm:right-4 sm:top-[80px]
        sm:w-96 sm:rounded-xl sm:max-h-none

        ${assessment ? meta.border : 'border-gray-700'}
      `}
      aria-label="AI Risk Assessment Panel"
    >
      {/* ── Sticky top (BF2-5): drag handle + header always visible ── */}
      <div className="sticky top-0 z-10 bg-gray-900/95 backdrop-blur-md
                      border-b border-gray-700/50
                      px-5 pt-4 pb-3 flex flex-col gap-2">
        <div className="sm:hidden flex justify-center" aria-hidden="true">
          <div className="w-10 h-1 bg-gray-600 rounded-full" />
        </div>

        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="text-[10px] uppercase tracking-widest text-gray-500 mb-0.5">
              HydroTwin Alert
            </p>
            <h2 className="text-base font-bold leading-snug text-white truncate">
              {region?.name ?? '…'}
            </h2>
            {region?.description && (
              <p className="text-[11px] text-gray-400 mt-1 leading-relaxed">
                {region.description}
              </p>
            )}
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            {assessment && (
              <span
                className="text-[10px] font-bold tracking-widest uppercase px-2 py-1 rounded"
                style={{
                  backgroundColor: `${tagColor(meta.tag)}22`,
                  color:           tagColor(meta.tag),
                  border:          `1px solid ${tagColor(meta.tag)}55`,
                }}
              >
                {meta.tag}
              </span>
            )}
            <button
              onClick={onClose}
              className="w-8 h-8 flex items-center justify-center
                         rounded-full bg-gray-800 hover:bg-gray-700 active:scale-90
                         text-gray-400 hover:text-white transition-all duration-150
                         cursor-pointer"
              aria-label="Close panel and return to map"
            >
              ✕
            </button>
          </div>
        </div>
      </div>

      {/* ── Scrollable body ────────────────────────────────────────── */}
      <div className="flex flex-col gap-4 px-5 pt-4 pb-5">
      {/* ── Replay banner (only when active) ───────────────────────── */}
      {isReplay && replayKind && (
        <div
          className={`flex items-center gap-2 px-3 py-2 rounded-lg
                      text-[11px] leading-relaxed border
                      ${isCurated
                        ? 'bg-cyan-950/50 border-cyan-700/70 text-cyan-100'
                        : 'bg-purple-950/50 border-purple-700/70 text-purple-100'}`}
          role="status"
          aria-live="polite"
        >
          <span aria-hidden="true">{isCurated ? '📚' : '📡'}</span>
          <span className="flex-1">
            <strong className="text-white">
              {isCurated ? 'Curated reference' : 'Live archive'}
            </strong>
            {' — '}
            {isCurated
              ? assessment?.curated?.name
              : new Date(`${replayDate}T00:00:00Z`).toLocaleDateString('en-GB', {
                  day: 'numeric', month: 'short', year: 'numeric',
                })}
          </span>
        </div>
      )}

      {/* ── Loading skeleton ───────────────────────────────────────── */}
      {isLoading && (
        <div className="flex flex-col gap-3 animate-pulse" aria-busy="true" aria-label="Loading assessment">
          <div className="h-7  w-2/3 bg-gray-700 rounded" />
          <div className="h-2  w-full bg-gray-700 rounded mt-1" />
          <div className="h-2  w-5/6 bg-gray-700 rounded" />
          <div className="h-2  w-4/6 bg-gray-700 rounded" />
          <div className="h-20 w-full bg-gray-700 rounded mt-2" />
          <p className="text-xs text-cyan-400 text-center pt-1">
            {isReplay ? 'Loading historical archive…' : 'Querying AWS Bedrock (Claude Sonnet)…'}
          </p>
        </div>
      )}

      {/* ── Assessment results ─────────────────────────────────────── */}
      {!isLoading && assessment && (
        <>
          {/* 3. Current status — top of the fold */}
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

          {/* 4. AI confidence — labelled progress bar */}
          <ConfidenceBar pct={pct} />

          {/* 5. Subscribe CTA — hidden in replay mode */}
          {!isReplay && (!formOpen ? (
            <button
              onClick={() => { setToast(null); setFormOpen(true); }}
              className={`
                w-full min-h-[44px] py-3 rounded-lg text-xs font-bold tracking-widest uppercase
                transition-all duration-200 active:scale-95 cursor-pointer
                ${isAlert
                  ? 'bg-red-600 hover:bg-red-500 text-white'
                  : 'bg-cyan-800 hover:bg-cyan-700 text-white'}
              `}
              aria-label={`Subscribe to push alerts for ${region?.name}`}
            >
              {isAlert ? '🔔 Subscribe to Alerts — URGENT' : '🔔 Subscribe to Push Alerts'}
            </button>
          ) : (
            <form
              onSubmit={submitSubscribe}
              className="flex flex-col gap-2"
              aria-label={`Subscribe form for ${region?.name}`}
            >
              <label htmlFor="subscribe-email" className="text-[10px] uppercase tracking-widest text-gray-400">
                Email Address
              </label>
              <input
                id="subscribe-email"
                type="email"
                autoComplete="email"
                autoFocus
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={submitting}
                placeholder="you@example.com"
                aria-invalid={toast?.kind === 'error' ? 'true' : 'false'}
                className="w-full min-h-[44px] px-3 py-2 bg-gray-800 border border-gray-700
                           rounded-lg text-sm text-white placeholder-gray-500
                           focus:outline-none focus:border-cyan-500
                           disabled:opacity-60 disabled:cursor-not-allowed"
              />
              <div className="flex gap-2">
                <button
                  type="submit"
                  disabled={submitting}
                  className={`flex-1 min-h-[44px] py-3 rounded-lg text-xs font-bold tracking-widest uppercase
                              transition-all duration-200 active:scale-95 cursor-pointer
                              disabled:opacity-60 disabled:cursor-not-allowed
                              ${isAlert
                                ? 'bg-red-600 hover:bg-red-500 text-white'
                                : 'bg-cyan-800 hover:bg-cyan-700 text-white'}`}
                >
                  {submitting ? 'Subscribing…' : 'Confirm'}
                </button>
                <button
                  type="button"
                  onClick={closeForm}
                  disabled={submitting}
                  className="min-h-[44px] px-4 py-3 rounded-lg text-xs font-bold tracking-widest uppercase
                             bg-gray-800 hover:bg-gray-700 text-gray-300
                             transition-all duration-200 active:scale-95 cursor-pointer
                             disabled:opacity-60 disabled:cursor-not-allowed"
                >
                  Cancel
                </button>
              </div>
            </form>
          ))}

          {!isReplay && toast && (
            <div
              role={toast.kind === 'error' ? 'alert' : 'status'}
              aria-live="polite"
              className={`text-[11px] px-3 py-2 rounded-md text-center leading-relaxed border
                ${toast.kind === 'success'
                  ? 'bg-emerald-950/50 border-emerald-700/70 text-emerald-200'
                  : 'bg-red-950/50 border-red-700/70 text-red-200'}`}
            >
              {toast.msg}
            </div>
          )}

          {/* 6. AI reasoning — structured (V3) or markdown blob fallback */}
          {hasStructured ? (
            <div className="flex flex-col gap-3">
              {visibleSections.map(s => (
                <Section
                  key={s.key}
                  icon={s.icon}
                  label={s.label}
                  content={structured[s.key]}
                />
              ))}
            </div>
          ) : (
            <div>
              <p className="text-[10px] uppercase tracking-widest text-gray-400 mb-1.5">
                {isReplay ? 'Event Reconstruction' : 'AI Reasoning'}{' '}
                <span className="text-cyan-500 normal-case tracking-normal font-normal">
                  {isCurated
                    ? '— Curated reference narrative (NIMH archive)'
                    : isReplay
                    ? '— Derived from ERA5 reanalysis'
                    : '— Claude Sonnet · Bedrock'}
                </span>
              </p>
              <blockquote className="text-xs text-gray-200 leading-relaxed bg-gray-800/60 p-3 rounded-lg border border-gray-700/60">
                <ReactMarkdown components={MD_COMPONENTS}>
                  {assessment.reasoning ?? ''}
                </ReactMarkdown>
              </blockquote>
            </div>
          )}

          {/* 7a. Precipitation history (OpenMeteo 14-day series) */}
          <PrecipitationChart region={region} />

          {/* 7b. 7-day forecast outlook — what's coming next */}
          {!isReplay && <ForecastOutlook region={region} />}

          {/* 7c. Synoptic field — Windy pressure embed centred on the oblast,
                 with a deep-link to the ECMWF Z500/T850 chart */}
          {!isReplay && <CycloneChart region={region} />}

          {/* 7d. Citizen reports for THIS oblast — ground truth pairing */}
          {!isReplay && <RegionReports region={region} />}

          {/* 8. Replay & past events — collapsible */}
          <CollapsibleSection
            title="🕓 Replay & past events"
            isOpen={replayOpen}
            onToggle={() => setReplayOpen(o => !o)}
          >
            <DatePicker
              value={replayDate ?? replayCuratedEvent?.peakDate ?? null}
              onChange={onReplayDateChange}
            />
            {curatedEvents.length > 0 && (
              <CuratedEventChips
                events={curatedEvents}
                selectedEventId={replayCuratedEvent?.id ?? null}
                onSelect={onCuratedEventSelect}
              />
            )}
          </CollapsibleSection>

          {/* 9. Compact metadata footer */}
          <div className="text-[10px] text-gray-500 bg-gray-800/30 rounded-md p-2.5 border border-gray-800/60 leading-relaxed">
            {isCurated ? (
              <>
                <span className="text-gray-400">Data:</span>{' '}
                Curated reference snapshot (NIMH / EMS archive — pending verification)
                <br />
                <span className="text-gray-400">Event:</span>{' '}
                {assessment?.curated?.name}
                <br />
                <span className="text-gray-400">Peak date:</span>{' '}
                {new Date(`${assessment.replay_date}T00:00:00Z`).toUTCString()}
                {assessment?.curated?.sourceUrl && (
                  <>
                    <br />
                    <span className="text-gray-400">Source:</span>{' '}
                    <a
                      href={assessment.curated.sourceUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="text-cyan-400 underline"
                    >
                      {assessment.curated.emsActivationId ?? 'reference'}
                    </a>
                  </>
                )}
              </>
            ) : isReplay ? (
              <>
                <span className="text-gray-400">Data:</span>{' '}
                OpenMeteo Historical Archive (ERA5 reanalysis)
                <br />
                <span className="text-gray-400">Replay date:</span>{' '}
                {new Date(`${replayDate}T00:00:00Z`).toUTCString()}
              </>
            ) : (
              <>
                <span className="text-gray-400">Data:</span>{' '}
                Copernicus EO (Sentinel-1/2) + OpenMeteo
                <br />
                <span className="text-gray-400">Assessed:</span>{' '}
                {new Date().toUTCString()}
              </>
            )}
          </div>
        </>
      )}

      {error && (
        <p
          className="text-[10px] text-yellow-400 border border-yellow-800/60
                     bg-yellow-950/40 px-3 py-2 rounded-md text-center leading-relaxed"
          role="alert"
        >
          ⚠️ {error}
        </p>
      )}
      </div>
    </aside>
  );
}

// ── Subcomponents ────────────────────────────────────────────────────────────

function Section({ icon, label, content }) {
  return (
    <div className="flex gap-3">
      <div
        className="flex-shrink-0 w-8 h-8 rounded-full bg-gray-800/80 border border-gray-700
                   flex items-center justify-center text-base"
        aria-hidden="true"
      >
        {icon}
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-[10px] uppercase tracking-widest text-gray-400 font-semibold mb-1">
          {label}
        </p>
        <div className="text-xs text-gray-200 leading-relaxed">
          <ReactMarkdown components={MD_COMPONENTS}>
            {content}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  );
}

function ConfidenceBar({ pct }) {
  const color = confidenceColor(pct);
  return (
    <div>
      <div className="flex items-center justify-between text-[10px] uppercase tracking-widest text-gray-400 mb-1.5">
        <span>AI Confidence</span>
        <span className="font-bold" style={{ color }}>{pct}%</span>
      </div>
      <div
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="AI confidence"
        className="w-full h-1.5 rounded-full bg-gray-800 overflow-hidden"
      >
        <div
          className="h-full rounded-full transition-all duration-300"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
    </div>
  );
}

function CollapsibleSection({ title, isOpen, onToggle, children }) {
  return (
    <div className="border-t border-gray-700/60 pt-3">
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center justify-between
                   text-[10px] uppercase tracking-widest text-gray-400
                   hover:text-gray-200 transition-colors mb-2 cursor-pointer"
        aria-expanded={isOpen}
      >
        <span>{title}</span>
        <span className="text-gray-500 text-base leading-none" aria-hidden="true">
          {isOpen ? '−' : '+'}
        </span>
      </button>
      {isOpen && (
        <div className="flex flex-col gap-3">
          {children}
        </div>
      )}
    </div>
  );
}
