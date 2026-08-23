const KEY = 'sp_pipeline'

// route → sidebar label → description
export const ENGINE_META = {
  'new-depts':        { label: 'New Depts',        desc: 'Add new departments introduced in TY', route: '/department-plan/new-depts' },
  'attr-correction':  { label: 'Attr Correction',   desc: 'Adjust attribute-level weights',       route: '/department-plan/attr-correction' },
  'base-correction':  { label: 'Base Correction',   desc: 'Fill zero-TY gaps via peer benchmark', route: '/department-plan/base-correction' },
}

export function startPipeline(keys) {
  sessionStorage.setItem(KEY, JSON.stringify({ queue: keys, current: 0 }))
}

export function getPipeline() {
  try { return JSON.parse(sessionStorage.getItem(KEY)) } catch { return null }
}

export function currentEngineKey() {
  const p = getPipeline()
  return p && p.current < p.queue.length ? p.queue[p.current] : null
}

/** Advance to next engine. Returns the next route, or '/department-plan/final-results' when done. */
export function advancePipeline() {
  const p = getPipeline()
  if (!p) return '/department-plan/final-results'
  p.current += 1
  sessionStorage.setItem(KEY, JSON.stringify(p))
  if (p.current >= p.queue.length) {
    clearPipeline()
    return '/department-plan/final-results'
  }
  return ENGINE_META[p.queue[p.current]]?.route ?? '/department-plan/final-results'
}

export function clearPipeline() {
  sessionStorage.removeItem(KEY)
}
