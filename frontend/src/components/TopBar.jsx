import SeverityCounter from './SeverityCounter';

/**
 * TopBar.jsx — page title + severity counter + mobile hamburger
 * ===============================================================
 *
 * Sits above the main content area. Title comes from the parent route
 * (Overview / Reports / etc). Severity counter is only shown when the
 * caller passes `regionStatuses` — Reports page hides it.
 *
 * Hamburger button is rendered only below `lg` (≥1024 px is desktop,
 * where Sidebar is statically visible). It calls `onMenuClick` to open
 * the MobileNav drawer owned by Layout.
 */

export default function TopBar({ title, subtitle, regionStatuses, onMenuClick }) {
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
          <span className="text-2xl leading-none" aria-hidden="true">☰</span>
        </button>
      )}

      <div className="min-w-0 flex-1">
        <h1 className="text-base sm:text-lg font-bold text-white leading-tight truncate">
          {title}
        </h1>
        {subtitle && (
          <p className="text-[11px] text-gray-500 leading-tight truncate">{subtitle}</p>
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
