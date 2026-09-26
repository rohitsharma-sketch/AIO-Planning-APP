// One palette for the RS Planning suite (2026-09-25 makeover): the same navy
// chrome + sage accent + light data area as the AOP Forecaster and the Buyer's
// Input Sheet. Key names are unchanged - every page reads them inline and
// App.jsx also exposes each one as a CSS variable (--primary, --surface, ...).
export const theme = {
  fontUI:   "'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  fontMono: "'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",   // numbers use tabular figures (index.css)

  // Brand
  navy:         'var(--st-chrome,#34453F)',   // chrome (sidebar + page header), strong headings
  primary:      'var(--st-accent,#4F7A66)',   // sage accent - links, active states, primary actions
  primaryLight: 'var(--st-tint,#EAF3EE)',   // accent tint
  primaryDark:  'var(--st-accent-dark,#3F6453)',   // accent hover

  // Accent (positive)
  accent:       '#15803D',
  accentLight:  '#ECFDF3',

  // Status
  success:  '#15803D',
  danger:   '#B42318',
  warning:  '#B45309',

  // Surfaces
  surface:    '#FFFFFF',   // cards, panels
  surfaceAlt: 'var(--st-page,#F7F6F2)',   // page background
  surfaceUp:  'var(--st-surface-2,#FAF9F6)',   // table heads, toolbars inside a card

  // Borders
  border:       'var(--st-line,#E5E3DA)',
  borderStrong: 'var(--st-line-2,#D3D0C4)',

  // Text
  textPrimary:   'var(--st-ink,#1E2723)',
  textSecondary: 'var(--st-muted,#5F6B64)',
  textMuted:     'var(--st-faint,#6E7872)',

  // Sidebar (same navy as the page header, so the chrome reads as one frame)
  sidebar:       'var(--st-chrome,#34453F)',
  sidebarText:   '#FFFFFF',
  sidebarActive: 'rgba(255,255,255,0.10)',
}

// `${color}22`-style hex alpha can't wrap a CSS var (suite theme), so fade via color-mix instead.
export const alpha = (c, hh) => `color-mix(in srgb, ${c} ${Math.round(parseInt(hh, 16) / 2.55)}%, transparent)`
