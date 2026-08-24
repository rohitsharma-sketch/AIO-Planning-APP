import { useState } from 'react'

const DAY_COLS = [
  ['pre', 'Pre (days)', 'Days before the core festival', 0],
  ['core', 'Core (days)', 'Core festival days starting from reference date', 1],
  ['post', 'Post (days)', 'Days after the core festival', 0],
]

export default function FestivalTable({ festivals, onChange, onAdd, onReset, onBulkSet, isPlanner }) {
  const [dragIdx, setDragIdx] = useState(null)
  const [dragOverIdx, setDragOverIdx] = useState(null)
  // Header bulk-set boxes, one per day column. Kept as strings so an empty box
  // stays empty (the old app's "all" placeholder state) instead of collapsing
  // to 0.
  const [bulk, setBulk] = useState({ pre: '', core: '', post: '' })

  function reorder(from, to) {
    const next = [...festivals]
    const [moved] = next.splice(from, 1)
    next.splice(to, 0, moved)
    onChange(next)
  }

  function updateField(idx, field, value) {
    const next = festivals.map((f, i) => i === idx ? { ...f, [field]: value } : f)
    onChange(next)
  }

  // +/- buttons flanking each Pre/Core/Post box — ported from stepFest()
  // (calendar_engine.html lines 2001-2008), including its per-field minimum
  // (core can't go below 1, pre/post can't go below 0).
  function step(idx, field, min, delta) {
    const cur = Number(festivals[idx]?.[field]) || 0
    updateField(idx, field, Math.max(min, cur + delta))
  }

  // Removal persists to the shared DB immediately and there is no undo (a deleted
  // festival can only be recreated by hand), so a stray click on the narrow × must
  // be cancellable. Plain browser confirm() — the codebase has no other
  // destructive-action confirmation pattern to follow.
  function removeRow(idx) {
    const label = festivals[idx]?.name || 'this festival'
    if (!window.confirm(`Delete "${label}"? This is saved immediately and cannot be undone.`)) return
    onChange(festivals.filter((_, i) => i !== idx))
  }

  // Header bulk-set — ported from applyHeaderBulk() (calendar_engine.html lines
  // 1977-2000). Scope is deliberately the same as the original's: EVERY festival
  // in EVERY cluster, not just the active one (the old code's own comment says
  // "active cluster" but its body loops clusterProfiles.forEach). The confirm()
  // has no old-app equivalent and is added here because, unlike the old
  // localStorage app, this writes straight through to the shared database with
  // no undo, and it is the widest-scoped destructive action on the page.
  function applyBulk(field, min) {
    const raw = bulk[field]
    if (raw === '') return
    const value = Number(raw)
    if (!Number.isFinite(value)) { window.alert('Enter a valid number.'); return }
    const v = Math.max(min, value)
    const label = field[0].toUpperCase() + field.slice(1)
    if (!window.confirm(`Set ${label} to ${v} for EVERY festival in EVERY cluster?\n\nThis is not limited to the cluster you are viewing, is saved immediately, and cannot be undone.`)) return
    // Keep the applied number showing in the box (frozen, not cleared back to
    // the "all" placeholder) so it reads as "this is what's applied everywhere",
    // matching the old app's `inp.value = v`.
    setBulk(b => ({ ...b, [field]: String(v) }))
    onBulkSet(field, v)
  }

  return (
    <>
      <div className="fest-table-scroll">
        <table id="festTable">
          <thead>
            <tr>
              <th style={{ width: '22px' }}></th><th>#</th><th>Festival Name</th><th>Reference Date</th><th>Future Date</th>
              {DAY_COLS.map(([field, label, tip, min]) => (
                <th key={field} title={tip}>
                  {label}
                  {isPlanner && (
                    <div className="hdr-bulk">
                      <input
                        type="number"
                        placeholder="all"
                        title={`Type a number and press Enter (or click OK) to set ${label.split(' ')[0]} for every festival in every cluster`}
                        value={bulk[field]}
                        onChange={e => setBulk(b => ({ ...b, [field]: e.target.value }))}
                        onKeyDown={e => { if (e.key === 'Enter') applyBulk(field, min) }}
                      />
                      <button type="button" onClick={() => applyBulk(field, min)} title="Apply to all clusters">OK</button>
                    </div>
                  )}
                </th>
              ))}
              <th></th>
            </tr>
          </thead>
          <tbody id="festTbody">
            {festivals.map((f, idx) => (
              <tr key={f.id}
                className={dragOverIdx === idx ? 'fest-row-drag-over' : undefined}
                onDragOver={(e) => { if (dragIdx !== null) { e.preventDefault(); setDragOverIdx(idx) } }}
                onDrop={(e) => { e.preventDefault(); setDragOverIdx(null); if (dragIdx !== null && dragIdx !== idx) reorder(dragIdx, idx); setDragIdx(null) }}
              >
                <td className="drag-handle" draggable={isPlanner}
                  onDragStart={() => setDragIdx(idx)}
                  onDragEnd={() => { setDragIdx(null); setDragOverIdx(null) }}
                  title="Drag to reorder">::</td>
                <td>{idx + 1}</td>
                <td><input value={f.name} disabled={!isPlanner} onChange={e => updateField(idx, 'name', e.target.value)} /></td>
                <td><input type="date" value={f.refDate} disabled={!isPlanner} onChange={e => updateField(idx, 'refDate', e.target.value)} /></td>
                <td><input type="date" value={f.futDate} disabled={!isPlanner} onChange={e => updateField(idx, 'futDate', e.target.value)} /></td>
                {DAY_COLS.map(([field, , , min]) => (
                  <td key={field}>
                    <div className="day-cell">
                      {isPlanner && <button type="button" className="day-step" tabIndex={-1} title="-1 day" onClick={() => step(idx, field, min, -1)}>-</button>}
                      <input type="number" min={min} value={f[field]} disabled={!isPlanner} onChange={e => updateField(idx, field, +e.target.value)} />
                      {isPlanner && <button type="button" className="day-step" tabIndex={-1} title="+1 day" onClick={() => step(idx, field, min, 1)}>+</button>}
                    </div>
                  </td>
                ))}
                <td>{isPlanner && <button onClick={() => removeRow(idx)} title="Remove">×</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Footer action bar — ported from calendar_engine.html lines 821-824.
          "Save Settings" is deliberately not ported: this app persists every
          edit immediately through persist(), so an explicit save button would
          be a no-op. "Change Log" already has its own viewer in the sidebar. */}
      <div className="fest-footer">
        {isPlanner && <button type="button" onClick={onAdd} title="Add a new festival row">+ Add Festival</button>}
        {isPlanner && <button type="button" onClick={onReset} title="Replace this cluster's festivals with the built-in defaults">Reset to Defaults</button>}
        <span className="fest-footer-note">Overlapping windows resolved by list order (first defined wins)</span>
      </div>
    </>
  )
}
