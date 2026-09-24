import { useState, useEffect } from 'react'
import { getAppState, putAppState, getClusterProfiles, putClusterProfiles } from '../lib/api'
import { applyYearToProfiles, yearSyncMessage, loadFestivalReference } from '../lib/festivalData'

// The seven mapping-type strings `lib/engine.js`'s scoreMapping() actually
// assigns to `mappingType` (see its `mtype = ...` branches) - these are the
// exact values the Day-by-Day table's "Mapping Type" column renders, so the
// legend has to list them verbatim to be useful.
//
// This replaces an earlier invented list ('Exact Match', 'Nearest Weekday',
// 'Cross-Month Shift', 'Regional Override', 'Fallback Assignment', 'Manual
// Override', 'Repaired (Excessive Shift)') - none of which the engine has ever
// emitted, making the legend actively misleading. Descriptions are ported from
// the old app's Mapping Type Reference card (calendar_engine.html lines
// 581-591).
const MAPPING_TYPES = [
  ['Festival-to-Festival', 'exact festival day match'],
  ['Festive Relative Day', 'same relative position'],
  ['Same Month + Same Weekday', 'ideal non-festive'],
  ['Same Month + Same Day Type', 'weekday unavailable, weekend/weekday kept'],
  ['Same Month + Nearest Weekday', 'weekday and day type unavailable'],
  ['Previous Month + Same Weekday', 'month boundary shift'],
  ['Next Month + Same Weekday', 'month boundary shift'],
  ['Nearest Available Date', 'last-resort fallback'],
]

// Ported from calendar_engine.html lines 573-577. The swatch colours are the
// same --pre-*/--core-*/--post-* tokens the Day-by-Day badges use, so the
// legend and the table agree; a previous version used --navy3/--navy/--muted/
// --border, which matched nothing on screen.
const CATEGORY_LEGEND = [
  ['var(--pre-bg)', 'var(--pre-border)', 'Pre-Festive', 'build-up window before festival'],
  ['var(--core-bg)', 'var(--core-border)', 'Core Festive', 'primary festival days'],
  ['var(--post-bg)', 'var(--post-border)', 'Post-Festive', 'tail window after festival'],
  ['var(--light)', 'var(--border)', 'Non-Festive', 'weekday-matched days'],
]

export default function VersionSettingTab({ isPlanner, onNavigate }) {
  const [refYear, setRefYear] = useState('')
  const [futYear, setFutYear] = useState('')
  const [maxShift, setMaxShift] = useState('45')
  const [moPri, setMoPri] = useState('prev')
  const [status, setStatus] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    getAppState().then(s => {
      if (s.refYear) setRefYear(s.refYear)
      if (s.futYear) setFutYear(s.futYear)
      if (s.maxShift) setMaxShift(s.maxShift)
      if (s.moPri) setMoPri(s.moPri)
    }).catch(() => {})
  }, [])

  async function save(partial) {
    if (!isPlanner) return
    try {
      await putAppState(partial)
      setStatus({ ok: true, msg: 'Saved' })
    } catch (e) {
      setStatus({ ok: false, msg: e.message })
    }
  }

  // "Create Calendar" - the old app had this button on this tab
  // (calendar_engine.html lines 2922-2938, createCalendar()); the React port
  // dropped it, leaving this tab with no way to act on a year change at all.
  //
  // VersionSettingTab does not own the cluster profiles (CalendarisationTab
  // does), so this fetches them, re-syncs every cluster's every festival to the
  // configured years via applyYearToProfiles(), writes them back, and then hands
  // over to the Calendarisation tab - which remounts and re-fetches, so it opens
  // showing the freshly re-synced dates.
  //
  // Deviation from the old app: it does NOT auto-run the engine on arrival. The
  // engine lives in CalendarisationTab's own state and isn't reachable from here
  // without lifting that whole state up. The user lands on Calendarisation with
  // correct dates already applied and clicks its "Create Calendar" - one extra
  // click, no correctness difference.
  async function createCalendar() {
    if (!isPlanner || busy) return
    const ry = Number(refYear), fy = Number(futYear)
    if (!ry || !fy || ry < 1900 || ry > 2099 || fy < 1900 || fy > 2099) {
      setStatus({ ok: false, msg: 'Years must be between 1900 and 2099.' })
      return
    }
    if (ry === fy) {
      setStatus({ ok: false, msg: 'Reference and Future year must be different.' })
      return
    }
    setBusy(true)
    try {
      // Save the years first: the inputs persist on blur, and clicking this
      // button fires blur and click as two independent async saves. Writing them
      // here explicitly means the years are stored before the profiles are
      // rewritten, whatever order those land in.
      await putAppState({ refYear: ry, futYear: fy })
      const { profiles } = await getClusterProfiles()
      await loadFestivalReference()
      const sync = applyYearToProfiles(profiles || [], ry, fy)
      await putClusterProfiles({
        profiles: sync.profiles.map(cp => ({ name: cp.name, region: cp.region, nextId: cp.nextId, festivals: cp.festivals })),
      })
      setStatus({ ok: true, msg: yearSyncMessage(ry, fy, sync.updated, sync.estimated, sync.fallback) })
      if (onNavigate) onNavigate('calendarisation')
    } catch (e) {
      setStatus({ ok: false, msg: e.message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="module-panel">
      <div className="card">
        <div className="card-label">Calendar Years</div>
        <div className="field-row">
          <div className="field">
            <label>Reference Year</label>
            <input type="number" className="year-input" value={refYear} disabled={!isPlanner}
              onChange={e => setRefYear(e.target.value)}
              onBlur={() => save({ refYear })} />
          </div>
          <div style={{ fontSize: '18px', color: 'var(--muted)', alignSelf: 'flex-end', paddingBottom: '4px' }}>-&gt;</div>
          <div className="field">
            <label>Future Year</label>
            <input type="number" className="year-input" value={futYear} disabled={!isPlanner}
              onChange={e => setFutYear(e.target.value)}
              onBlur={() => save({ futYear })} />
          </div>
          <div className="field">
            <label>Max Date Shift</label>
            <input type="number" value={maxShift} disabled={!isPlanner}
              onChange={e => setMaxShift(e.target.value)}
              onBlur={() => save({ maxShift })} />
          </div>
        </div>
        <div style={{ marginTop: '12px' }}>
          <button className="btn" onClick={createCalendar} disabled={!isPlanner || busy}>
            {busy ? 'Updating dates...' : 'Create Calendar'}
          </button>
          <div style={{ fontSize: '11px', color: 'var(--muted)', marginTop: '6px' }}>
            Re-syncs every cluster's festival dates to the years above using the multi-year
            festival date table, then opens the Calendarisation tab.
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-label">Month Priority (non-festive days)</div>
        <div className="radio-group">
          <label className="radio-opt">
            <input type="radio" name="moPri" value="prev" checked={moPri === 'prev'} disabled={!isPlanner}
              onChange={() => { setMoPri('prev'); save({ moPri: 'prev' }) }} />
            Same -&gt; Previous -&gt; Next
            <div className="radio-tip">
              <strong>Shift backward first.</strong> When a non-festive day has no same-month match in
              the future year, it tries the <code>previous</code> month before the next. Good when your
              year runs Jan-Dec.
            </div>
          </label>
          <label className="radio-opt">
            <input type="radio" name="moPri" value="next" checked={moPri === 'next'} disabled={!isPlanner}
              onChange={() => { setMoPri('next'); save({ moPri: 'next' }) }} />
            Same -&gt; Next -&gt; Previous
            <div className="radio-tip">
              <strong>Shift forward first.</strong> When a non-festive day has no same-month match, it
              tries the <code>next</code> month before the previous. Good for fiscal years running
              April-March.
            </div>
          </label>
        </div>
      </div>

      <div className="card">
        <div className="card-label">Festive Category Legend</div>
        <div className="legend">
          {CATEGORY_LEGEND.map(([bg, border, name, desc]) => (
            <div className="leg-item" key={name}>
              <div className="leg-dot" style={{ background: bg, border: `1px solid ${border}` }} />
              <span>{name} - {desc}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <div className="card-label">Mapping Type Reference</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '5px', fontSize: '11px', color: 'var(--muted)' }}>
          {MAPPING_TYPES.map(([type, desc]) => (
            <div key={type}><span className="b-map">{type}</span> {desc}</div>
          ))}
        </div>
      </div>

      {status && <p style={{ color: status.ok ? 'var(--green)' : 'var(--red)' }}>{status.msg}</p>}
    </div>
  )
}
