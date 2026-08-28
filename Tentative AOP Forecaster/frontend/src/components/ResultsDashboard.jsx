import { useState, useEffect, useMemo } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  PieChart, Pie, Cell, ComposedChart, LabelList
} from 'recharts'
import OutputTab from './OutputTab'
import StoreDrillTable from './StoreDrillTable'
import { toLeaf, MONTHS, TYPES } from '../lib/tags'
import { apiUrl } from '../lib/apiBase'
import './ResultsDashboard.css'

// FY28_M = [Mar'27 (stub anchor), Apr'27..Jun'27 (Q1), Jul'27..Sep'27 (Q2),
// Oct'27..Dec'27 (Q3), Jan'28..Mar'28 (Q4)] — quarter shortcuts skip the stub.
const QUARTERS = [
  { label: 'Q1', months: MONTHS.slice(1, 4) },
  { label: 'Q2', months: MONTHS.slice(4, 7) },
  { label: 'Q3', months: MONTHS.slice(7, 10) },
  { label: 'Q4', months: MONTHS.slice(10, 13) },
]

const NAVY   = '#1F3864'
const NAVY2  = '#2F5597'
const LIGHT  = '#A8C0E8'
const ORANGE = '#C96A00'
const TEAL   = '#0F6E56'
const DIVS   = ['GM', 'KIDS', 'LADIES', 'MENS', 'RETAIL']
const TYPE_COLORS = { LfL: NAVY, Ramp: ORANGE, NSO: TEAL }

function fmt(v)    { return v?.toLocaleString('en-IN', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) }
function fmtPct(v) { return (v > 0 ? '+' : '') + v?.toFixed(1) + '%' }
const lbl0 = v => v ? Math.round(v).toLocaleString('en-IN') : ''

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div className="chart-tooltip">
      <div className="tt-label">{label}</div>
      {payload.map(p => (
        <div key={p.name} className="tt-row">
          <span className="tt-dot" style={{ background: p.color }} />
          <span>{p.name}:</span>
          <span className="num"> ₹{fmt(p.value)} Cr</span>
        </div>
      ))}
    </div>
  )
}

export default function ResultsDashboard({ results, session, runKey, onDownload, onRunAgain }) {
  const { summary } = results
  const [activeTab, setActiveTab] = useState('summary')
  const [leaves, setLeaves]       = useState(null)
  const [dataErr, setDataErr]     = useState(null)
  const [typeFilter, setTypeFilter] = useState([])      // [] = all types
  const [monthFilter, setMonthFilter] = useState([])    // [] = all months
  const [showLabels, setShowLabels] = useState(true)

  // Base source for the charts below: 'actual' is the DB's own actuals (what
  // the engine itself forecast against); 'reindexed' swaps in Calendar
  // Engine's saved month-wise reindex output for the LfL portion, so a
  // planner can compare the SAME forecast's growth% against either base.
  // Reindexed data is aggregate-only (div x month, LfL stores only - see
  // db/reindexed_base_sales.py) - Ramp/NSO base is unaffected either way.
  const [baseSource, setBaseSource] = useState('actual')   // 'actual' | 'reindexed'
  const [reindexed, setReindexed] = useState(null)
  const [reindexedLoading, setReindexedLoading] = useState(false)
  const [reindexedError, setReindexedError] = useState(null)

  useEffect(() => {
    if (baseSource !== 'reindexed' || reindexed || reindexedLoading) return
    setReindexedLoading(true)
    fetch(apiUrl('/api/config/base-sales-reindexed'))
      .then(r => r.ok ? r.json() : Promise.reject(new Error('Failed to load')))
      .then(data => setReindexed(data))
      .catch(e => setReindexedError(e.message))
      .finally(() => setReindexedLoading(false))
  }, [baseSource, reindexed, reindexedLoading])

  // Row-level detail (store × division) — shared by the chart filters and the drill table
  useEffect(() => {
    const sid = session?.session_id
    if (!sid) return
    setLeaves(null); setDataErr(null); setTypeFilter([]); setMonthFilter([])
    fetch(apiUrl(`/api/data/${sid}`))
      .then(r => r.ok ? r.json() : r.json().then(e => { throw new Error(e.detail || 'Failed to load detail data') }))
      // NOT rows.map(toLeaf) - Array.map calls its callback as (element, index,
      // array), and toLeaf's 2nd param is `scale` (default 0.01) - passing
      // toLeaf directly silently fed each row's ARRAY INDEX in as scale
      // instead of 0.01, so every row past the first was multiplied by its
      // own position (row 500 scaled by 500x instead of 0.01x). Summed across
      // ~1,500 store x division rows, that's exactly the kind of
      // astronomically wrong total that showed up in the KPI cards.
      .then(rows => setLeaves(rows.map(r => toLeaf(r))))
      .catch(e => setDataErr(e.message))
  }, [session?.session_id, runKey])

  const typeOn = t => typeFilter.length === 0 || typeFilter.includes(t)
  const toggleType = t => setTypeFilter(f => {
    const cur = f.length ? f : TYPES
    const next = cur.includes(t) ? cur.filter(x => x !== t) : [...cur, t]
    return next.length === TYPES.length ? [] : next.length ? next : [t]
  })

  const monthOn = m => monthFilter.length === 0 || monthFilter.includes(m)
  const toggleMonth = m => setMonthFilter(f => {
    const cur = f.length ? f : MONTHS
    const next = cur.includes(m) ? cur.filter(x => x !== m) : [...cur, m]
    return next.length === MONTHS.length ? [] : next.length ? next : [m]
  })
  const setQuarter = months => setMonthFilter(f =>
    f.length === months.length && months.every(m => f.includes(m)) ? [] : months
  )

  // Chart + KPI datasets — recomputed from filtered rows when detail is loaded;
  // fall back to the API's own unfiltered aggregates until then (same fallback
  // the charts already used - the KPI row now shares it too, so "Base (Actuals)"/
  // "Forecasted AOP"/"Overall growth"/"Total stores" reflect the Store Type
  // filter exactly like the charts below already did, instead of always
  // showing the grand total regardless of which chips are toggled off.
  const charts = useMemo(() => {
    if (!leaves) return { monthly: results.monthly, divisions: results.divisions, store_types: results.store_types, summary }
    const sel = leaves.filter(r => typeOn(r.Type))
    const monthIdx = MONTHS.map((m, i) => i).filter(i => monthOn(MONTHS[i]))
    // Sum only the selected months' base/forecast for one row — the Monthly
    // chart shows just the selected months, everything else (KPIs, division
    // breakdown, store-type pie) rolls up totals over that same subset.
    const sumSel = (r, arr) => monthIdx.reduce((s, i) => s + arr[i], 0)

    // Base-source swap: reindexed data only exists aggregated at div x month
    // for LfL stores (see db/reindexed_base_sales.py), so it's substituted at
    // the point of summation, not per store row. Forecast is never touched —
    // this only changes which base the SAME forecast is compared against.
    const reindexedOn = baseSource === 'reindexed' && !!reindexed?.base_sales
    const rBase = (div, i) => (reindexed.base_sales[div]?.[MONTHS[i]] || 0) * 0.01   // Lakhs -> Cr

    const monthly = monthIdx.map(i => {
      const nonLfl = sel.filter(r => r.Type !== 'LfL').reduce((s, r) => s + r.mb[i], 0)
      const lfl = reindexedOn && typeOn('LfL')
        ? DIVS.reduce((s, d) => s + rBase(d, i), 0)
        : sel.filter(r => r.Type === 'LfL').reduce((s, r) => s + r.mb[i], 0)
      return { month: MONTHS[i], base: +(nonLfl + lfl).toFixed(2), forecast: +sel.reduce((s, r) => s + r.m[i], 0).toFixed(2) }
    })
    const divisions = DIVS.map(division => {
      const rs = sel.filter(r => r.Division === division)
      const nonLfl = rs.filter(r => r.Type !== 'LfL').reduce((s, r) => s + sumSel(r, r.mb), 0)
      const lfl = reindexedOn && typeOn('LfL')
        ? monthIdx.reduce((s, i) => s + rBase(division, i), 0)
        : rs.filter(r => r.Type === 'LfL').reduce((s, r) => s + sumSel(r, r.mb), 0)
      const base = nonLfl + lfl, forecast = rs.reduce((s, r) => s + sumSel(r, r.m), 0)
      return { division, base: +base.toFixed(2), forecast: +forecast.toFixed(2), growth_pct: base > 0 ? +((forecast / base - 1) * 100).toFixed(1) : 0 }
    })
    const store_types = TYPES.filter(typeOn).map(type => {
      const rs = leaves.filter(r => r.Type === type)
      const base = reindexedOn && type === 'LfL'
        ? DIVS.reduce((s, d) => s + monthIdx.reduce((ss, i) => ss + rBase(d, i), 0), 0)
        : rs.reduce((s, r) => s + sumSel(r, r.mb), 0)
      return { type, base: +base.toFixed(2), forecast: +rs.reduce((s, r) => s + sumSel(r, r.m), 0).toFixed(2), count: new Set(rs.map(r => r.Store)).size }
    })
    // toLeaf's default scale (0.01) already puts .base/.fcst in ₹ Cr, matching
    // summary.base_cr/forecast_cr's own unit - no rescale needed here.
    // Reuse `monthly`'s per-month base (already swap-aware) rather than
    // re-deriving the sum a second way.
    const base_cr = monthly.reduce((s, m) => s + m.base, 0)
    const forecast_cr = sel.reduce((s, r) => s + sumSel(r, r.m), 0)
    const filteredSummary = {
      base_cr, forecast_cr,
      growth_pct: base_cr > 0 ? (forecast_cr / base_cr - 1) * 100 : 0,
      n_stores: new Set(sel.map(r => r.Store)).size,
      n_lfl:  new Set(leaves.filter(r => r.Type === 'LfL'  && typeOn(r.Type)).map(r => r.Store)).size,
      n_ramp: new Set(leaves.filter(r => r.Type === 'Ramp' && typeOn(r.Type)).map(r => r.Store)).size,
      n_nso:  new Set(leaves.filter(r => r.Type === 'NSO'  && typeOn(r.Type)).map(r => r.Store)).size,
    }
    return { monthly, divisions, store_types, summary: filteredSummary }
  }, [leaves, typeFilter, monthFilter, results, summary, baseSource, reindexed])

  const { monthly, divisions, store_types, summary: kpiSummary } = charts
  const filterLabel = typeFilter.length ? typeFilter.join(' + ') : 'All store types'
  const monthsChrono = MONTHS.filter(m => monthOn(m))   // click order -> fiscal order
  const monthLabel = monthFilter.length === 0 ? 'Mar\'27 – Mar\'28'
    : monthsChrono.length === 1 ? monthsChrono[0]
    : `${monthsChrono[0]} – ${monthsChrono[monthsChrono.length - 1]} (${monthsChrono.length} mo)`
  // Same-index LY month (Base column) is exactly one fiscal year behind its TY counterpart.
  const toLY = m => m.replace(/'(\d\d)$/, (_, yy) => `'${String(+yy - 1).padStart(2, '0')}`)
  const baseLabel = monthFilter.length === 0 ? 'Mar\'26 – Mar\'27'
    : monthsChrono.length === 1 ? toLY(monthsChrono[0])
    : `${toLY(monthsChrono[0])} – ${toLY(monthsChrono[monthsChrono.length - 1])}`
  const typeCount = t => (leaves ? new Set(leaves.filter(r => r.Type === t).map(r => r.Store)).size : { LfL: summary.n_lfl, Ramp: summary.n_ramp, NSO: summary.n_nso }[t])

  return (
    <div className="dash-wrap">

      {/* ── Action bar ── */}
      <div className="dash-header">
        <div>
          <h2 className="dash-title">Forecast results</h2>
          <p className="dash-sub">FY28 Annual Operating Plan — Mar'27 to Mar'28</p>
        </div>
        <div className="dash-actions">
          <button className="btn-secondary" onClick={onRunAgain}>← Back</button>
          <button className="btn-primary"   onClick={onDownload}>⬇ Download Excel</button>
        </div>
      </div>

      {/* ── Tab bar ── */}
      <div className="dash-tabs">
        <button className={`dash-tab ${activeTab === 'summary' ? 'active' : ''}`} onClick={() => setActiveTab('summary')}>Summary</button>
        <button className={`dash-tab ${activeTab === 'output' ? 'active' : ''}`} onClick={() => setActiveTab('output')}>Output</button>
      </div>

      {/* ── Output tab — always mounted so filter state survives Summary↔Output toggling ── */}
      <div style={{ display: activeTab === 'output' ? '' : 'none' }}>
        <OutputTab sessionId={session?.session_id} runKey={runKey} />
      </div>

      {/* ── Summary tab ── */}
      {activeTab === 'summary' && <>

      {/* ── KPI row — reflects the Store Type filter below (kpiSummary), not the
          unfiltered grand total, once row-level detail has loaded (falls back
          to the server's own unfiltered summary until it has - see charts
          useMemo above) ── */}
      <div className="kpi-row">
        {[
          { label: 'Base (Actuals)',  value: `₹${fmt(kpiSummary.base_cr)} Cr`,     sub: baseLabel },
          { label: 'Forecasted AOP', value: `₹${fmt(kpiSummary.forecast_cr)} Cr`, sub: monthLabel, primary: true },
          { label: 'Overall growth', value: fmtPct(kpiSummary.growth_pct),         sub: 'Base vs Forecast', pct: true, positive: kpiSummary.growth_pct >= 0 },
          {
            label: 'Total stores', value: kpiSummary.n_stores,
            sub: TYPES.filter(typeOn).map(t => `${kpiSummary[`n_${t.toLowerCase()}`]} ${t}`).join(' · '),
          },
        ].map(k => (
          <div key={k.label} className={`kpi-card card ${k.primary ? 'kpi-primary' : ''}`}>
            <div className="kpi-label">{k.label}</div>
            <div className={`kpi-value num ${k.positive !== undefined ? (k.positive ? 'positive' : 'negative') : ''}`}>{k.value}</div>
            <div className="kpi-sub">{k.sub}</div>
          </div>
        ))}
      </div>

      {/* ── Chart controls: store-type filter + data labels ── */}
      <div className="chart-filter-bar">
        <span className="sdt-tb-label">Store type</span>
        {TYPES.map(t => (
          <button key={t} className={`sdt-chip${typeOn(t) ? ' on' : ''}`} onClick={() => toggleType(t)} disabled={!leaves && !dataErr}
                  title={`${typeOn(t) ? 'Hide' : 'Show'} ${t} stores`}>
            <span className="chip-dot" style={{ background: typeOn(t) ? '#fff' : TYPE_COLORS[t] }} />{t} · {typeCount(t)}
          </button>
        ))}
        {typeFilter.length > 0 && <button className="sdt-reset" onClick={() => setTypeFilter([])}>All types</button>}
        <label className="sdt-chip sdt-toggle" style={{ marginLeft: 12 }}>
          <input type="checkbox" checked={showLabels} onChange={e => setShowLabels(e.target.checked)} /> Data labels
        </label>
        <span className="chart-filter-note">
          {dataErr ? `Detail unavailable — ${dataErr}` : !leaves ? 'Loading store detail…' : `Charts: ${filterLabel} · ${monthLabel}`}
        </span>
      </div>

      {/* ── Base source toggle: Actual vs Calendar Engine's reindexed sales.
          Reindexed data only covers LfL stores (aggregate, div x month) — see
          db/reindexed_base_sales.py — so Ramp/NSO base is unchanged either way. ── */}
      <div className="actuals-source-toggle" style={{ padding: '0 2px' }}>
        <span className="actuals-source-label">Base source (LfL):</span>
        <div className="actuals-source-btns">
          <button
            className={`actuals-source-btn ${baseSource === 'actual' ? 'active' : ''}`}
            onClick={() => setBaseSource('actual')}
          >Actual Sales</button>
          <button
            className={`actuals-source-btn ${baseSource === 'reindexed' ? 'active' : ''}`}
            onClick={() => setBaseSource('reindexed')}
          >Re-indexed Sales</button>
        </div>
        {baseSource === 'reindexed' && reindexedLoading && (
          <span className="actuals-source-status">Loading Calendar Engine's reindexed sales…</span>
        )}
        {baseSource === 'reindexed' && reindexedError && (
          <span className="actuals-source-status actuals-source-status--err">Couldn't load: {reindexedError}</span>
        )}
        {baseSource === 'reindexed' && reindexed?.note && (
          <span className="actuals-source-status actuals-source-status--warn">{reindexed.note}</span>
        )}
        {baseSource === 'reindexed' && reindexed?.base_sales && (
          <span className="actuals-source-status">Ramp/NSO base unaffected — reindexed data covers LfL stores only.</span>
        )}
      </div>

      {/* ── Month filter: quarter shortcuts + individual month chips ── */}
      <div className="chart-filter-bar">
        <span className="sdt-tb-label">Month</span>
        {QUARTERS.map(q => {
          const on = q.months.every(m => monthOn(m)) && monthFilter.length > 0 && monthFilter.length <= q.months.length
          return (
            <button key={q.label} className={`sdt-chip${on ? ' on' : ''}`} onClick={() => setQuarter(q.months)}
                    disabled={!leaves && !dataErr} title={`${q.months[0]} – ${q.months[q.months.length - 1]}`}>
              {q.label}
            </button>
          )
        })}
        <span className="month-chip-sep" />
        {MONTHS.map(m => (
          <button key={m} className={`sdt-chip month-chip${monthOn(m) ? ' on' : ''}`} onClick={() => toggleMonth(m)}
                  disabled={!leaves && !dataErr} title={`${monthOn(m) ? 'Hide' : 'Show'} ${m}`}>
            {m}
          </button>
        ))}
        {monthFilter.length > 0 && <button className="sdt-reset" onClick={() => setMonthFilter([])}>Full year</button>}
      </div>

      {/* ── Monthly chart ── */}
      <div className="card chart-card">
        <h3 className="section-title">Monthly base vs forecast  (₹ Cr) — {filterLabel}</h3>
        <ResponsiveContainer width="100%" height={showLabels ? 290 : 260}>
          <ComposedChart data={monthly} margin={{ top: showLabels ? 18 : 4, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#E5EDF7" />
            <XAxis dataKey="month" tick={{ fontSize: 11, fill: '#6B7A99' }} />
            <YAxis tick={{ fontSize: 11, fill: '#6B7A99' }} tickFormatter={v => `${v}`} width={48} />
            <Tooltip content={<CustomTooltip />} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="base" name="Base" fill={LIGHT} isAnimationActive={false} radius={[3, 3, 0, 0]}>
              {showLabels && <LabelList dataKey="base" position="top" formatter={lbl0} style={{ fontSize: 10, fill: '#6B7A99' }} />}
            </Bar>
            <Bar dataKey="forecast" name="Forecast" fill={NAVY} isAnimationActive={false} radius={[3, 3, 0, 0]}>
              {showLabels && <LabelList dataKey="forecast" position="top" formatter={lbl0} style={{ fontSize: 10, fill: NAVY, fontWeight: 600 }} />}
            </Bar>
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* ── Division + Store type row ── */}
      <div className="chart-row">
        <div className="card chart-card">
          <h3 className="section-title">Division breakdown  (₹ Cr) — {filterLabel} · {monthLabel}</h3>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={divisions} layout="vertical" margin={{ top: 4, right: showLabels ? 48 : 16, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E5EDF7" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 11, fill: '#6B7A99' }} tickFormatter={v => `${v}`} />
              <YAxis dataKey="division" type="category" width={56} tick={{ fontSize: 11, fill: '#6B7A99' }} />
              <Tooltip content={<CustomTooltip />} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="base" name="Base" fill={LIGHT} isAnimationActive={false} radius={[0, 3, 3, 0]}>
                {showLabels && <LabelList dataKey="base" position="right" formatter={lbl0} style={{ fontSize: 10, fill: '#6B7A99' }} />}
              </Bar>
              <Bar dataKey="forecast" name="Forecast" fill={NAVY2} isAnimationActive={false} radius={[0, 3, 3, 0]}>
                {showLabels && <LabelList dataKey="forecast" position="right" formatter={lbl0} style={{ fontSize: 10, fill: NAVY, fontWeight: 600 }} />}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="card chart-card">
          <h3 className="section-title">Store type forecast share — {filterLabel} · {monthLabel}</h3>
          <ResponsiveContainer width="100%" height={240}>
            <PieChart>
              <Pie data={store_types} dataKey="forecast" nameKey="type"
                cx="50%" cy="50%" outerRadius={80} innerRadius={40} paddingAngle={3}
                label={showLabels ? ({ type, percent, forecast }) => `${type} ${(percent * 100).toFixed(0)}% · ₹${fmt(forecast)}` : false}
                labelLine={showLabels}>
                {store_types.map(s => <Cell key={s.type} fill={TYPE_COLORS[s.type] || NAVY} />)}
              </Pie>
              <Tooltip formatter={(v) => [`₹${fmt(v)} Cr`, 'Forecast']} />
            </PieChart>
          </ResponsiveContainer>
          <div className="pie-legend">
            {store_types.map(s => (
              <div key={s.type} className="pie-leg-item">
                <span className="pie-dot" style={{ background: TYPE_COLORS[s.type] || NAVY }} />
                <span>{s.type}{s.count != null ? ` (${s.count})` : ''}</span>
                <span className="num pie-val">₹{fmt(s.forecast)} Cr</span>
                <span className={`num ${s.forecast > s.base ? 'positive' : 'negative'}`} style={{ fontSize: 11 }}>
                  {fmtPct(s.base > 0 ? (s.forecast / s.base - 1) * 100 : 0)}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── Store drill-down: every level, pivot-style filters, sortable headers ── */}
      <StoreDrillTable leaves={leaves} error={dataErr} runKey={runKey} />

      </>}
    </div>
  )
}
