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
export const pollReindex = (jobId) => fetchJson(`/salesdata/reindex/poll/${jobId}`)
export const getSourceSchema = (sourceType) => fetchJson(`/salesdata/schema/${sourceType}`)
