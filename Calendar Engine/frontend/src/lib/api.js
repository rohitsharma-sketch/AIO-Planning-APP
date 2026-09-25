const BASE = '/api/calendar'

export async function fetchJson(path, opts) {
  const res = await fetch(`${BASE}${path}`, { credentials: 'same-origin', ...opts })
  if (res.status === 401) {
    window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`
    throw new Error('Not authenticated')
  }
  if (!res.ok) {
    let msg = `HTTP ${res.status}`
    try { const e = await res.json(); msg = typeof e.detail === 'string' ? e.detail : JSON.stringify(e.detail ?? e) } catch {}
    throw new Error(msg)
  }
  return res.json()
}

const jsonPost = (path, body, method = 'POST') =>
  fetchJson(path, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export async function getMe() {
  const res = await fetch('/api/auth/me', { credentials: 'same-origin' })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

// calendar-library
export const listCalendarLibrary = () => fetchJson('/calendar-library')
export const getCalendar = (id) => fetchJson(`/calendar-library/${id}`)
export const saveCalendar = (payload) => jsonPost('/calendar-library', payload)
export const deleteCalendar = (id) => fetchJson(`/calendar-library/${id}`, { method: 'DELETE' })
export const renameCalendar = (id, name) => jsonPost(`/calendar-library/${id}/name`, { name }, 'PUT')
export const updateCalendarFestivals = (id, payload) => jsonPost(`/calendar-library/${id}/festivals`, payload, 'PUT')

// store-cluster-map
export const getStoreClusterMap = () => fetchJson('/store-cluster-map')
export const putStoreClusterMap = (payload) => jsonPost('/store-cluster-map', payload, 'PUT')
export const getStoreClusterLog = () => fetchJson('/store-cluster-log')
export async function importStoreCluster(file) {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${BASE}/import/store-cluster`, { method: 'POST', credentials: 'same-origin', body: form })
  if (!res.ok) {
    let msg = `HTTP ${res.status}`
    try { const e = await res.json(); msg = typeof e.detail === 'string' ? e.detail : JSON.stringify(e.detail ?? e) } catch {}
    throw new Error(msg)
  }
  return res.json()
}

// cluster-profiles
export const getClusterProfiles = () => fetchJson('/cluster-profiles')
export const putClusterProfiles = (payload) => jsonPost('/cluster-profiles', payload, 'PUT')
export async function importFestivals(file) {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${BASE}/import/festivals`, { method: 'POST', credentials: 'same-origin', body: form })
  if (!res.ok) {
    let msg = `HTTP ${res.status}`
    try { const e = await res.json(); msg = typeof e.detail === 'string' ? e.detail : JSON.stringify(e.detail ?? e) } catch {}
    throw new Error(msg)
  }
  return res.json()
}

// festival-reference (Google "Holidays in India" cache - see sync/festival_dates_sync.py)
export const getClusterDaySales = () => fetchJson('/cluster-day-sales')
export const getFestivalReference = (years) => fetchJson(`/festival-reference${years ? `?years=${years.join(',')}` : ''}`)
export const syncFestivalReference = () => fetchJson('/festival-reference/sync', { method: 'POST' })

// app-state
export const getAppState = () => fetchJson('/app-state')
export const putAppState = (payload) => jsonPost('/app-state', payload, 'PUT')

// festival-changelog
export const getFestivalChangelog = (rangeKey) => fetchJson(`/festival-changelog${rangeKey ? `?range_key=${encodeURIComponent(rangeKey)}` : ''}`)
export const putFestivalChangelog = (payload) => jsonPost('/festival-changelog', payload, 'PUT')

// salesdata-link-selection
export const getSalesdataLinkSelection = (sourceType) => fetchJson(`/salesdata-link-selection/${sourceType}`)
export const putSalesdataLinkSelection = (sourceType, payload) => jsonPost(`/salesdata-link-selection/${sourceType}`, payload, 'PUT')

// scan endpoints
export const getSalesdataLink = (refresh) => fetchJson(`/salesdata/link${refresh ? '?refresh=1' : ''}`)
export const getSalesdataLinkDaywise = (refresh) => fetchJson(`/salesdata/link-daywise${refresh ? '?refresh=1' : ''}`)
export const startLinkScan = (sourceType, refresh) =>
  fetchJson(`/salesdata/link/start?source_type=${sourceType}${refresh ? '&refresh=1' : ''}`, { method: 'POST' })
export const pollLinkScan = (jobId) => fetchJson(`/salesdata/link/poll/${jobId}`)
export const runReindex = (payload) => jsonPost('/salesdata/reindex', payload)
export const startReindex = (payload) => jsonPost('/salesdata/reindex/start', payload)
export const getSalesSnapshotSummary = (source) => fetchJson(`/salesdata/snapshot-summary?source=${source}`)
// A completed job's result now streams straight off disk (see
// get_reindex_result_stream_path in scans.py) with no server-side size cap -
// but a large combined multi-month day-wise result (400+MB) can crash the
// BROWSER TAB itself trying to JSON.parse and hold that much in memory
// (reproduced live). Past this threshold, skip the parse: cancel the
// in-flight body (so the bytes aren't downloaded twice for nothing) and
// return a small marker the caller uses to offer a direct file download
// instead of an in-page table. A normal single/few-month run comfortably
// stays under this and behaves exactly as before.
const REINDEX_PREVIEW_MAX_BYTES = 80 * 1024 * 1024

export async function pollReindex(jobId) {
  const res = await fetch(`${BASE}/salesdata/reindex/poll/${jobId}`, { credentials: 'same-origin' })
  if (res.status === 401) {
    window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`
    throw new Error('Not authenticated')
  }
  if (!res.ok) {
    let msg = `HTTP ${res.status}`
    try { const e = await res.json(); msg = typeof e.detail === 'string' ? e.detail : JSON.stringify(e.detail ?? e) } catch {}
    throw new Error(msg)
  }
  const contentLength = +(res.headers.get('content-length') || 0)
  if (contentLength > REINDEX_PREVIEW_MAX_BYTES) {
    res.body?.cancel?.()
    // csvUrl(view): every download in this app is a CSV - never hand the
    // user a raw JSON file. See salesdata/reindex/csv/{job_id} (router.py) /
    // reindex_csv_worker.py, which converts the same result server-side,
    // in its own process, into the wide or stacked CSV shape.
    return {
      ok: true, status: 'too_large', contentLength, jobId,
      csvUrl: (view) => `${BASE}/salesdata/reindex/csv/${jobId}?view=${view}`,
    }
  }
  return res.json()
}
export const getReindexCacheStatus = (payload) => jsonPost('/salesdata/reindex/cache-status', payload)
export const getSourceSchema = (sourceType) => fetchJson(`/salesdata/schema/${sourceType}`)
