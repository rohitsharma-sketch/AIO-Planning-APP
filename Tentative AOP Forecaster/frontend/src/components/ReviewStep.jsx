import { useState, useCallback, useMemo, useEffect } from 'react'
import './ReviewStep.css'
import { apiUrl } from '../lib/apiBase'
import { useShownMonths } from '../lib/horizon'

const MONTHS  = ["Mar'27","Apr'27","May'27","Jun'27","Jul'27","Aug'27","Sep'27","Oct'27","Nov'27","Dec'27","Jan'28","Feb'28","Mar'28"]
const DIVS    = ['GM','KIDS','LADIES','MENS','RETAIL']
const ALL_ROWS = [...DIVS, 'Overall']

function initQuick() { return Object.fromEntries(ALL_ROWS.map(r => [r, ''])) }

export default function ReviewStep({ session, running, onRun, rates, setRates, cellLocks, setCellLocks }) {
  const { n_stores, n_lfl, n_ramp, n_nso, growth_rates, base_sales } = session
  // Rule 1 (2026-09-25): columns/preview show only months whose base month has
  // closed. Rates for the hidden months stay in the plan ("All months" fills
  // them too) so they are ready the day those months close.
  // Month selector (user, 2026-09-26): the closed months are the default, and any month - a future one too - can be
  // picked by hand to set its growth ahead of a future forecast. The pick is remembered in this browser only.
  // Results follows the same selection (lib/horizon.js useShownMonths).
  const { shown: VIS, closed: CLOSED, picked, pick: pickMonths } = useShownMonths()
  const togglePick = m => {
    const next = VIS.includes(m) ? VIS.filter(x => x !== m) : MONTHS.filter(x => x === m || VIS.includes(x))
    if (next.length) pickMonths(next)
  }

  // AOP Overrides (Configure -> Edit Growth % / NSO / AOP) are the user's own figures for those store x division x
  // month cells and replace base x growth there (user, 2026-09-26: keep them, they are optional inputs). Shown here
  // so a growth % typed for an overridden month isn't mistaken for what the run will use.
  const [aopOv, setAopOv] = useState({})   // {month: {cells, lakhs}}
  useEffect(() => {
    fetch(apiUrl('/api/config/aop-overrides')).then(r => (r.ok ? r.json() : []))
      .then(rows => {
        const by = {}
        for (const r of rows) { const b = (by[r.month] ||= { cells: 0, lakhs: 0 }); b.cells++; b.lakhs += r.value }
        setAopOv(by)
      }).catch(() => {})
  }, [])

  const [includeDebug, setIncludeDebug] = useState(false)
  const [quick,        setQuick]        = useState(initQuick)

  // Actuals-source toggle for the LFL preview below: 'own' is AOP's own
  // store_actuals sync (base_sales.LFL, already in `session`) - 'reindexed'
  // is Calendar Engine's own saved month-wise reindex output, fetched lazily
  // on first switch so a review that never touches the toggle never pays for
  // it. These are two INDEPENDENT computations of "the same" LFL actuals
  // (see db/reindexed_base_sales.py) - the toggle exists so a planner can
  // compare AOP's replica against Calendar Engine's authoritative output.
  const [actualsSource, setActualsSource] = useState('own')
  const [reindexed, setReindexed] = useState(null)      // { base_sales, hasAttribute, availableMonths, note }
  const [reindexedLoading, setReindexedLoading] = useState(false)
  const [reindexedError, setReindexedError] = useState(null)

  useEffect(() => {
    if (actualsSource !== 'reindexed' || reindexed || reindexedLoading) return
    setReindexedLoading(true)
    fetch(apiUrl('/api/config/base-sales-reindexed'))
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
      .then(data => setReindexed(data))
      .catch(e => setReindexedError(e.message))
      .finally(() => setReindexedLoading(false))
  }, [actualsSource, reindexed, reindexedLoading])

  const activeLflBase = actualsSource === 'reindexed' ? (reindexed?.base_sales ?? null) : (base_sales?.LFL ?? null)

  const isLocked   = (row, m) => cellLocks[row]?.[m] ?? false
  const isChanged  = (row, m) => {
    const src = row === 'Overall' ? 'GM' : row
    return String(growth_rates?.[src]?.[m] ?? 0) !== rates[row]?.[m]
  }
  const anyChanged = ALL_ROWS.some(row => MONTHS.some(m => isChanged(row, m)))

  const toggleCellLock = (row, m) =>
    setCellLocks(prev => ({ ...prev, [row]: { ...prev[row], [m]: !prev[row][m] } }))

  const allLocked = ALL_ROWS.every(row => MONTHS.every(m => isLocked(row, m)))
  const toggleAllLocks = () => {
    const wantLock = !allLocked   // any cell unlocked → lock everything; else unlock everything
    const l = {}
    for (const row of ALL_ROWS) { l[row] = {}; for (const m of MONTHS) l[row][m] = wantLock }
    setCellLocks(l)
  }

  const setCell = (row, m, val) => {
    if (isLocked(row, m)) return
    setRates(prev => ({ ...prev, [row]: { ...prev[row], [m]: val } }))
    setCellLocks(prev => ({ ...prev, [row]: { ...prev[row], [m]: false } }))
  }

  const applyQuick = (row) => {
    const v = quick[row].trim()
    if (v === '' || isNaN(parseFloat(v))) return
    // Apply only to UNLOCKED cells — locked cells are protected
    setRates(prev => {
      const next = { ...prev, [row]: { ...prev[row] } }
      for (const m of MONTHS) {
        if (!cellLocks[row]?.[m]) next[row][m] = v
      }
      return next
    })
  }

  const resetRates = () => {
    const r = {}
    for (const row of ALL_ROWS) {
      r[row] = {}
      const src = row === 'Overall' ? 'GM' : row
      for (const m of MONTHS) r[row][m] = String(growth_rates?.[src]?.[m] ?? 0)
    }
    setRates(r)
    setQuick(initQuick())
    // Re-lock all cells back to file defaults
    const l = {}
    for (const row of ALL_ROWS) { l[row] = {}; for (const m of MONTHS) l[row][m] = true }
    setCellLocks(l)
  }

  const buildOverrides = useCallback(() => {
    if (!anyChanged) return { growth_overrides: null, overall_override: null }

    // Overall row — fallback for divisions with no explicit per-div changes
    let overall_override = null
    for (const m of MONTHS) {
      const orig = growth_rates?.['GM']?.[m] ?? 0
      const val  = parseFloat(rates['Overall']?.[m])
      if (!isNaN(val) && val !== orig) {
        if (!overall_override) overall_override = {}
        overall_override[m] = val
      }
    }

    const overrides = {}
    for (const div of DIVS) {
      // Include division if any month changed OR any month is locked.
      // Locked cells must be sent as explicit overrides so the engine
      // treats this division as "fixed" and never scales it via overall_override.
      const hasDivChange = MONTHS.some(m => {
        const orig = growth_rates?.[div]?.[m] ?? 0
        const val  = parseFloat(rates[div]?.[m])
        return !isNaN(val) && val !== orig
      })
      const hasDivLock = MONTHS.some(m => cellLocks[div]?.[m])
      if (hasDivChange || hasDivLock) {
        // Send ALL 13 months so overall_override cannot bleed into this division.
        overrides[div] = {}
        for (const m of MONTHS) {
          const val = parseFloat(rates[div]?.[m])
          overrides[div][m] = isNaN(val) ? (growth_rates?.[div]?.[m] ?? 0) : val
        }
      }
    }

    return {
      growth_overrides: Object.keys(overrides).length ? overrides : null,
      overall_override,
    }
  }, [rates, growth_rates, anyChanged])

  // ── Live forecast preview (LFL only, quarterly) ───────────────────────────
  const QTRS = [
    { label: 'Q1',        months: ["Apr'27","May'27","Jun'27"] },
    { label: 'Q2',        months: ["Jul'27","Aug'27","Sep'27"] },
    { label: 'Q3',        months: ["Oct'27","Nov'27","Dec'27"] },
    { label: 'Q4',        months: ["Jan'28","Feb'28","Mar'28"] },
  ].map(q => ({ ...q, months: q.months.filter(m => VIS.includes(m)) })).filter(q => q.months.length)
  const QTR_LABELS = [...QTRS.map(q => q.label), 'Grand TTL']

  const livePreview = useMemo(() => {
    if (!activeLflBase) return null
    // base_sales (and everything derived from it here) is already Rs Lakhs -
    // the app's one consistent unit everywhere else (AOP Review's own inputs,
    // the AOP overrides grid, division-aop-summary). Generic K/M scaling on
    // top of that just relabels an already-Lakhs number as if it were a raw
    // rupee figure - "8.0K" for a true value of 8,000 Lakhs (₹80 Cr) reads as
    // "eight thousand" of nothing in particular. Show the real Lakhs number
    // instead, comma-grouped Indian-style for readability at these magnitudes.
    const fmt = v => v.toLocaleString('en-IN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })

    // Compute LFL monthly forecast per division
    const lflByDiv = {}
    for (const div of DIVS) {
      const base = activeLflBase?.[div] ?? {}
      lflByDiv[div] = {}
      for (const m of MONTHS) {
        const b = base[m] ?? 0
        const g = parseFloat(rates[div]?.[m] ?? 0) / 100
        lflByDiv[div][m] = b * (1 + g)
      }
    }

    // Aggregate to quarters
    const rows = DIVS.map(div => {
      const qVals = {}
      let grand = 0
      for (const { label, months } of QTRS) {
        const sum = months.reduce((s, m) => s + (lflByDiv[div][m] ?? 0), 0)
        qVals[label] = sum
        grand += sum
      }
      qVals['Grand TTL'] = grand
      return { div, qVals }
    })

    // Grand total row across all divisions
    const grandRow = {}
    for (const lbl of QTR_LABELS)
      grandRow[lbl] = rows.reduce((s, r) => s + (r.qVals[lbl] ?? 0), 0)

    // Effective growth % per division per quarter
    const gRows = DIVS.map(div => {
      const base = activeLflBase?.[div] ?? {}
      const gVals = {}
      let totalBase = 0, totalFcst = 0
      for (const { label, months } of QTRS) {
        const qBase = months.reduce((s, m) => s + (base[m] ?? 0), 0)
        const qFcst = months.reduce((s, m) => s + (lflByDiv[div]?.[m] ?? 0), 0)
        gVals[label] = qBase > 0 ? ((qFcst - qBase) / qBase) * 100 : 0
        totalBase += qBase
        totalFcst += qFcst
      }
      gVals['Grand TTL'] = totalBase > 0 ? ((totalFcst - totalBase) / totalBase) * 100 : 0
      return { div, gVals }
    })
    // Grand TTL growth row
    const gGrand = {}
    for (const { label, months } of QTRS) {
      const qBase = DIVS.reduce((s, d) => s + months.reduce((ss, m) => ss + (activeLflBase?.[d]?.[m] ?? 0), 0), 0)
      const qFcst = DIVS.reduce((s, d) => s + months.reduce((ss, m) => ss + (lflByDiv[d]?.[m] ?? 0), 0), 0)
      gGrand[label] = qBase > 0 ? ((qFcst - qBase) / qBase) * 100 : 0
    }
    const allBase = DIVS.reduce((s, d) => s + VIS.reduce((ss, m) => ss + (activeLflBase?.[d]?.[m] ?? 0), 0), 0)
    const allFcst = DIVS.reduce((s, d) => s + VIS.reduce((ss, m) => ss + (lflByDiv[d]?.[m] ?? 0), 0), 0)
    gGrand['Grand TTL'] = allBase > 0 ? ((allFcst - allBase) / allBase) * 100 : 0

    const fmtG = v => `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`

    return { rows, grandRow, gRows, gGrand, fmt, fmtG }
  }, [rates, activeLflBase, VIS])

  const handleRun = () => {
    const { growth_overrides, overall_override } = buildOverrides()
    onRun('classic', includeDebug, growth_overrides, overall_override)
  }

  const renderRow = (row, isOverall = false) => (
    <tr key={row} className={isOverall ? 'overall-row-tr' : ''}>
      <td className={`div-cell ${isOverall ? 'overall-div-label' : ''}`}>{row}</td>

      {/* Per-row quick-set (skips locked cells) */}
      <td className={`quickset-cell ${isOverall ? 'overall-quickset-cell' : ''}`}>
        <div className="quickset-wrap">
          <input
            className="quickset-input"
            type="number" step="0.1"
            placeholder="—"
            value={quick[row]}
            onChange={e => setQuick(prev => ({ ...prev, [row]: e.target.value }))}
            onKeyDown={e => e.key === 'Enter' && applyQuick(row)}
          />
          <button
            className="quickset-btn"
            onClick={() => applyQuick(row)}
            disabled={quick[row].trim() === ''}
            title="Apply to every unlocked month, shown or not"
          >Apply</button>
        </div>
      </td>

      {/* Individual month cells */}
      {VIS.map(m => {
        const v      = rates[row]?.[m] ?? '0'
        const num    = parseFloat(v)
        const locked = isLocked(row, m)
        const chg    = isChanged(row, m)
        return (
          <td key={m} className={`rate-cell-wrap ${chg && !locked ? 'rate-changed' : ''} ${locked ? 'cell-locked' : ''}`}>
            <div className="cell-inner">
              <input
                className={`rate-input ${!isNaN(num) && num > 0 ? 'pos' : num < 0 ? 'neg' : ''}`}
                type="number" step="0.1"
                value={v}
                disabled={locked}
                onChange={e => setCell(row, m, e.target.value)}
              />
              <button
                className={`cell-lock-btn ${locked ? 'cell-lock-btn--on' : ''}`}
                onClick={() => toggleCellLock(row, m)}
                title={locked ? `Unlock ${row} ${m}` : `Lock ${row} ${m}`}
                tabIndex={-1}
              >
                {locked ? '🔒' : '🔓'}
              </button>
            </div>
          </td>
        )
      })}
    </tr>
  )

  return (
    <div className="review-wrap">
      {/* Back/forward is the header stepper (App.jsx) - shown on 8000 and 8010 alike since 2026-09-25,
          Configure always reachable, Results once results exist - so the duplicate top/bottom nav
          buttons here were dropped in the UI declutter (2026-10-07). */}
      <div className="review-header">
        <div>
          <h2 className="review-title">Review inputs</h2>
          <p className="review-sub">Edit growth rates per division and month. Lock individual cells to protect them.</p>
          <p className="review-counts">
            <b>{n_stores ?? '—'}</b> stores · <b className="count-num--lfl">{n_lfl ?? '—'}</b> LfL · <b className="count-num--ramp">{n_ramp ?? '—'}</b> Ramp · <b className="count-num--nso">{n_nso ?? '—'}</b> NSO
          </p>
        </div>
        <div style={{display:'flex', alignItems:'center', gap:10, alignSelf:'flex-start', marginTop:4}}>
          {(anyChanged || !allLocked) && <span className="autosave-badge" title="Saved to this browser — restores automatically if you reload">Autosaved locally</span>}
          {anyChanged && <button className="btn-sm-outline" onClick={resetRates}>Reset all</button>}
        </div>
      </div>

      <div className="card growth-card">
        <div className="growth-card-header">
          <h3 className="section-title" style={{marginBottom: 0, cursor: 'help'}}
              title={'Hover any cell to reveal its lock control. Locked cells are skipped by "All months", which also fills months not shown. Divisions and Overall are independent.'}>
            Growth % — division × month
          </h3>
          <details className="aop-menu aop-menu--panel aop-menu--right" style={{marginLeft: 'auto'}}>
            <summary>Months · {VIS.length} of {MONTHS.length} ▾</summary>
            <div className="aop-menu-pop">
              <div className="aop-menu-group" role="group" aria-label="Months shown">
                {MONTHS.map(m => (
                  <button key={m} type="button"
                    className={`rv-month-chip ${VIS.includes(m) ? 'rv-month-chip--on' : ''} ${CLOSED.includes(m) ? '' : 'rv-month-chip--future'}`}
                    aria-pressed={VIS.includes(m)}
                    title={CLOSED.includes(m) ? m : `${m} - its base month has not closed yet (future forecast)`}
                    onClick={() => togglePick(m)}>{m}</button>
                ))}
              </div>
              <div className="aop-menu-group">
                <button type="button" className="link-btn" onClick={() => pickMonths(MONTHS)}>All</button>
                {picked && <button type="button" className="link-btn" onClick={() => pickMonths(null)}>Closed months only</button>}
              </div>
            </div>
          </details>
          <button
            className={`lock-all-btn ${allLocked ? 'lock-all-btn--locked' : ''}`}
            onClick={toggleAllLocks}
            title={allLocked ? 'Unlock every cell' : 'Lock every cell'}
          >
            <span className="lock-all-label">{allLocked ? 'Unlock all' : 'Lock all'}</span>
          </button>
        </div>
        <div className="table-scroll">
          <table className="growth-table">
            <thead>
              <tr>
                <th>Division</th>
                <th className="th-quickset">All months</th>
                {VIS.map(m => <th key={m}>{m}{aopOv[m] && <span className="th-aop-ov" title="Has AOP Overrides - see the note below">AOP</span>}</th>)}
              </tr>
            </thead>
            <tbody>
              {DIVS.map(div => renderRow(div))}
              {renderRow('Overall', true)}
            </tbody>
          </table>
        </div>

        {anyChanged && (
          <p className="growth-note" style={{color:'var(--navy3)'}}>
            Growth rates edited — changes apply on next run.
          </p>
        )}
        {Object.keys(aopOv).length > 0 && (
          <details className="growth-note rv-aop-ov">
            <summary>AOP overrides in {Object.keys(aopOv).length} month{Object.keys(aopOv).length === 1 ? '' : 's'}</summary>
            {Object.entries(aopOv).map(([m, o]) => (
              <p key={m} className="growth-note growth-note--aop">
                <b>{m}:</b> {o.cells.toLocaleString('en-IN')} store × division cells use your AOP Overrides
                ({(o.lakhs / 100).toLocaleString('en-IN', { maximumFractionDigits: 1 })} Cr, all store types) instead of base × growth.
                Change or clear them in Configure → Edit Growth % / NSO / AOP → AOP Overrides.
              </p>
            ))}
          </details>
        )}
      </div>

      <div className="actuals-source-toggle">
        <span className="actuals-source-label">LFL actuals source:</span>
        <div className="actuals-source-btns">
          <button
            className={`actuals-source-btn ${actualsSource === 'own' ? 'active' : ''}`}
            onClick={() => setActualsSource('own')}
          >Actuals</button>
          <button
            className={`actuals-source-btn ${actualsSource === 'reindexed' ? 'active' : ''}`}
            onClick={() => setActualsSource('reindexed')}
          >Re-indexed Sales</button>
        </div>
        {actualsSource === 'reindexed' && reindexedLoading && (
          <span className="actuals-source-status">Loading Calendar Engine's reindexed sales…</span>
        )}
        {actualsSource === 'reindexed' && reindexedError && (
          <span className="actuals-source-status actuals-source-status--err">Couldn't load: {reindexedError}</span>
        )}
        {actualsSource === 'reindexed' && reindexed?.note && (
          <span className="actuals-source-status actuals-source-status--warn">{reindexed.note}</span>
        )}
      </div>

      {livePreview && (
        <div className="preview-row-wrap">
          {/* ── Values table ── */}
          <div className="card preview-card">
            <h3 className="section-title" style={{cursor: 'help'}} title="Live LFL estimate, updates as you edit growth rates.">LFL Forecast — Quarterly (Rs. Lakhs)</h3>
            <div className="table-scroll">
              <table className="growth-table preview-table">
                <colgroup>
                  <col style={{width:80}} />
                  <col style={{width:88}} /><col style={{width:88}} /><col style={{width:88}} /><col style={{width:88}} />
                  <col style={{width:96}} />
                </colgroup>
                <thead>
                  <tr>
                    <th style={{textAlign:'left'}}>Division</th>
                    {QTRS.map(q => <th key={q.label}>{q.label}<span className="qtr-sub">{q.months[0].slice(0, 3)}{q.months.length > 1 ? `–${q.months[q.months.length - 1].slice(0, 3)}` : ''}</span></th>)}
                    <th className="grand-ttl-col">Grand TTL</th>
                  </tr>
                </thead>
                <tbody>
                  {livePreview.rows.map(({ div, qVals }) => (
                    <tr key={div} className="preview-div-row">
                      <td className="preview-div-cell">{div}</td>
                      {QTRS.map(({ label: q }) => <td key={q} className="preview-val">{livePreview.fmt(qVals[q])}</td>)}
                      <td className="preview-val grand-ttl-val">{livePreview.fmt(qVals['Grand TTL'])}</td>
                    </tr>
                  ))}
                  <tr className="preview-grand-total">
                    <td>Grand TTL</td>
                    {QTRS.map(({ label: q }) => <td key={q}>{livePreview.fmt(livePreview.grandRow[q])}</td>)}
                    <td>{livePreview.fmt(livePreview.grandRow['Grand TTL'])}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* ── Effective growth % table ── */}
          <div className="card preview-card">
            <h3 className="section-title" style={{cursor: 'help'}} title="Weighted average growth % per division per quarter.">Effective Growth % — LFL</h3>
            <div className="table-scroll">
              <table className="growth-table preview-table">
                <colgroup>
                  <col style={{width:80}} />
                  <col style={{width:88}} /><col style={{width:88}} /><col style={{width:88}} /><col style={{width:88}} />
                  <col style={{width:96}} />
                </colgroup>
                <thead>
                  <tr>
                    <th style={{textAlign:'left'}}>Division</th>
                    {QTRS.map(q => <th key={q.label}>{q.label}<span className="qtr-sub">{q.months[0].slice(0, 3)}{q.months.length > 1 ? `–${q.months[q.months.length - 1].slice(0, 3)}` : ''}</span></th>)}
                    <th className="grand-ttl-col">Grand TTL</th>
                  </tr>
                </thead>
                <tbody>
                  {livePreview.gRows.map(({ div, gVals }) => (
                    <tr key={div} className="preview-div-row">
                      <td className="preview-div-cell">{div}</td>
                      {QTRS.map(({ label: q }) => (
                        <td key={q} className={`preview-val growth-val ${gVals[q] >= 0 ? 'pos' : 'neg'}`}>
                          {livePreview.fmtG(gVals[q])}
                        </td>
                      ))}
                      <td className={`preview-val grand-ttl-val growth-val ${gVals['Grand TTL'] >= 0 ? 'pos' : 'neg'}`}>
                        {livePreview.fmtG(gVals['Grand TTL'])}
                      </td>
                    </tr>
                  ))}
                  <tr className="preview-grand-total">
                    <td>Grand TTL</td>
                    {QTRS.map(({ label: q }) => <td key={q}>{livePreview.fmtG(livePreview.gGrand[q])}</td>)}
                    <td>{livePreview.fmtG(livePreview.gGrand['Grand TTL'])}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      <div style={{display:'flex', alignItems:'center', justifyContent:'flex-end', gap:16, flexWrap:'wrap'}}>
        <div style={{display:'flex', alignItems:'center', gap:12}}>
          <details className="aop-menu aop-menu--panel aop-menu--right">
            <summary>Run options{includeDebug ? ' · 1 on' : ''} ▾</summary>
            <div className="aop-menu-pop">
              <label className="debug-toggle">
                <input type="checkbox" checked={includeDebug} onChange={e => setIncludeDebug(e.target.checked)} />
                <span>Include flat detail sheet in Excel</span>
              </label>
            </div>
          </details>
          <button className="btn-primary" onClick={handleRun} disabled={running} style={{minWidth:180}}>
            {running ? <span className="run-spinner">Running…</span> : 'Run forecast'}
          </button>
        </div>
      </div>

      {running && (
        <div className="running-overlay">
          <div className="running-card card">
            <div className="spinner" />
            <div>
              <div style={{fontWeight:600,color:'var(--navy)'}}>Running forecast engine…</div>
              <div style={{fontSize:13,color:'var(--muted)',marginTop:4}}>Processing {n_stores} stores across 5 divisions</div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
