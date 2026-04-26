import { Menu } from 'lucide-react';
import SeverityCounter from "./SeverityCounter";
import logoUrl from "../../logo.jpg";

/**
 * TopBar.jsx — page title + severity counter + mobile hamburger
 * ===============================================================
 *
 * Sits above the main content area. Title comes from the parent route
 * (Overview / Incidents / etc). Severity counter is only shown when the
 * caller passes `regionStatuses` — Incidents page hides it.
 *
 * Hamburger button is rendered only below `lg` (≥1024 px is desktop,
 * where Sidebar is statically visible). It calls `onMenuClick` to open
 * the MobileNav drawer owned by Layout.
 */

export default function TopBar({
  title,
  subtitle,
  regionStatuses,
  onMenuClick,
}) {
  return (
    <header
      className="flex items-center gap-3 sm:gap-6 pl-2 pr-4 sm:px-6 h-16 flex-shrink-0
                 bg-gray-950/95 border-b border-gray-800 backdrop-blur-md
                 z-20"
    >
      {onMenuClick && (
        <button
          type="button"
          onClick={onMenuClick}
          aria-label="Open navigation menu"
          className="lg:hidden w-11 h-11 flex items-center justify-center flex-shrink-0
                     rounded-md text-gray-200 hover:text-white hover:bg-gray-800
                     active:scale-95 cursor-pointer transition-colors"
        >
          <Menu className="w-5 h-5" aria-hidden="true" />
        </button>
      )}

      <div className="min-w-0 flex-1">
        {/* Mobile: brand wordmark (sidebar isn't visible to carry it).
            Desktop: page title + subtitle (sidebar already shows the brand). */}
        <div className="sm:hidden flex items-center gap-1.5">
          <img
            src={logoUrl}
            alt=""
            aria-hidden="true"
            className="w-7 h-7 object-contain select-none flex-shrink-0"
            draggable="false"
          />
          <span className="text-sm font-bold tracking-widest text-cyan-400 uppercase leading-none">
            HydroTwin
          </span>
        </div>
        <h1 className="hidden sm:block text-base sm:text-lg font-bold text-white leading-tight truncate">
          {title}
        </h1>
        {subtitle && (
          <p className="hidden sm:block text-[11px] text-gray-500 leading-tight truncate">
            {subtitle}
          </p>
        )}
      </div>

      {regionStatuses !== undefined && (
        <div className="ml-auto flex-shrink-0">
          <SeverityCounter regionStatuses={regionStatuses} />
        </div>
      )}
    </header>
  );
}
