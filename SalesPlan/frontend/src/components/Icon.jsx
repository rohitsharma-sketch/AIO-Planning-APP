// Small line icons for the sidebar and Home cards (replaces the emoji icons).
const PATHS = {
  home:     'M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z',
  division: 'M4 20V11M10 20V4M16 20v-6M2 20h20',
  dept:     'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',
  mrp:      'M20.6 13.4 13.4 20.6a2 2 0 0 1-2.8 0L3 13V3h10l7.6 7.6a2 2 0 0 1 0 2.8zM7.5 7.5h.01',
  display:  'M3 4h18v12H3zM8 20h8M12 16v4',
  sync:     'M21 12a9 9 0 0 1-15.5 6.2M3 12A9 9 0 0 1 18.5 5.8M21 4v5h-5M3 20v-5h5',
  check:    'M20 6 9 17l-5-5',
}

export default function Icon({ name, size = 18, strokeWidth = 1.8 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"
         style={{ flexShrink: 0 }}>
      <path d={PATHS[name]} />
    </svg>
  )
}
