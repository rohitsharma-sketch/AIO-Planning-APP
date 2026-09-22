import { useState } from 'react'
import { suggestFestivalNames, resolveFestivalDefaults } from '../../lib/festivalData'

const DAY_COLS = [
  ['pre', 'Pre (days)', 'Days before the core festival', 0],
  ['core', 'Core (days)', 'Core festival days starting from reference date', 1],
  ['post', 'Post (days)', 'Days after the core festival', 0],
]

export default function FestivalTable({ festivals, onChange, onAdd, onReset, onBulkSet, onDayFieldChange, onIndependentToggle, onFestivalPicked, isPlanner, refYear, futYear }) {
  const [dragIdx, setDragIdx] = useState(null)
  const [dragOverIdx, setDragOverIdx] = useState(null)
  // Header bulk-set boxes, one per day column. Kept as strings so an empty box
  // stays empty (the old app's "all" placeholder state) instead of collapsing
  // to 0.
  const [bulk, setBulk] = useState({ pre: '', core: '', post: '' })
  // Festival Name autocomplete: which row's dropdown is open (index, or null)
  // and the current suggestion list for it. Suggestions come from FESTIVAL_DB
  // (name + aliases) - see suggestFestivalNames() in lib/festivalData.js. Picking
  // one auto-fills ref/fut dates (for the CURRENTLY set ref/fut year) and
  // pre/core/post, same as the old app's autofill-on-name-match behaviour.
  const [suggestIdx, setSuggestIdx] = useState(null)
  const [suggestions, setSuggestions] = useState([])
  // Screen position of the currently-focused name input, so the dropdown can
  // render as position:fixed at that spot - the table body scrolls (.fest-
  // table-scroll has overflow-x:auto, which computes overflow-y:auto too), so
  // a plain position:absolute dropdown gets clipped by that scroll container
  // for any row near the bottom of a long festival list.
  const [suggestPos, setSuggestPos] = useState(null)

  function openSuggestions(idx, value, inputEl) {
    const r = inputEl.getBoundingClientRect()
    setSuggestPos({ top: r.bottom, left: r.left, width: r.width })
    setSuggestIdx(idx)
    setSuggestions(suggestFestivalNames(value))
  }

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

  // Festival Name typed: update the name as normal, and refresh the suggestion
  // dropdown for this row from FESTIVAL_DB's names/aliases.
  function updateName(idx, value, inputEl) {
    updateField(idx, 'name', value)
    openSuggestions(idx, value, inputEl)
  }

  // A suggestion was picked: snap the name to the canonical spelling and, if
  // FESTIVAL_DB/FESTIVAL_DATES has real dates for the CURRENT ref/fut year,
  // auto-fill refDate/futDate/pre/core/post too - stays cluster-local (plain
  // onChange), same as any other name/date edit; it does not cascade like a
  // pre/core/post edit on an EXISTING shared festival would.
  function pickSuggestion(idx, name) {
    const defaults = resolveFestivalDefaults(name, refYear, futYear)
    const next = festivals.map((f, i) => i === idx ? { ...f, name, ...(defaults || {}) } : f)
    onChange(next)
    setSuggestIdx(null)
    setSuggestions([])
    // Only a catalog pick (real FESTIVAL_DB dates, not a hand-typed custom
    // name) is eligible to auto-copy into other saved templates - see
    // handleFestivalPicked in index.jsx. A custom name has no per-year dates
    // to resolve for another template's own ref/fut period.
    if (defaults) onFestivalPicked?.(name)
  }

  // Pre/Core/Post edits cascade to every OTHER cluster's festival with the
  // same name (index.jsx's handleDayFieldChange does the actual cross-cluster
  // write + persist) - unlike name/date edits, which stay local to this
  // cluster via updateField/onChange above. Requested so a shared festival's
  // window doesn't have to be kept in sync by hand, cluster by cluster.
  function updateDayField(idx, field, value) {
    onDayFieldChange(idx, field, value)
  }

  // +/- buttons flanking each Pre/Core/Post box - ported from stepFest()
  // (calendar_engine.html lines 2001-2008), including its per-field minimum
  // (core can't go below 1, pre/post can't go below 0).
  function step(idx, field, min, delta) {
    const cur = Number(festivals[idx]?.[field]) || 0
    updateDayField(idx, field, Math.max(min, cur + delta))
  }

  // Removal persists to the shared DB immediately and there is no undo (a deleted
  // festival can only be recreated by hand), so a stray click on the narrow x must
  // be cancellable. Plain browser confirm() - the codebase has no other
  // destructive-action confirmation pattern to follow.
  function removeRow(idx) {
    const label = festivals[idx]?.name || 'this festival'
    if (!window.confirm(`Delete "${label}"? This is saved immediately and cannot be undone.`)) return
    onChange(festivals.filter((_, i) => i !== idx))
  }

  // Header bulk-set - ported from applyHeaderBulk() (calendar_engine.html lines
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
              <th title="Exempt this cluster's row from the cross-cluster Pre/Core/Post cascade for this one festival - it neither pushes its own edits out nor gets overwritten by another cluster's edit, but stays synced on every other festival">Independent</th>
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
                <td>
                  <input value={f.name} disabled={!isPlanner} autoComplete="off"
                    onChange={e => updateName(idx, e.target.value, e.target)}
                    onFocus={e => { if (f.name) openSuggestions(idx, f.name, e.target) }}
                    onBlur={() => setTimeout(() => setSuggestIdx(s => s === idx ? null : s), 150)} />
                  {isPlanner && suggestIdx === idx && suggestions.length > 0 && suggestPos && (
                    <ul className="fest-name-suggest" style={{ top: suggestPos.top, left: suggestPos.left, minWidth: suggestPos.width }}>
                      {suggestions.map(name => (
                        <li key={name} onMouseDown={e => { e.preventDefault(); pickSuggestion(idx, name) }}>{name}</li>
                      ))}
                    </ul>
                  )}
                </td>
                <td><input type="date" value={f.refDate} disabled={!isPlanner} onChange={e => updateField(idx, 'refDate', e.target.value)} /></td>
                <td><input type="date" value={f.futDate} disabled={!isPlanner} onChange={e => updateField(idx, 'futDate', e.target.value)} /></td>
                <td style={{ textAlign: 'center' }}>
                  <input type="checkbox" checked={!!f.independent} disabled={!isPlanner}
                    title="Exempt this row from the cross-cluster cascade"
                    onChange={e => onIndependentToggle(idx, e.target.checked)} />
                </td>
                {DAY_COLS.map(([field, , , min]) => (
                  <td key={field}>
                    <div className="day-cell">
                      {isPlanner && <button type="button" className="day-step" tabIndex={-1} title="-1 day" onClick={() => step(idx, field, min, -1)}>-</button>}
                      <input type="number" min={min} value={f[field]} disabled={!isPlanner} onChange={e => updateDayField(idx, field, +e.target.value)} />
                      {isPlanner && <button type="button" className="day-step" tabIndex={-1} title="+1 day" onClick={() => step(idx, field, min, 1)}>+</button>}
                    </div>
                  </td>
                ))}
                <td>{isPlanner && <button onClick={() => removeRow(idx)} title="Remove">x</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Footer action bar - ported from calendar_engine.html lines 821-824.
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
