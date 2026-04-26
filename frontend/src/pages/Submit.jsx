import { useState } from 'react';
import IncidentForm from '../components/IncidentForm';

/**
 * Submit.jsx — public, citizen-facing incident submission page
 * ===============================================================
 *
 * Lives outside the dashboard <Layout> (no sidebar, no top bar, no
 * data-sources strip). The dashboard is built for municipalities; this
 * is the surface citizens actually visit to send a report from the field.
 *
 * After a successful submission we swap the form out for a thank-you
 * panel with a "Submit another" button — the IncidentForm itself already
 * fires the global event the dashboard listens for.
 */

export default function Submit() {
  const [submitted, setSubmitted] = useState(false);

  return (
    <div className="h-[100dvh] overflow-y-auto bg-gray-950 text-white font-mono flex flex-col">
      <header className="border-b border-gray-800 bg-gray-950/80 backdrop-blur sticky top-0 z-10">
        <div className="max-w-3xl mx-auto px-4 py-3 flex items-center gap-3">
          <span className="text-xl select-none" aria-hidden="true">💧</span>
          <div className="min-w-0 flex-1">
            <p className="text-xs font-bold tracking-widest text-cyan-400 uppercase leading-none">
              HydroTwin · Report an incident
            </p>
            <p className="text-[10px] text-gray-400 mt-1 leading-tight truncate">
              Flooding, drought damage, or other water issues near you
            </p>
          </div>
        </div>
      </header>

      <main className="flex-1 w-full max-w-3xl mx-auto px-4 py-3 flex flex-col gap-3">
        {submitted ? (
          <ThankYou onAnother={() => setSubmitted(false)} />
        ) : (
          <IncidentForm onSubmitted={() => setSubmitted(true)} />
        )}
      </main>
    </div>
  );
}

function ThankYou({ onAnother }) {
  return (
    <section
      className="bg-emerald-950/40 border border-emerald-700/60 rounded-xl p-6 flex flex-col gap-3 text-center"
      role="status"
      aria-live="polite"
    >
      <span className="text-3xl" aria-hidden="true">✅</span>
      <h2 className="text-base font-bold text-emerald-100">
        Incident received — thank you
      </h2>
      <p className="text-xs text-emerald-200/80 leading-relaxed">
        Your report is now visible to the municipality dashboard.
        If we need more details, we&apos;ll reach out at the email you provided.
      </p>
      <button
        type="button"
        onClick={onAnother}
        className="self-center mt-2 min-h-[44px] px-5 py-2 rounded-lg
                   text-xs font-bold tracking-widest uppercase
                   bg-cyan-700 hover:bg-cyan-600 text-white
                   transition-all duration-200 active:scale-95 cursor-pointer"
      >
        Submit another incident
      </button>
    </section>
  );
}
