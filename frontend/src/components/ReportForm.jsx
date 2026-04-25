import { useState } from 'react';
import Map, { Marker, NavigationControl } from 'react-map-gl';
import 'mapbox-gl/dist/mapbox-gl.css';
import { submitReport } from '../lib/reports-api';

/**
 * ReportForm.jsx — citizen incident-report submission
 * =====================================================
 *
 * Fields:
 *   - email       (required, RFC-ish format check on the client)
 *   - region      (dropdown: pleven / yambol / burgas / other)
 *   - description (textarea, 10–500 chars)
 *   - location    (mini-map; click to drop / move a pin)
 *
 * On submit: POST /reports with the payload. Success clears the form and
 * shows a toast; the parent ReportsList component re-fetches via a window
 * event so the new report appears at the top.
 */

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN ?? '';

const REGION_OPTIONS = [
  { value: '',        label: 'Select a region…' },
  { value: 'pleven',  label: 'Pleven Oblast' },
  { value: 'yambol',  label: 'Yambol Oblast' },
  { value: 'burgas',  label: 'Burgas Oblast' },
  { value: 'other',   label: 'Other / Outside monitored areas' },
];

const INITIAL_VIEW_STATE = {
  longitude: 25.20,
  latitude:  42.75,
  zoom:      6.4,
};

export default function ReportForm() {
  const [email,       setEmail]       = useState('');
  const [regionId,    setRegionId]    = useState('');
  const [description, setDescription] = useState('');
  const [pin,         setPin]         = useState(null);  // { lng, lat } | null

  const [submitting, setSubmitting] = useState(false);
  const [toast,      setToast]      = useState(null);

  const reset = () => {
    setEmail('');
    setRegionId('');
    setDescription('');
    setPin(null);
  };

  const onMapClick = (e) => {
    const { lng, lat } = e.lngLat;
    setPin({ lng, lat });
  };

  const onSubmit = async (e) => {
    e.preventDefault();

    // ── Client-side validation ───────────────────────────────────────────
    if (!/^\S+@\S+\.\S+$/.test(email.trim())) {
      setToast({ kind: 'error', msg: 'Please enter a valid email address.' });
      return;
    }
    if (!regionId) {
      setToast({ kind: 'error', msg: 'Please pick a region.' });
      return;
    }
    if (description.trim().length < 10) {
      setToast({ kind: 'error', msg: 'Description must be at least 10 characters.' });
      return;
    }
    if (!pin) {
      setToast({ kind: 'error', msg: 'Please drop a pin on the map.' });
      return;
    }

    setSubmitting(true);
    setToast(null);
    try {
      await submitReport({
        email:       email.trim(),
        region_id:   regionId,
        description: description.trim(),
        lat:         pin.lat,
        lng:         pin.lng,
      });
      setToast({ kind: 'success', msg: '✅ Report submitted — thank you.' });
      reset();
      // Tell the list to re-fetch
      window.dispatchEvent(new CustomEvent('hydrotwin:reports:changed'));
      setTimeout(() => {
        setToast(t => (t && t.kind === 'success' ? null : t));
      }, 4000);
    } catch (err) {
      console.warn('[HydroTwin] Report submit failed:', err.message);
      setToast({ kind: 'error', msg: 'Submission failed. Please try again.' });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="bg-gray-900/60 border border-gray-800 rounded-xl p-5">
      <header className="mb-4">
        <h2 className="text-base font-bold text-white">Report an incident</h2>
        <p className="text-xs text-gray-400 mt-1">
          Spotted flooding, drought damage, or other water-related issues?
          Submit a report so authorities can review and respond.
        </p>
      </header>

      <form onSubmit={onSubmit} className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* ── Left column: text fields ────────────────────────────────── */}
        <div className="flex flex-col gap-3">
          <label className="text-[10px] uppercase tracking-widest text-gray-400">
            Email
            <input
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={submitting}
              placeholder="you@example.com"
              className="mt-1 w-full min-h-[44px] px-3 py-2 bg-gray-800 border border-gray-700
                         rounded-lg text-sm text-white placeholder-gray-500
                         focus:outline-none focus:border-cyan-500
                         disabled:opacity-60"
            />
          </label>

          <label className="text-[10px] uppercase tracking-widest text-gray-400">
            Region
            <select
              required
              value={regionId}
              onChange={(e) => setRegionId(e.target.value)}
              disabled={submitting}
              className="mt-1 w-full min-h-[44px] px-3 py-2 bg-gray-800 border border-gray-700
                         rounded-lg text-sm text-white
                         focus:outline-none focus:border-cyan-500
                         disabled:opacity-60"
            >
              {REGION_OPTIONS.map(o => (
                <option key={o.value} value={o.value} disabled={!o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>

          <label className="text-[10px] uppercase tracking-widest text-gray-400">
            Description
            <textarea
              required
              rows={5}
              minLength={10}
              maxLength={500}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={submitting}
              placeholder="What did you observe? When? Any photos or other context."
              className="mt-1 w-full px-3 py-2 bg-gray-800 border border-gray-700
                         rounded-lg text-sm text-white placeholder-gray-500
                         focus:outline-none focus:border-cyan-500
                         resize-y disabled:opacity-60"
            />
            <span className="block text-right text-[10px] text-gray-500 mt-0.5 normal-case tracking-normal">
              {description.length}/500
            </span>
          </label>
        </div>

        {/* ── Right column: pinpoint map ──────────────────────────────── */}
        <div className="flex flex-col gap-2">
          <p className="text-[10px] uppercase tracking-widest text-gray-400">
            Location {pin ? '· pinned' : '· click the map to drop a pin'}
          </p>
          <div className="h-[260px] rounded-lg overflow-hidden border border-gray-800">
            <Map
              mapboxAccessToken={MAPBOX_TOKEN}
              initialViewState={INITIAL_VIEW_STATE}
              style={{ width: '100%', height: '100%' }}
              mapStyle="mapbox://styles/mapbox/dark-v11"
              onClick={onMapClick}
            >
              <NavigationControl position="top-right" showCompass={false} />
              {pin && (
                <Marker longitude={pin.lng} latitude={pin.lat} anchor="bottom">
                  <span className="text-2xl drop-shadow-lg" aria-hidden="true">📍</span>
                </Marker>
              )}
            </Map>
          </div>
          {pin && (
            <p className="text-[10px] text-gray-500">
              {pin.lat.toFixed(4)}°N, {pin.lng.toFixed(4)}°E
            </p>
          )}
        </div>

        {/* ── Submit row (spans both columns) ─────────────────────────── */}
        <div className="md:col-span-2 flex flex-col gap-2">
          {toast && (
            <div
              role={toast.kind === 'error' ? 'alert' : 'status'}
              aria-live="polite"
              className={`text-xs px-3 py-2 rounded-md leading-relaxed border
                ${toast.kind === 'success'
                  ? 'bg-emerald-950/50 border-emerald-700/70 text-emerald-200'
                  : 'bg-red-950/50 border-red-700/70 text-red-200'}`}
            >
              {toast.msg}
            </div>
          )}
          <button
            type="submit"
            disabled={submitting}
            className="w-full min-h-[44px] py-3 rounded-lg text-xs font-bold tracking-widest uppercase
                       bg-cyan-700 hover:bg-cyan-600 text-white
                       transition-all duration-200 active:scale-95 cursor-pointer
                       disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {submitting ? 'Submitting…' : 'Submit report'}
          </button>
        </div>
      </form>
    </section>
  );
}
