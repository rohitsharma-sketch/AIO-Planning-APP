import { useState, useEffect } from 'react'
import { listCalendarLibrary, getCalendar, saveCalendar, deleteCalendar, renameCalendar } from '../../lib/api'

// Saved-date format used on every library card, matching the old app's
// renderCalendarLibrary() (calendar_engine.html line ~3849:
// toLocaleDateString('en-IN', {day:'2-digit',month:'short',year:'numeric'})).
function fmtSavedAt(iso) {
  if (!iso) return '-'
  const d = new Date(iso)
  if (isNaN(d)) return '-'
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
}

export default function CalendarLibrary({ onLoad, onSaved, isPlanner, buildSavePayload }) {
  const [items, setItems] = useState([])
  const [status, setStatus] = useState(null)
  const [busy, setBusy] = useState(false)

  function refresh() {
    listCalendarLibrary().then(setItems).catch(e => setStatus({ ok: false, msg: e.message }))
  }

  useEffect(refresh, [])

  // "Lock & Save Calendar" - ported from the old app's saveCalendarToLibrary()
  // (calendar_engine.html lines 3756-3817). Two behaviours are restored here:
  //   1. It prompts for a template name (defaulting to the auto-generated one,
  //      so a plain click-through behaves exactly as it did before), and
  //      cancelling the prompt saves nothing.
  //   2. Re-using an existing entry's name overwrites that entry rather than
  //      piling up duplicates. The backend has no update endpoint (POST
  //      /calendar-library 409s on a duplicate id and there is no PUT), so
  //      "overwrite" is done as delete-then-create, which reaches the same end
  //      state with only the endpoints that already exist.
  // The old app's third behaviour - refusing to save a snapshot whose content is
  // identical to an existing one - is NOT ported: with this backend it would mean
  // GET /calendar-library/{id} for every entry in the library (the list endpoint
  // returns no dayMap/clusters to compare against) on every save, which is not
  // the cheap local check it was against localStorage.
  async function handleSave() {
    if (!isPlanner || busy) return
    let payload
    try {
      payload = buildSavePayload()
    } catch (e) {
      setStatus({ ok: false, msg: e.message })
      return
    }
    const entered = window.prompt(
      'Name this calendar template:\n(Using an existing name overwrites that template with your changes.)',
      payload.name,
    )
    if (entered === null) return           // cancelled - save nothing
    const name = entered.trim()
    if (!name) { setStatus({ ok: false, msg: 'Enter a name to save this calendar.' }); return }

    setBusy(true)
    try {
      const existing = items.find(c => (c.name || '') === name)
      if (existing) await deleteCalendar(existing.id)
      await saveCalendar({ ...payload, name })
      setStatus({ ok: true, msg: existing ? `Template "${name}" updated with your changes` : `Template "${name}" locked & saved` })
      onSaved?.(payload.id, name)
      refresh()
    } catch (e) {
      setStatus({ ok: false, msg: e.message })
    } finally {
      setBusy(false)
    }
  }

  async function handleLoad(id) {
    try {
      const full = await getCalendar(id)
      onLoad(full)
      setStatus(null)
    } catch (e) {
      setStatus({ ok: false, msg: e.message })
    }
  }

  async function handleRename(c) {
    if (!isPlanner) return
    const entered = window.prompt('Rename this calendar:', c.name)
    if (entered === null) return   // cancelled
    const name = entered.trim()
    if (!name || name === c.name) return
    try {
      await renameCalendar(c.id, name)
      setStatus({ ok: true, msg: `Renamed to "${name}"` })
      refresh()
    } catch (e) {
      setStatus({ ok: false, msg: e.message })
    }
  }

  async function handleDelete(id) {
    if (!isPlanner) return
    // Same confirm-before-destroy pattern as deleteSavedCalendar()
    // (calendar_engine.html line ~3821) and FestivalTable.jsx's row delete.
    if (!window.confirm('Delete this saved calendar? This cannot be undone.')) return
    try {
      await deleteCalendar(id)
      setStatus({ ok: true, msg: 'Calendar deleted' })
      refresh()
    } catch (e) {
      setStatus({ ok: false, msg: e.message })
    }
  }

  return (
    <div className="card" id="calLibrary">
      <div className="lib-header">
        <span className="lib-title">
          Calendar Library<span className="lib-count">({items.length})</span>
        </span>
        {isPlanner && (
          <button className="btn lib-save-btn" onClick={handleSave} disabled={busy}>Lock &amp; Save</button>
        )}
      </div>

      {items.length === 0 ? (
        <div className="lib-empty">
          <div className="lib-empty-icon">LK</div>
          <div className="lib-empty-title">No saved calendars yet</div>
          <div className="lib-empty-desc">
            Generate a comparative calendar, then click "Lock &amp; Save" to create a locked snapshot here.
          </div>
        </div>
      ) : (
        <div className="lib-grid">
          {items.map(c => {
            const chips = c.mappingSummary || []
            return (
              <div
                key={c.id}
                className="lib-card"
                role="button"
                tabIndex={0}
                title={`Load "${c.name}" into the editor`}
                onClick={() => handleLoad(c.id)}
                onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleLoad(c.id) } }}
              >
                <div className="lib-card-head">
                  <div className="lib-lock-icon">LK</div>
                  <div style={{ minWidth: 0 }}>
                    <div className="lib-name">
                      {c.name}
                      {/* Every entry in this library is a finalised snapshot: the API exposes
                          only create + delete for a saved calendar (no PUT/edit), so there is
                          no "unlocked/draft" state a badge could distinguish it from. The badge
                          is therefore shown on all of them, as a statement that saved calendars
                          are immutable, rather than driven by a (non-existent) `locked` field. */}
                      <span className="lib-locked-badge">Locked</span>
                    </div>
                    <div className="lib-pair">{c.refYear} -&gt; {c.futYear}</div>
                  </div>
                </div>

                {/* Chip count is days mapped for that cluster (mappingSummary.totalDays,
                    the only per-cluster number the list endpoint returns). The old app's
                    chip showed the cluster's festival count instead - that would cost one
                    full GET per calendar here, so the day count stands in for it. */}
                <div className="lib-clusters">
                  {chips.map(m => (
                    <span key={m.cluster} className="lib-cluster-chip" title={`${m.totalDays} days mapped`}>
                      {m.cluster} ({m.totalDays})
                    </span>
                  ))}
                </div>

                <div className="lib-meta">
                  Saved {fmtSavedAt(c.savedAt)} • {chips.length} cluster{chips.length === 1 ? '' : 's'}
                </div>

                <div className="lib-actions">
                  <button className="btn" onClick={e => { e.stopPropagation(); handleLoad(c.id) }}>Load &amp; Preview</button>
                  {isPlanner && (
                    <button className="btn" onClick={e => { e.stopPropagation(); handleRename(c) }}>Rename</button>
                  )}
                  {isPlanner && (
                    <button className="lib-del-btn" onClick={e => { e.stopPropagation(); handleDelete(c.id) }}>Delete</button>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {status && <p style={{ color: status.ok ? 'var(--green)' : 'var(--red)', fontSize: '12px', margin: '10px 0 0' }}>{status.msg}</p>}
    </div>
  )
}
