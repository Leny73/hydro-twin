import { CalendarDays } from 'lucide-react';

/**
 * DatePicker.jsx — Replay-date selector
 * ======================================
 *
 * Native HTML5 <input type="date"> styled to match the panel theme.
 * Triggers an OpenMeteo Historical fetch in App.jsx on change.
 *
 * Props:
 *   value     – current ISO date string (YYYY-MM-DD), or null/'' for live
 *   onChange  – (isoDate | null) => void   (null = clear, return to live)
 *   minDate   – earliest selectable date (default 2010-01-01)
 *   maxDate   – latest selectable date   (default today UTC)
 */

const TODAY = new Date().toISOString().slice(0, 10);

export default function DatePicker({
  value,
  onChange,
  minDate = '2000-01-01',
  maxDate = TODAY,
}) {
  const handleChange = (e) => {
    const iso = e.target.value;
    onChange(iso || null);
  };

  return (
    <div>
      <label
        htmlFor="replay-date"
        className="block text-[10px] uppercase tracking-widest text-gray-400 mb-1.5"
      >
        <span className="flex items-center gap-1.5">
          <CalendarDays className="w-3.5 h-3.5 text-purple-400" aria-hidden="true" />
          Replay any past day
        </span>
      </label>
      <div className="flex gap-2">
        <input
          id="replay-date"
          type="date"
          value={value ?? TODAY}
          onChange={handleChange}
          min={minDate}
          max={maxDate}
          className="flex-1 min-h-[44px] px-3 py-2 bg-gray-800 border border-gray-700
                     rounded-lg text-sm text-white
                     focus:outline-none focus:border-cyan-500
                     cursor-pointer"
          aria-label="Pick a past date to replay"
        />
        {value && (
          <button
            type="button"
            onClick={() => onChange(null)}
            className="min-h-[44px] px-3 rounded-lg text-[10px] font-bold uppercase tracking-wider
                       bg-gray-800 hover:bg-gray-700 text-gray-300 border border-gray-700
                       transition-colors duration-150 cursor-pointer"
            aria-label="Clear replay date and return to live"
          >
            Clear
          </button>
        )}
      </div>
    </div>
  );
}
