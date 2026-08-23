// Browser-local autosave: keeps in-progress configuration edits across a reload
// or an accidental tab close, without any explicit "save" click. Nothing here
// talks to the server — a real Save still persists to config/levers.json; this
// is only the safety net for what hasn't been saved yet.
import { useEffect, useRef } from 'react'

const NS = 'aop.autosave.'

export function loadAutosave(key, fallback = null) {
  try {
    const raw = localStorage.getItem(NS + key)
    return raw != null ? JSON.parse(raw) : fallback
  } catch { return fallback }
}

export function saveAutosave(key, value) {
  try { localStorage.setItem(NS + key, JSON.stringify(value)) } catch { /* storage full/blocked — draft is best-effort */ }
}

export function clearAutosave(key) {
  try { localStorage.removeItem(NS + key) } catch {}
}

/**
 * Debounced persistence of `value` under `key`. While `enabled` is true, writes
 * settle `delay` ms after the last change. The moment `enabled` goes false, any
 * stored draft for `key` is cleared immediately (e.g. once changes are saved for
 * real, or discarded, the local safety-net copy is no longer needed).
 */
export function useAutosave(key, value, { enabled = true, delay = 500 } = {}) {
  const timer = useRef(null)
  // Tracks whether this hook instance has ever been "enabled" before. Without this,
  // a component that mounts not-dirty (the normal case, before an async restore has
  // even run) would immediately wipe out the very draft it's about to restore —
  // enabled starts false on every mount, and that must NOT be treated as "just
  // saved/discarded, clear the draft". Only a real true→false transition clears.
  const wasEnabled = useRef(false)
  useEffect(() => {
    clearTimeout(timer.current)
    if (!enabled) {
      if (wasEnabled.current) clearAutosave(key)
      wasEnabled.current = false
      return
    }
    wasEnabled.current = true
    timer.current = setTimeout(() => saveAutosave(key, value), delay)
    return () => clearTimeout(timer.current)
  }, [key, value, enabled, delay]) // eslint-disable-line react-hooks/exhaustive-deps
}

/**
 * Keeps a bounded, most-recently-used list of ids under `indexKey` (e.g. session
 * ids), evicting the oldest entry's own autosave key once the list exceeds `keep`.
 * Call once per id you start autosaving under a per-id key.
 */
export function touchAutosaveIndex(indexKey, id, keyForId, keep = 8) {
  const idx = loadAutosave(indexKey, [])
  const next = [id, ...idx.filter(x => x !== id)].slice(0, keep)
  idx.filter(x => !next.includes(x)).forEach(old => clearAutosave(keyForId(old)))
  saveAutosave(indexKey, next)
}
