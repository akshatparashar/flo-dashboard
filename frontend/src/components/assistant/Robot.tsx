/** FLO Assistant's robot. Its right arm waves (every 15 s on the launcher, see assistant.css); colours follow the
 *  surrounding text colour, so it works on the navy / blush launcher and inside the panel. */
export function Robot({ size = 30, className = "" }: { size?: number; className?: string }) {
  return (
    <svg className={`robot ${className}`} width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden="true">
      <line x1="16" y1="4.6" x2="16" y2="8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <circle className="robot-bulb" cx="16" cy="3.4" r="1.7" fill="currentColor" />
      <rect x="6.5" y="8" width="19" height="14.5" rx="5" stroke="currentColor" strokeWidth="1.8" />
      <g className="robot-eyes">
        <circle cx="12.4" cy="14.6" r="1.9" fill="currentColor" />
        <circle cx="19.6" cy="14.6" r="1.9" fill="currentColor" />
      </g>
      <path d="M13 18.6c1.8 1.3 4.2 1.3 6 0" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <path d="M8.6 22.5v3.2M23.4 22.5v3.2" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <path d="M6.5 18.2 3.6 21" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <g className="robot-arm">
        <path d="M25.5 17.8 28.6 13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        <circle cx="29.1" cy="12.1" r="1.6" fill="currentColor" />
      </g>
    </svg>
  );
}
