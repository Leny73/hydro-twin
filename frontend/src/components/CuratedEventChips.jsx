/**
 * CuratedEventChips.jsx — Quick-access pre-baked event chips
 * ===========================================================
 *
 * Compact wrap-row of buttons for verified historical events. Clicking a chip
 * loads the baked snapshot from historicalEvents.json — bypassing OpenMeteo so
 * basin-driven river floods (which point precipitation can't detect) still
 * render with their correct severity for pitch demos.
 *
 * Props:
 *   events            – array of curated event objects (see historicalEvents.json)
 *   selectedEventId   – id of the active curated event, or null
 *   onSelect          – (event | null) => void
 */

const SEVERITY_DOT = {
  SAFE:            'bg-emerald-400',
  DROUGHT_WATCH:   'bg-yellow-400',
  DROUGHT_WARNING: 'bg-orange-500',
  FLOOD_WATCH:     'bg-blue-400',
  FLOOD_WARNING:   'bg-red-500',
};

// "2014-08-01" → "Aug '14"
function shortPeak(iso) {
  const d = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return iso;
  const month = d.toLocaleDateString('en-US', { month: 'short' });
  const yr    = String(d.getUTCFullYear()).slice(-2);
  return `${month} '${yr}`;
}

// Short label for the chip body — falls back to event name if no shortName.
function chipLabel(event) {
  return event.shortName ?? event.name.split(/[—–-]/)[0].trim();
}

export default function CuratedEventChips({ events, selectedEventId, onSelect }) {
  if (!events?.length) return null;

  return (
    <div>
      <p className="text-[10px] uppercase tracking-widest text-gray-400 mb-1.5">
        Or jump to a known event
      </p>
      <div className="flex flex-wrap gap-1.5">
        {events.map((event) => {
          const active = event.id === selectedEventId;
          return (
            <button
              key={event.id}
              type="button"
              onClick={() => onSelect(active ? null : event)}
              className={`
                inline-flex items-center gap-1.5 min-h-[32px] px-2.5 py-1 rounded-full
                text-[11px] font-medium leading-none
                border transition-all duration-150 active:scale-95 cursor-pointer
                ${active
                  ? 'bg-cyan-900/70 border-cyan-500 text-white'
                  : 'bg-gray-800/70 border-gray-700 text-gray-300 hover:border-gray-500 hover:text-white'}
              `}
              aria-pressed={active}
              aria-label={`Replay curated event: ${event.name}`}
              title={event.summary ?? event.name}
            >
              <span
                className={`w-1.5 h-1.5 rounded-full ${SEVERITY_DOT[event.severity] ?? 'bg-gray-500'}`}
                aria-hidden="true"
              />
              <span className="font-mono opacity-80">{shortPeak(event.peakDate)}</span>
              <span>·</span>
              <span>{chipLabel(event)}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
