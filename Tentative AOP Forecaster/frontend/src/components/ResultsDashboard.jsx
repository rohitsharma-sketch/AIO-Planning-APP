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
  const [showLabels, setShowLabels] = useState(true)

  // Row-level detail (store × division) — shared by the chart filters and the drill table
  useEffect(() => {
    const sid = session?.session_id
    if (!sid) return
    setLeaves(null); setDataErr(null); setTypeFilter([])
    fetch(apiUrl(`/api/data/${sid}`))
      .then(r => r.ok ? r.json() : r.json().then(e => { throw new Error(e.detail || 'Failed to load detail data') }))
      .then(rows => setLeaves(rows.map(toLeaf)))
      .catch(e => setDataErr(e.message))
  }, [session?.session_id, runKey])

  const typeOn = t => typeFilter.length === 0 || typeFilter.includes(t)
  const toggleType = t => setTypeFilter(f => {
    const cur = f.length ? f : TYPES
    const next = cur.includes(t) ? cur.filter(x => x !== t) : [...cur, t]
    return next.length === TYPES.length ? [] : next.length ? next : [t]
  })

  // Chart + KPI datasets — recomputed from filtered rows when detail is loaded;
  // fall back to the API's own unfiltered aggregates until then (same fallback
  // the charts already used - the KPI row now shares it too, so "Base (Actuals)"/
  // "Forecasted AOP"/"Overall growth"/"Total stores" reflect the Store Type
  // filter exactly like the charts below already did, instead of always
  // showing the grand total regardless of which chips are toggled off.
  const charts = useMemo(() => {
    if (!leaves) return { monthly: results.monthly, divisions: results.divisions, store_types: results.store_types, summary }
    const sel = leaves.filter(r => typeOn(r.Type))
    const monthly = MONTHS.map((month, i) => ({
      month,
      base:     +sel.reduce((s, r) => s + r.mb[i], 0).toFixed(2),
      forecast: +sel.reduce((s, r) => s + r.m[i], 0).toFixed(2),
    }))
    const divisions = DIVS.map(division => {
      const rs = sel.filter(r => r.Division === division)
      const base = rs.reduce((s, r) => s + r.base, 0), forecast = rs.reduce((s, r) => s + r.fcst, 0)
      return { division, base: +base.toFixed(2), forecast: +forecast.toFixed(2), growth_pct: base > 0 ? +((forecast / base - 1) * 100).toFixed(1) : 0 }
    })
    const store_types = TYPES.filter(typeOn).map(type => {
      const rs = leaves.filter(r => r.Type === type)
      return { type, base: +rs.reduce((s, r) => s + r.base, 0).toFixed(2), forecast: +rs.reduce((s, r) => s + r.fcst, 0).toFixed(2), count: new Set(rs.map(r => r.Store)).size }
    })
    // toLeaf's default scale (0.01) already puts .base/.fcst in ₹ Cr, matching
    // summary.base_cr/forecast_cr's own unit - no rescale needed here.
    const base_cr = sel.reduce((s, r) => s + r.base, 0)
    const forecast_cr = sel.reduce((s, r) => s + r.fcst, 0)
    const filteredSummary = {
      base_cr, forecast_cr,
      growth_pct: base_cr > 0 ? (forecast_cr / base_cr - 1) * 100 : 0,
      n_stores: new Set(sel.map(r => r.Store)).size,
      n_lfl:  new Set(leaves.filter(r => r.Type === 'LfL'  && typeOn(r.Type)).map(r => r.Store)).size,
      n_ramp: new Set(leaves.filter(r => r.Type === 'Ramp' && typeOn(r.Type)).map(r => r.Store)).size,
      n_nso:  new Set(leaves.filter(r => r.Type === 'NSO'  && typeOn(r.Type)).map(r => r.Store)).size,
    }
    return { monthly, divisions, store_types, summary: filteredSummary }
  }, [leaves, typeFilter, results, summary])

  const { monthly, divisions, store_types, summary: kpiSummary } = charts
  const filterLabel = typeFilter.length ? typeFilter.join(' + ') : 'All store types'
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
          { label: 'Base (Actuals)',  value: `₹${fmt(kpiSummary.base_cr)} Cr`,     sub: 'Mar\'26 – Mar\'27' },
          { label: 'Forecasted AOP', value: `₹${fmt(kpiSummary.forecast_cr)} Cr`, sub: 'Mar\'27 – Mar\'28', primary: true },
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
          {dataErr ? `Detail unavailable — ${dataErr}` : !leaves ? 'Loading store detail…' : `Charts: ${filterLabel}`}
        </span>
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
          <h3 className="section-title">Division breakdown  (₹ Cr) — {filterLabel}</h3>
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
          <h3 className="section-title">Store type forecast share — {filterLabel}</h3>
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
