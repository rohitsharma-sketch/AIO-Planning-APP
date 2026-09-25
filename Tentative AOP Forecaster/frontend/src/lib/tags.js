// Single source of truth for store-tag → type classification.
// MUST mirror LFL_TAGS / RAMP_TAGS / NSO_TAGS in engine_v3.py.
export const LFL_TAGS  = new Set(['032 - Stores', '080 - Stores', '095 - Stores', '125 - Stores', '3 - Stores',
                                  'FY26 - Q1', 'FY26 - Q2', 'FY26 - Q3', 'LFL', 'lfl'])
export const RAMP_TAGS = new Set(['FY26 - Q4', 'FY27 - Q1', 'FY27 - Q2', 'Ramp', 'RAMP', 'ramp'])
export const NSO_TAGS  = new Set(['NSO', 'MAMJ-NSO'])

export const TYPES = ['LfL', 'Ramp', 'NSO']

export function tagGroup(tag) {
  if (!tag) return 'LfL'
  if (NSO_TAGS.has(tag))  return 'NSO'
  if (RAMP_TAGS.has(tag)) return 'Ramp'
  if (LFL_TAGS.has(tag))  return 'LfL'
  // Unknown tag: fall back on naming convention
  if (tag.includes('NSO'))  return 'NSO'
  if (tag.includes('FY27')) return 'Ramp'
  return 'LfL'
}

export function tagClass(tag) {
  const g = tagGroup(tag)
  return g === 'NSO' ? 'tag-nso' : g === 'Ramp' ? 'tag-ramp' : 'tag-lfl'
}

export const MONTHS = ["Mar'27", "Apr'27", "May'27", "Jun'27", "Jul'27", "Aug'27", "Sep'27",
                       "Oct'27", "Nov'27", "Dec'27", "Jan'28", "Feb'28", "Mar'28"]

// Normalise one detail.json row (₹ Lakhs) → leaf. scale 0.01 → ₹ Cr (default), 1 → ₹ Lakhs.
export function toLeaf(r, scale = 0.01) {
  const mb = MONTHS.map(m => (r[`${m} | Base`] || 0) * scale)
  const m  = MONTHS.map(mo => (r[`${mo} | Forecast`] || 0) * scale)
  const sum = a => a.reduce((s, v) => s + v, 0)
  return {
    Type: tagGroup(r.Tag), Tag: r.Tag || '—', Cluster: r.Cluster || '—',
    Store: r.Store || '—', Division: r.Division || '—',
    base: sum(mb), fcst: sum(m), mb, m,
  }
}
