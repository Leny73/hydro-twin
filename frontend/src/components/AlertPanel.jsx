import { useEffect, useState } from 'react';
import {
  CheckCircle2, Sun, Flame, Waves, AlertTriangle, AlertCircle,
  TrendingUp, Droplets, Sprout, ClipboardList,
  Mail, MessageSquare, Smartphone, Send,
  Satellite, Radio, CloudRain,
  BellRing, Bot, X, ChevronDown, ChevronUp,
  BookOpen, RotateCcw, Info,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import PrecipitationChart from './PrecipitationChart';
import ForecastOutlook    from './ForecastOutlook';
import CycloneChart       from './CycloneChart';
import RegionIncidents    from './RegionIncidents';
import DatePicker         from './DatePicker';
import CuratedEventChips  from './CuratedEventChips';
import AlertChat          from './AlertChat';

/**
 * AlertPanel.jsx — AI Risk Assessment Panel (v3 + BF1-4 hierarchy)
 * ==================================================================
 *
 * Layout (top → bottom):
 *   1. Header (sticky)  — region name + status tag + close
 *   2. Replay banner    — only when in replay mode (compact)
 *   3. Current status   — colored badge with icon (top of fold)
 *   4. Data sources     — what powered THIS assessment
 *   5. Subscribe CTA    — hidden in replay mode
 *   6. AI Reasoning     — structured (4 sections) or markdown blob
 *   7a. Precipitation   — 14-day OpenMeteo history chart
 *   7b. Forecast        — next 7 days outlook (precip + temp), live-only
 *   7c. Synoptic field  — ECMWF Z500/T850 chart, live-only
 *   7d. Citizen incidents — last 3 incidents for THIS oblast, live-only
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
  SAFE:            { bg: 'bg-emerald-950/60', border: 'border-emerald-500', dot: 'bg-emerald-400', Icon: CheckCircle2,   iconColor: 'text-emerald-400', label: 'Safe',            tag: 'NORMAL'   },
  DROUGHT_WATCH:   { bg: 'bg-yellow-950/60',  border: 'border-yellow-500',  dot: 'bg-yellow-400',  Icon: Sun,            iconColor: 'text-yellow-400',  label: 'Drought Watch',   tag: 'WATCH'    },
  DROUGHT_WARNING: { bg: 'bg-orange-950/60',  border: 'border-orange-500',  dot: 'bg-orange-500',  Icon: Flame,          iconColor: 'text-orange-400',  label: 'Drought Warning', tag: 'WARNING'  },
  FLOOD_WATCH:     { bg: 'bg-blue-950/60',    border: 'border-blue-400',    dot: 'bg-blue-400',    Icon: Waves,          iconColor: 'text-blue-400',    label: 'Flood Watch',     tag: 'WATCH'    },
  FLOOD_WARNING:   { bg: 'bg-red-950/60',     border: 'border-red-500',     dot: 'bg-red-500',     Icon: AlertTriangle,  iconColor: 'text-red-400',     label: 'Flood Warning',   tag: 'CRITICAL' },
};
const DEFAULT_META = STATUS_META.SAFE;

const SECTIONS = [
  { key: 'whats_happening', Icon: TrendingUp,   iconColor: 'text-blue-400',   label: 'What is happening'    },
  { key: 'why_it_matters',  Icon: Droplets,     iconColor: 'text-cyan-400',   label: 'Why it matters'       },
  { key: 'current_context', Icon: Sprout,       iconColor: 'text-green-400',  label: 'Current context'      },
  { key: 'next_step',       Icon: ClipboardList, iconColor: 'text-amber-400', label: 'Suggested next step'  },
];

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

// ── Subscribe channels ──────────────────────────────────────────────────────
// Shape mirrors what the backend accepts in POST /subscribe:
//   email        → required, always on
//   discord      → optional per-user webhook URL, fan-out from cron
//   sms          → blocked on AWS SNS sandbox approval (notifications.send_sms is a stub)
//   telegram     → blocked on per-user bot UX (notifications.send_telegram_to_user is a stub)
const CHANNELS = [
  { id: 'email',    Icon: Mail,         label: 'Email',    enabled: true,  required: true  },
  { id: 'discord',  Icon: MessageSquare, label: 'Discord', enabled: true,  required: false },
  { id: 'sms',      Icon: Smartphone,   label: 'SMS',      enabled: false, required: false },
  { id: 'telegram', Icon: Send,         label: 'Telegram', enabled: false, required: false },
];

// Discord webhook URL shape — kept loose, the backend re-validates strictly.
const DISCORD_WEBHOOK_RE = /^https:\/\/(?:[a-z]+\.)?discord(?:app)?\.com\/api\/webhooks\/\d+\/[\w-]+$/;

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
  const [formOpen,        setFormOpen]        = useState(false);
  const [email,           setEmail]           = useState('');
  const [discordEnabled,  setDiscordEnabled]  = useState(false);
  const [discordWebhook,  setDiscordWebhook]  = useState('');
  const [discordHelpOpen, setDiscordHelpOpen] = useState(false);
  const [submitting,      setSubmitting]      = useState(false);
  const [toast,           setToast]           = useState(null);
  const [replayOpen,      setReplayOpen]      = useState(false);
  const [chatOpen,        setChatOpen]        = useState(false);

  // Reset transient state when region changes
  useEffect(() => {
    setFormOpen(false);
    setEmail('');
    setDiscordEnabled(false);
    setDiscordWebhook('');
    setDiscordHelpOpen(false);
    setSubmitting(false);
    setToast(null);
    setReplayOpen(false);
    setChatOpen(false);
  }, [region?.id]);

  // Auto-expand replay section whenever the user is actually in replay mode
  const isReplay = Boolean(replayDate || replayCuratedEvent);
  useEffect(() => {
    if (isReplay) setReplayOpen(true);
  }, [isReplay]);

  if (!region && !isLoading) return null;

  const meta       = STATUS_META[assessment?.status] ?? DEFAULT_META;
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
    setDiscordEnabled(false);
    setDiscordWebhook('');
    setDiscordHelpOpen(false);
    setToast(null);
  };

  const submitSubscribe = async (e) => {
    e.preventDefault();

    const trimmedEmail = email.trim();
    if (!/^\S+@\S+\.\S+$/.test(trimmedEmail)) {
      setToast({ kind: 'error', msg: 'Please enter a valid email address.' });
      return;
    }

    let trimmedWebhook = '';
    if (discordEnabled) {
      trimmedWebhook = discordWebhook.trim();
      if (!DISCORD_WEBHOOK_RE.test(trimmedWebhook)) {
        setToast({
          kind: 'error',
          msg:  "Discord webhook URL doesn't look right — copy the full URL from Server Settings → Integrations → Webhooks.",
        });
        return;
      }
    }

    setToast(null);
    setSubmitting(true);
    try {
      const base = import.meta.env.VITE_API_ENDPOINT ?? '';
      const url  = base.replace('/assess', '/subscribe');
      const body = {
        email:     trimmedEmail,
        region_id: region?.id,
      };
      if (trimmedWebhook) body.discord_webhook = trimmedWebhook;

      const res  = await fetch(url, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));

      if (res.status === 409) {
        setToast({
          kind: 'info',
          msg:  `You're already subscribed to ${region?.name}.`,
        });
      } else if (res.status === 400) {
        setToast({
          kind: 'error',
          msg:  data?.error ?? 'Subscription rejected — please review the form.',
        });
      } else if (!res.ok) {
        setToast({
          kind: 'error',
          msg:  `Subscription failed (${res.status}). Please try again.`,
        });
      } else {
        const channels = [];
        if (data?.delivered?.email)   channels.push('email');
        if (data?.delivered?.discord) channels.push('Discord');
        const detail = channels.length
          ? ` Welcome message sent via ${channels.join(' + ')}.`
          : ' Welcome message will arrive shortly.';
        // Backend rolls municipality clicks up to the parent oblast — surface
        // that to the user so the toast matches what they actually got.
        const targetName  = data?.region_name ?? region?.name;
        const rolledUp    = data?.rolled_up_to && data?.requested_region_id;
        const rollupHint  = rolledUp && region?.name && targetName !== region.name
          ? ` (covers ${region.name})`
          : '';
        setToast({
          kind: 'success',
          msg:  `✅ Subscribed to ${targetName}${rollupHint}.${detail}`,
        });
        setEmail('');
        setDiscordEnabled(false);
        setDiscordWebhook('');
        setDiscordHelpOpen(false);
        setFormOpen(false);
        setTimeout(() => {
          setToast((t) => (t && t.kind === 'success' ? null : t));
        }, 6000);
      }
    } catch {
      setToast({ kind: 'error', msg: 'Network error — check your connection and retry.' });
    } finally {
      setSubmitting(false);
    }
  };

  const alertColor = assessment ? tagColor(meta.tag) : '#374151';

  return (<>
    <aside
      className="
        fixed z-30
        flex flex-col border backdrop-blur-md
        bg-gray-900/95 text-white overflow-y-auto
        transition-all duration-300 ease-in-out
        bottom-0 left-0 right-0 rounded-t-2xl
        max-h-[68vh]
        sm:bottom-[72px] sm:left-auto sm:right-4 sm:top-[80px]
        sm:w-96 sm:rounded-xl sm:max-h-none
      "
      style={{
        borderColor: alertColor,
        boxShadow: assessment
          ? `0 0 32px ${alertColor}28, inset 0 1px 0 ${alertColor}18`
          : 'none',
      }}
      aria-label="AI Risk Assessment Panel"
    >
      {/* ── Sticky top (BF2-5): drag handle + header always visible ── */}
      <div className="sticky top-0 z-10 bg-gray-900/95 backdrop-blur-md
                      border-b border-gray-700/50
                      px-5 pt-4 pb-3 flex flex-col gap-2">
        <div className="sm:hidden flex justify-center" aria-hidden="true">
          <div
            className="w-10 h-1 rounded-full transition-colors duration-300"
            style={{ backgroundColor: assessment ? `${alertColor}90` : '#4B5563' }}
          />
        </div>

        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p
              className="text-[10px] uppercase tracking-widest mb-0.5 transition-colors duration-300"
              style={{ color: assessment ? alertColor : '#6B7280' }}
            >
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
            {assessment && !isReplay && (
              <button
                onClick={() => setChatOpen(true)}
                className="w-8 h-8 flex items-center justify-center
                           rounded-full bg-cyan-900/60 hover:bg-cyan-800 active:scale-90
                           text-cyan-400 hover:text-cyan-200 transition-all duration-150
                           cursor-pointer"
                aria-label="Open AI chat assistant"
                title="Ask HydroAgent"
              >
                <Bot className="w-4 h-4" aria-hidden="true" />
              </button>
            )}
            <button
              onClick={onClose}
              className="w-8 h-8 flex items-center justify-center
                         rounded-full bg-gray-800 hover:bg-gray-700 active:scale-90
                         text-gray-400 hover:text-white transition-all duration-150
                         cursor-pointer"
              aria-label="Close panel and return to map"
            >
              <X className="w-4 h-4" aria-hidden="true" />
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
          {isCurated
            ? <BookOpen className="w-4 h-4 flex-shrink-0" aria-hidden="true" />
            : <Radio    className="w-4 h-4 flex-shrink-0" aria-hidden="true" />}
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
              <meta.Icon className={`ml-auto w-4 h-4 ${meta.iconColor}`} aria-hidden="true" />
            </div>
          </div>

          {/* 4. Data sources — what actually powered THIS assessment */}
          <AssessmentSources sources={assessment?.sources} isReplay={isReplay} />

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
              <span className="flex items-center justify-center gap-2">
                <BellRing className="w-4 h-4" aria-hidden="true" />
                {isAlert ? 'Subscribe to Alerts — URGENT' : 'Subscribe to Push Alerts'}
              </span>
            </button>
          ) : (
            <form
              onSubmit={submitSubscribe}
              className="flex flex-col gap-3"
              aria-label={`Subscribe form for ${region?.name}`}
            >
              {/* Channel picker — 4 icons in a row, 2 active + 2 "soon" */}
              <div>
                <p className="text-[10px] uppercase tracking-widest text-gray-400 mb-1.5">
                  Choose channels
                </p>
                <div className="grid grid-cols-4 gap-1.5">
                  <ChannelButton
                    Icon={Mail} label="Email"
                    state="required"
                    disabled={submitting}
                  />
                  <ChannelButton
                    Icon={MessageSquare} label="Discord"
                    state={discordEnabled ? 'on' : 'off'}
                    disabled={submitting}
                    onClick={() => {
                      setDiscordEnabled(v => !v);
                      if (discordEnabled) setDiscordHelpOpen(false);
                    }}
                  />
                  <ChannelButton
                    Icon={Smartphone} label="SMS"
                    state="soon"
                    title="Awaiting AWS SNS approval — coming soon"
                  />
                  <ChannelButton
                    Icon={Send} label="Telegram"
                    state="soon"
                    title="Per-user Telegram bot — coming soon"
                  />
                </div>
              </div>

              {/* Email input — always visible (required) */}
              <div className="flex flex-col gap-1.5">
                <label htmlFor="subscribe-email" className="text-[10px] uppercase tracking-widest text-gray-400 flex items-center gap-1.5">
                  <Mail className="w-3.5 h-3.5 text-cyan-500" aria-hidden="true" /> Email Address
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
              </div>

              {/* Discord webhook input — only when channel is enabled */}
              {discordEnabled && (
                <div className="flex flex-col gap-1.5">
                  <label htmlFor="subscribe-discord" className="text-[10px] uppercase tracking-widest text-gray-400 flex items-center gap-1.5">
                    <MessageSquare className="w-3.5 h-3.5 text-indigo-400" aria-hidden="true" /> Discord Webhook URL
                  </label>
                  <input
                    id="subscribe-discord"
                    type="url"
                    inputMode="url"
                    value={discordWebhook}
                    onChange={(e) => setDiscordWebhook(e.target.value)}
                    disabled={submitting}
                    placeholder="https://discord.com/api/webhooks/..."
                    spellCheck={false}
                    className="w-full min-h-[44px] px-3 py-2 bg-gray-800 border border-gray-700
                               rounded-lg text-xs font-mono text-white placeholder-gray-500
                               focus:outline-none focus:border-cyan-500
                               disabled:opacity-60 disabled:cursor-not-allowed"
                  />
                  <button
                    type="button"
                    onClick={() => setDiscordHelpOpen(o => !o)}
                    className="text-[10px] text-cyan-400 hover:text-cyan-300 self-start
                               cursor-pointer flex items-center gap-1"
                    aria-expanded={discordHelpOpen}
                  >
                    {discordHelpOpen
                      ? <ChevronUp className="w-3.5 h-3.5" aria-hidden="true" />
                      : <Info      className="w-3.5 h-3.5" aria-hidden="true" />}
                    <span>How do I get a Discord webhook?</span>
                  </button>
                  {discordHelpOpen && (
                    <ol className="text-[11px] text-gray-300 leading-relaxed
                                   bg-gray-800/60 border border-gray-700/60 rounded-lg
                                   p-3 list-decimal list-inside space-y-1
                                   marker:text-cyan-500">
                      <li>Open Discord → right-click your server → <strong className="text-white">Server Settings</strong></li>
                      <li>Go to <strong className="text-white">Integrations → Webhooks</strong></li>
                      <li>Click <strong className="text-white">New Webhook</strong>, pick a channel</li>
                      <li>Click <strong className="text-white">Copy Webhook URL</strong> and paste it above</li>
                    </ol>
                  )}
                </div>
              )}

              {/* Submit row */}
              <div className="flex gap-2 pt-1">
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
                  {submitting ? 'Subscribing…' : 'Confirm Subscribe'}
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
                  : toast.kind === 'info'
                    ? 'bg-cyan-950/50 border-cyan-700/70 text-cyan-200'
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
                  Icon={s.Icon}
                  iconColor={s.iconColor}
                  label={s.label}
                  content={structured[s.key]}
                  accentColor={s.key === 'next_step' ? alertColor : undefined}
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

          {/* 7d. Citizen incidents for THIS oblast — ground truth pairing */}
          {!isReplay && <RegionIncidents region={region} />}

          {/* 9. Replay & past events — collapsible */}
          <CollapsibleSection
            title="Replay & past events"
            TitleIcon={RotateCcw}
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
        <div
          className="flex items-center justify-center gap-1.5 text-[10px] text-yellow-400 border border-yellow-800/60
                     bg-yellow-950/40 px-3 py-2 rounded-md leading-relaxed"
          role="alert"
        >
          <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" aria-hidden="true" />
          {error}
        </div>
      )}
      </div>
    </aside>

    {/* ── Chat overlay — floating above the assessment panel ── */}
    {chatOpen && (
      <div
        className="
          fixed z-40
          flex flex-col border backdrop-blur-md
          bg-gray-900/98 text-white
          bottom-0 left-0 right-0 rounded-t-2xl
          max-h-[85vh]
          sm:bottom-[72px] sm:left-auto sm:right-4 sm:top-[80px]
          sm:w-96 sm:rounded-xl sm:max-h-none
        "
        style={{
          borderColor: alertColor,
          boxShadow: `0 0 32px ${alertColor}28, inset 0 1px 0 ${alertColor}18`,
        }}
        aria-label="HydroAgent Chat Assistant"
        role="dialog"
      >
        <AlertChat
          region={region}
          assessment={assessment}
          onClose={() => setChatOpen(false)}
        />
      </div>
    )}
  </>
  );
}

// ── Subcomponents ────────────────────────────────────────────────────────────

function Section({ Icon, iconColor, label, content, accentColor }) {
  // `accentColor` turns the section LABEL into a tinted pill — same hue as
  // the panel frame, so the call-out reads as part of the alert visual.
  const labelStyle = accentColor
    ? {
        backgroundColor: `${accentColor}1F`,  // ~12% fill
        borderColor:     `${accentColor}66`,  // ~40% stroke
        color:            accentColor,
      }
    : undefined;

  return (
    <div className="flex gap-3">
      <div
        className="flex-shrink-0 w-8 h-8 rounded-full bg-gray-800/80 border border-gray-700
                   flex items-center justify-center"
        aria-hidden="true"
      >
        <Icon className={`w-4 h-4 ${iconColor}`} />
      </div>
      <div className="min-w-0 flex-1">
        <p
          className={
            accentColor
              ? 'inline-flex items-center text-[10px] uppercase tracking-widest font-semibold mb-1.5 px-2 py-0.5 rounded-full border'
              : 'text-[10px] uppercase tracking-widest text-gray-400 font-semibold mb-1'
          }
          style={labelStyle}
        >
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


// ── Data sources block ───────────────────────────────────────────────────────
// Shows what powered THIS assessment in the same visual language as the
// footer DataSourcesBar, but compact enough to live inside the panel. Curated
// 3-chip list so it stays readable at panel width; the raw `sources` array
// from the API (e.g. "Sentinel Hub Statistical API + OpenMeteo") is shown as
// a small monospace caption underneath for transparency.

const ASSESSMENT_SOURCES = [
  { Icon: Satellite,  iconColor: 'text-green-400', name: 'Sentinel-2', sub: 'NDVI · NDWI · vegetation' },
  { Icon: Radio,      iconColor: 'text-cyan-400',  name: 'Sentinel-1', sub: 'SAR soil moisture'        },
  { Icon: CloudRain,  iconColor: 'text-sky-400',   name: 'OpenMeteo',  sub: 'Precipitation · ERA5'     },
];

function AssessmentSources({ sources, isReplay }) {
  const raw = Array.isArray(sources) ? sources.filter(Boolean).join(' · ') : '';
  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900/40 p-3">
      <div className="flex items-center justify-between mb-2">
        <p className="text-[10px] uppercase tracking-widest text-gray-400">
          Data Sources
        </p>
        {isReplay && (
          <span className="text-[9px] uppercase tracking-widest text-purple-300">
            Archive
          </span>
        )}
      </div>
      <div className="grid grid-cols-3 gap-1.5">
        {ASSESSMENT_SOURCES.map(s => (
          <div
            key={s.name}
            className="flex flex-col items-center text-center gap-0.5
                       px-1.5 py-1.5 rounded-md bg-gray-800/50 border border-gray-700/50"
          >
            <s.Icon className={`w-4 h-4 ${s.iconColor}`} aria-hidden="true" />
            <span className="text-[10px] font-semibold text-gray-200 leading-tight">
              {s.name}
            </span>
            <span className="text-[9px] text-gray-500 leading-tight">
              {s.sub}
            </span>
          </div>
        ))}
      </div>
      {raw && (
        <p
          className="mt-2 text-[9px] text-gray-500 leading-relaxed font-mono break-words"
          title={raw}
        >
          {raw}
        </p>
      )}
    </div>
  );
}

// ── Channel picker button ────────────────────────────────────────────────────
// Square card showing icon + label + a small status pill ("Default" / "On" /
// "Off" / "Soon"). Required + Soon are non-clickable; the latter is greyed out
// because the backend channel hasn't been provisioned yet.
function ChannelButton({ Icon, label, state, onClick, disabled, title }) {
  const isRequired = state === 'required';
  const isSoon     = state === 'soon';
  const isOn       = state === 'on';
  const inactive   = isSoon || disabled;

  const styles = isSoon
    ? 'border-gray-800/70 bg-gray-900/40 text-gray-500 cursor-not-allowed'
    : isRequired
      ? 'border-cyan-600/60 bg-cyan-950/30 text-cyan-100 cursor-default'
      : isOn
        ? 'border-cyan-500/80 bg-cyan-950/50 text-cyan-100 cursor-pointer hover:border-cyan-400'
        : 'border-gray-700 bg-gray-800/40 text-gray-300 cursor-pointer hover:border-gray-600 hover:bg-gray-800/60';

  const pillText = isRequired ? 'Default'
                  : isSoon    ? 'Soon'
                  : isOn      ? 'On'
                              : 'Off';
  const pillColor = isRequired ? 'text-cyan-300'
                   : isSoon    ? 'text-gray-600'
                   : isOn      ? 'text-cyan-300'
                               : 'text-gray-500';

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={inactive || isRequired}
      title={title}
      aria-pressed={isOn}
      aria-disabled={inactive}
      className={`flex flex-col items-center justify-center gap-0.5
                  px-1.5 py-2 rounded-lg border min-h-[60px]
                  transition-all duration-150 ${styles}
                  ${disabled && !isSoon ? 'opacity-60' : ''}`}
    >
      <Icon className="w-4 h-4" aria-hidden="true" />
      <span className="text-[10px] font-semibold tracking-wide leading-tight">{label}</span>
      <span className={`text-[8px] uppercase tracking-widest font-semibold ${pillColor}`}>
        {pillText}
      </span>
    </button>
  );
}

function CollapsibleSection({ title, TitleIcon, isOpen, onToggle, children }) {
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
        <span className="flex items-center gap-1.5">
          {TitleIcon && <TitleIcon className="w-3.5 h-3.5 text-purple-400" aria-hidden="true" />}
          {title}
        </span>
        {isOpen
          ? <ChevronUp   className="w-3.5 h-3.5 text-gray-500" aria-hidden="true" />
          : <ChevronDown className="w-3.5 h-3.5 text-gray-500" aria-hidden="true" />}
      </button>
      {isOpen && (
        <div className="flex flex-col gap-3">
          {children}
        </div>
      )}
    </div>
  );
}
