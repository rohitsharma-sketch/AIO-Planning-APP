// One palette for the RS Planning suite (2026-09-25 makeover): the same navy
// chrome + sage accent + light data area as the AOP Forecaster and the Buyer's
// Input Sheet. Key names are unchanged - every page reads them inline and
// App.jsx also exposes each one as a CSS variable (--primary, --surface, ...).
export const theme = {
  fontUI:   "'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  fontMono: "'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",   // numbers use tabular figures (index.css)

  // Brand
  navy:         '#34453F',   // chrome (sidebar + page header), strong headings
  primary:      '#4F7A66',   // sage accent - links, active states, primary actions
  primaryLight: '#EAF3EE',   // accent tint
  primaryDark:  '#3F6453',   // accent hover

  // Accent (positive)
  accent:       '#15803D',
  accentLight:  '#ECFDF3',

  // Status
  success:  '#15803D',
  danger:   '#B42318',
  warning:  '#B45309',

  // Surfaces
  surface:    '#FFFFFF',   // cards, panels
  surfaceAlt: '#F7F6F2',   // page background
  surfaceUp:  '#FAF9F6',   // table heads, toolbars inside a card

  // Borders
  border:       '#E5E3DA',
  borderStrong: '#D3D0C4',

  // Text
  textPrimary:   '#1E2723',
  textSecondary: '#5F6B64',
  textMuted:     '#8C958F',

  // Sidebar (same navy as the page header, so the chrome reads as one frame)
  sidebar:       '#34453F',
  sidebarText:   '#FFFFFF',
  sidebarActive: 'rgba(255,255,255,0.10)',
}
