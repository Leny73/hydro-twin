/**
 * HistoryPicker.jsx — Past Events Dropdown
 * =========================================
 *
 * Lists verified historical flood/drought events for the selected region.
 * Selecting one switches AlertPanel from live assessment to a baked snapshot.
 *
 * Props:
 *   events           – array of event objects (see historicalEvents.json schema)
 *   selectedEventId  – id of the currently active replay event, or null
 *   onSelect         – (event | null) => void
 */

const SEVERITY_ICON = {
  SAFE:            '✅',
  DROUGHT_WATCH:   '🟡',
  DROUGHT_WARNING: '🟠',
  FLOOD_WATCH:     '🌊',
  FLOOD_WARNING:   '🔴',
};

// Pretty-print "2014-08-01" → "Aug 2014"
function formatPeak(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
}

export default function HistoryPicker({ events, selectedEventId, onSelect }) {
  if (!events?.length) return null;

  const handleChange = (e) => {
    const id = e.target.value;
    if (!id) {
      onSelect(null);
      return;
    }
    const event = events.find((ev) => ev.id === id);
    if (event) onSelect(event);
  };

  return (
    <div>
      <label
        htmlFor="history-picker"
        className="block text-[10px] uppercase tracking-widest text-gray-400 mb-1.5"
      >
        📼 Replay Past Event
      </label>
      <select
        id="history-picker"
        value={selectedEventId ?? ''}
        onChange={handleChange}
        className="w-full min-h-[44px] px-3 py-2 bg-gray-800 border border-gray-700
                   rounded-lg text-sm text-white
                   focus:outline-none focus:border-cyan-500
                   cursor-pointer"
        aria-label="Select a historical event to replay"
      >
        <option value="">— Live assessment —</option>
        {events.map((event) => (
          <option key={event.id} value={event.id}>
            {SEVERITY_ICON[event.severity] ?? '•'} {formatPeak(event.peakDate)} — {event.name}
          </option>
        ))}
      </select>
    </div>
  );
}
