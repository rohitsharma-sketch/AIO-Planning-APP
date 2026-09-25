// One palette for the RS Planning suite (2026-09-25 makeover): the same navy
// chrome + teal accent + light data area as the AOP Forecaster and the Buyer's
// Input Sheet. Key names are unchanged - every page reads them inline and
// App.jsx also exposes each one as a CSS variable (--primary, --surface, ...).
export const theme = {
  fontUI:   "'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  fontMono: "'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",   // numbers use tabular figures (index.css)

  // Brand
  navy:         '#0F2742',   // chrome (sidebar + page header), strong headings
  primary:      '#0E7490',   // teal accent - links, active states, primary actions
  primaryLight: '#E7F1F4',   // accent tint
  primaryDark:  '#155E75',   // accent hover

  // Accent (positive)
  accent:       '#15803D',
  accentLight:  '#ECFDF3',

  // Status
  success:  '#15803D',
  danger:   '#B42318',
  warning:  '#B45309',

  // Surfaces
  surface:    '#FFFFFF',   // cards, panels
  surfaceAlt: '#F3F5F9',   // page background
  surfaceUp:  '#F8FAFC',   // table heads, toolbars inside a card

  // Borders
  border:       '#E3E8EF',
  borderStrong: '#CFD8E3',

  // Text
  textPrimary:   '#0F1B2D',
  textSecondary: '#5B6B82',
  textMuted:     '#8A99AD',

  // Sidebar (same navy as the page header, so the chrome reads as one frame)
  sidebar:       '#0F2742',
  sidebarText:   '#FFFFFF',
  sidebarActive: 'rgba(255,255,255,0.10)',
}
