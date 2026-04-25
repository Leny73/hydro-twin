import SeverityCounter from './SeverityCounter';

/**
 * TopBar.jsx — page title + severity counter
 * =============================================
 *
 * Sits above the main content area. Title comes from the parent route
 * (Overview / Reports / etc). Severity counter is only shown when the
 * caller passes `regionStatuses` — Reports page hides it.
 */

export default function TopBar({ title, subtitle, regionStatuses }) {
  return (
    <header
      className="flex items-center gap-6 px-6 h-16 flex-shrink-0
                 bg-gray-950/95 border-b border-gray-800 backdrop-blur-md
                 z-20"
    >
      <div className="min-w-0">
        <h1 className="text-lg font-bold text-white leading-tight truncate">
          {title}
        </h1>
        {subtitle && (
          <p className="text-[11px] text-gray-500 leading-tight">{subtitle}</p>
        )}
      </div>

      {regionStatuses !== undefined && (
        <div className="ml-auto">
          <SeverityCounter regionStatuses={regionStatuses} />
        </div>
      )}
    </header>
  );
}
