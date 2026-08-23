import { useState } from 'react'
import { parseDate, fmtISO } from '../../lib/dateUtils'
import { DEFAULT_FESTIVALS } from '../../lib/festivalData'

// ─── Bulk Adjust Panels ────────────────────────────────────────────────────
// Two collapsible cards matching the old app's "Bulk Future Date Shift" and
// "Bulk Pre / Core / Post Adjust" (old `Calendar Engine/calendar_engine.html`
// lines ~682-757, JS at lines ~2207-2320).
//
// Known, documented simplifications vs. the old app (task-7-brief.md already
// calls out the month-pill scope removal; this file's NOTE below covers the
// rest found while porting):
//
// 1. Month-pill scoping (old `buildMonthPills()`/`#monthPillsContainer`,
//    `bulkShiftScope`/`bulkDaysScope` = "select") is not ported. Both panels
//    here always apply to every festival in the active cluster. Per the
//    brief, this is intentional — month-scoped bulk editing is a secondary
//    convenience, not required for the tab to be functional.
//
// 2. "Apply & Save" for Pre/Core/Post always writes all three fields (old app
//    let you leave any of the three input boxes blank to skip that column;
//    here all three fields always participate, using their current numeric
//    state). This mirrors the "apply to all, unconditionally" simplification
//    already adopted for scoping above, so this file's Pre/Core/Post inputs
//    default to 0 rather than blank.
//
// 3. Pre/Core/Post results are clamped to the old app's minimums (core >= 1,
//    pre/post >= 0) — ported from `applyBulkDays()`'s
//    `Math.max(minVal, next)` — since going below those breaks the
//    downstream day-count assumptions used elsewhere in the tab.
export default function BulkAdjustPanels({ festivals, onChange, isPlanner }) {
  const [shiftOpen, setShiftOpen] = useState(false)
  const [daysOpen, setDaysOpen] = useState(false)
  const [monthOffset, setMonthOffset] = useState(0)
  const [daysMode, setDaysMode] = useState('set')
  const [bulkPre, setBulkPre] = useState(0)
  const [bulkCore, setBulkCore] = useState(0)
  const [bulkPost, setBulkPost] = useState(0)

  function applyShift() {
    if (!isPlanner || !monthOffset) return
    onChange(festivals.map(f => {
      if (!f.futDate) return f
      const d = parseDate(f.futDate)
      if (!d) return f
      d.setMonth(d.getMonth() + Number(monthOffset))
      return { ...f, futDate: fmtISO(d) }
    }))
  }

  // Old app's resetFutDates() (calendar_engine.html:2313-2320) resets futDate
  // to the matching DEFAULT_FESTIVALS entry's futDate (looked up by id) — NOT
  // to the festival's own refDate. refDate and futDate are genuinely
  // different fields a year apart (see lib/festivalData.js), so `futDate =
  // refDate` would silently corrupt every future date. Festivals with no
  // matching id in DEFAULT_FESTIVALS (e.g. custom-added ones) are left
  // untouched, matching the old app.
  function resetDates() {
    if (!isPlanner) return
    onChange(festivals.map(f => {
      const def = DEFAULT_FESTIVALS.find(df => df.id === f.id)
      return def ? { ...f, futDate: def.futDate } : f
    }))
  }

  function applyBulkDays() {
    if (!isPlanner) return
    onChange(festivals.map(f => {
      const nextPre = daysMode === 'set' ? Number(bulkPre) : Number(f.pre) + Number(bulkPre)
      const nextCore = daysMode === 'set' ? Number(bulkCore) : Number(f.core) + Number(bulkCore)
      const nextPost = daysMode === 'set' ? Number(bulkPost) : Number(f.post) + Number(bulkPost)
      return {
        ...f,
        pre: Math.max(0, nextPre),
        core: Math.max(1, nextCore),
        post: Math.max(0, nextPost),
      }
    }))
  }

  return (
    <>
      <div className="card">
        <div className="card-toggle-hdr" onClick={() => setShiftOpen(!shiftOpen)}>
          <h4>Bulk Future Date Shift</h4>
          <span className="toggle-lbl">{shiftOpen ? 'Hide' : 'Show'}</span>
        </div>
        {shiftOpen && (
          <div className="field-row">
            <div className="field">
              <label>Shift By</label>
              <select value={monthOffset} disabled={!isPlanner} onChange={e => setMonthOffset(e.target.value)}>
                {[-3, -2, -1, 0, 1, 2, 3].map(n => <option key={n} value={n}>{n > 0 ? `+${n}` : n} month{Math.abs(n) === 1 ? '' : 's'}</option>)}
              </select>
            </div>
            <button className="btn" disabled={!isPlanner} onClick={applyShift}>Apply Shift</button>
            <button disabled={!isPlanner} onClick={resetDates}>Reset Dates</button>
          </div>
        )}
      </div>

      <div className="card">
        <div className="card-toggle-hdr" onClick={() => setDaysOpen(!daysOpen)}>
          <h4>Bulk Pre / Core / Post Adjust</h4>
          <span className="toggle-lbl">{daysOpen ? 'Hide' : 'Show'}</span>
        </div>
        {daysOpen && (
          <div className="field-row">
            <div className="field">
              <label>Mode</label>
              <select value={daysMode} disabled={!isPlanner} onChange={e => setDaysMode(e.target.value)}>
                <option value="set">Set to value</option>
                <option value="add">Add / Subtract</option>
              </select>
            </div>
            <div className="field">
              <label>Pre</label>
              <input type="number" value={bulkPre} disabled={!isPlanner} onChange={e => setBulkPre(e.target.value)} />
            </div>
            <div className="field">
              <label>Core</label>
              <input type="number" value={bulkCore} disabled={!isPlanner} onChange={e => setBulkCore(e.target.value)} />
            </div>
            <div className="field">
              <label>Post</label>
              <input type="number" value={bulkPost} disabled={!isPlanner} onChange={e => setBulkPost(e.target.value)} />
            </div>
            <button className="btn" disabled={!isPlanner} onClick={applyBulkDays}>Apply &amp; Save</button>
          </div>
        )}
      </div>
    </>
  )
}
