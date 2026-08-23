import { useState, useEffect, useCallback } from 'react'
import axios from 'axios'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, PieChart, Pie, Cell, Legend,
} from 'recharts'
import Header from '../components/Header'
import { theme } from '../theme'

const DIVS = ['GM', 'KIDS', 'LADIES', 'MENS', 'RETAIL']

const DIV_COLORS = {
  GM: '#1E54C0',
  KIDS: '#C85A12',
  LADIES: '#7420B8',
  MENS: '#077A4A',
  RETAIL: '#B22620',
}

const fmt = (v) => v != null ? v.toLocaleString('en-IN', { maximumFractionDigits: 1 }) : '—'

function heatBg(val) {
  if (val === null || val === 0) return 'transparent'
  if (val < 0)
    return `rgba(178,38,32,${Math.min(Math.abs(val) / 15, 1) * 0.18 + 0.06})`
  return `rgba(7,122,74,${Math.min(val / 20, 1) * 0.20 + 0.05})`
}

const pillBtn = (active) => ({
  padding: '7px 18px',
  borderRadius: 20,
  border: active ? 'none' : `1px solid ${theme.border}`,
  background: active ? theme.primary : theme.surface,
  color: active ? '#fff' : theme.textSecondary,
  fontSize: 13,
  fontWeight: active ? 600 : 400,
  cursor: 'pointer',
  transition: 'all 0.15s',
  letterSpacing: 0.2,
})

const TABS = [
  { id: 'matrix', label: 'Growth Matrix' },
  { id: 'forecast', label: 'Forecast vs Base' },
  { id: 'trend', label: 'Monthly Trend' },
  { id: 'mix', label: 'Division Mix' },
]

// ── Tab 1: Growth Matrix ──────────────────────────────────────────────────────

function GrowthMatrixTab({ data, matrix, setMatrix, setData }) {
  const { months } = data

  const overall = matrix['OVERALL'] || Array(12).fill(6.0)

  const getEffective = (div, i) =>
    matrix[div]?.[i] != null ? matrix[div][i] : overall[i]

  const avgEffective = months.map((_, i) => {
    const vals = DIVS.map(d => getEffective(d, i))
    return vals.reduce((a, b) => a + b, 0) / vals.length
  })

  const handleChange = (rowKey, i, raw) => {
    const val = raw === '' ? null : parseFloat(raw)
    setMatrix(prev => {
      const newRow = [...(prev[rowKey] || Array(12).fill(null))]
      newRow[i] = val
      return { ...prev, [rowKey]: newRow }
    })
  }

  const recalculate = useCallback(async (mat) => {
    try {
      const res = await axios.post('/api/division-plan/growth-structure', { growth_matrix: mat })
      setData(res.data)
    } catch {
      // silently ignore
    }
  }, [setData])

  // Auto-recalc on matrix change with debounce
  useEffect(() => {
    const t = setTimeout(() => recalculate(matrix), 600)
    return () => clearTimeout(t)
  }, [matrix, recalculate])

  const cellInputStyle = (val) => ({
    border: 'none',
    outline: 'none',
    background: 'transparent',
    width: '100%',
    fontSize: 12,
    textAlign: 'center',
    color: theme.textPrimary,
    fontWeight: 600,
  })

  const thStyle = {
    padding: '9px 6px',
    textAlign: 'center',
    fontWeight: 600,
    color: theme.textSecondary,
    fontSize: 11,
    letterSpacing: 0.4,
    borderBottom: `1px solid ${theme.border}`,
    background: theme.surfaceAlt,
    whiteSpace: 'nowrap',
  }

  const tdStyle = (bg) => ({
    padding: '4px 6px',
    borderBottom: `1px solid ${theme.border}`,
    borderRight: `1px solid ${theme.border}`,
    background: bg,
    minWidth: 62,
    textAlign: 'center',
  })

  return (
    <div style={{
      background: theme.surface,
      border: `1px solid ${theme.border}`,
      borderRadius: 10,
      overflow: 'hidden',
      boxShadow: '0 1px 4px rgba(27,79,138,0.05)',
    }}>
      <div style={{
        padding: '14px 20px',
        borderBottom: `1px solid ${theme.border}`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 14, fontWeight: 600, color: theme.textPrimary }}>
            Monthly Growth Matrix (%)
          </span>
          <span style={{
            background: theme.accentLight,
            color: theme.accent,
            fontSize: 12,
            padding: '3px 10px',
            borderRadius: 5,
            fontWeight: 500,
          }}>
            ✓ Growth rates sourced from AOP Forecaster — inputs.xlsx
          </span>
        </div>
        <button
          onClick={() => recalculate(matrix)}
          style={{
            padding: '7px 16px',
            borderRadius: 7,
            border: `1px solid ${theme.primary}`,
            background: theme.surface,
            color: theme.primary,
            fontSize: 12,
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          ⟳ Recalculate
        </button>
      </div>

      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr>
              <th style={{ ...thStyle, textAlign: 'left', paddingLeft: 16, minWidth: 90 }}>Division</th>
              {months.map(m => (
                <th key={m} style={thStyle}>{m}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {/* OVERALL row */}
            <tr>
              <td style={{
                padding: '6px 16px',
                fontWeight: 700,
                color: theme.primary,
                fontSize: 12,
                borderBottom: `1px solid ${theme.border}`,
                borderRight: `1px solid ${theme.border}`,
                background: '#EEF3FB',
              }}>OVERALL</td>
              {overall.map((v, i) => (
                <td key={i} style={tdStyle(heatBg(v))}>
                  <input
                    type="number"
                    step="0.1"
                    value={v ?? ''}
                    onChange={e => handleChange('OVERALL', i, e.target.value)}
                    style={cellInputStyle(v)}
                  />
                </td>
              ))}
            </tr>
            {/* Division rows */}
            {DIVS.map(div => {
              const row = matrix[div] || Array(12).fill(null)
              return (
                <tr key={div}>
                  <td style={{
                    padding: '6px 16px',
                    fontWeight: 700,
                    color: DIV_COLORS[div],
                    fontSize: 12,
                    borderBottom: `1px solid ${theme.border}`,
                    borderRight: `1px solid ${theme.border}`,
                  }}>{div}</td>
                  {row.map((v, i) => {
                    const isInherited = v === null
                    const displayVal = isInherited ? overall[i] : v
                    return (
                      <td key={i} style={tdStyle(heatBg(displayVal))}>
                        <input
                          type="number"
                          step="0.1"
                          value={v ?? ''}
                          placeholder={isInherited ? (overall[i]?.toFixed(1) ?? '') : ''}
                          onChange={e => handleChange(div, i, e.target.value)}
                          style={{
                            ...cellInputStyle(displayVal),
                            fontStyle: isInherited ? 'italic' : 'normal',
                            color: isInherited ? theme.textMuted : theme.textPrimary,
                            fontWeight: isInherited ? 400 : 600,
                          }}
                        />
                      </td>
                    )
                  })}
                </tr>
              )
            })}
            {/* Avg Effective row */}
            <tr style={{ background: theme.surfaceAlt }}>
              <td style={{
                padding: '6px 16px',
                fontWeight: 600,
                color: theme.textSecondary,
                fontSize: 11,
                borderTop: `2px solid ${theme.border}`,
                borderRight: `1px solid ${theme.border}`,
                letterSpacing: 0.3,
              }}>Avg Effective %</td>
              {avgEffective.map((v, i) => (
                <td key={i} style={{
                  padding: '5px 6px',
                  textAlign: 'center',
                  fontSize: 11,
                  color: theme.textSecondary,
                  fontWeight: 600,
                  borderTop: `2px solid ${theme.border}`,
                }}>
                  {v.toFixed(1)}%
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Tab 2: Forecast vs Base ───────────────────────────────────────────────────

function ForecastVsBaseTab({ data }) {
  const maxVal = Math.max(...data.divisions.map(d => d.annual_forecast))

  return (
    <div style={{
      background: theme.surface,
      border: `1px solid ${theme.border}`,
      borderRadius: 10,
      padding: '20px 24px',
      boxShadow: '0 1px 4px rgba(27,79,138,0.05)',
    }}>
      <div style={{ fontSize: 14, fontWeight: 600, color: theme.textPrimary, marginBottom: 20 }}>
        FY28 Forecast vs FY27 Base
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
        {data.divisions.map(div => {
          const color = DIV_COLORS[div.division_name]
          const baseW = (div.annual_base / maxVal) * 100
          const fcastW = (div.annual_forecast / maxVal) * 100
          const growth = div.growth_pct
          return (
            <div key={div.division_name} style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
              <div style={{ width: 70, fontWeight: 700, color, fontSize: 13, flexShrink: 0 }}>
                {div.division_name}
              </div>
              <div style={{ flex: 1 }}>
                {/* Base bar */}
                <div style={{
                  height: 14,
                  borderRadius: 4,
                  width: `${baseW}%`,
                  background: color,
                  opacity: 0.38,
                  marginBottom: 5,
                  transition: 'width 0.4s',
                }} />
                {/* Forecast bar */}
                <div style={{
                  height: 18,
                  borderRadius: 4,
                  width: `${fcastW}%`,
                  background: color,
                  transition: 'width 0.4s',
                }} />
              </div>
              <div style={{ width: 220, fontSize: 12, color: theme.textSecondary, flexShrink: 0, paddingLeft: 10 }}>
                ₹{fmt(div.annual_base)}L →{' '}
                <strong style={{ color: theme.textPrimary }}>₹{fmt(div.annual_forecast)}L</strong>
                <span style={{
                  marginLeft: 8,
                  background: growth >= 0 ? theme.accentLight : '#FEE2E0',
                  color: growth >= 0 ? theme.accent : theme.danger,
                  borderRadius: 5,
                  padding: '2px 7px',
                  fontWeight: 700,
                  fontSize: 11,
                }}>
                  {growth >= 0 ? '+' : ''}{growth.toFixed(1)}%
                </span>
              </div>
            </div>
          )
        })}
      </div>
      <div style={{ marginTop: 16, fontSize: 11, color: theme.textMuted }}>
        Light bar = FY27 Base &nbsp;|&nbsp; Solid bar = FY28 Forecast
      </div>
    </div>
  )
}

// ── Tab 3: Monthly Trend ──────────────────────────────────────────────────────

function MonthlyTrendTab({ data }) {
  const chartData = data.months.map((m, i) => {
    const entry = { month: m.replace("'", '’') }
    DIVS.forEach(d => {
      const found = data.divisions.find(x => x.division_name === d)
      entry[d] = found ? found.monthly_forecast[i] : 0
    })
    return entry
  })

  return (
    <div style={{
      background: theme.surface,
      border: `1px solid ${theme.border}`,
      borderRadius: 10,
      padding: '20px 24px',
      boxShadow: '0 1px 4px rgba(27,79,138,0.05)',
    }}>
      <div style={{ fontSize: 14, fontWeight: 600, color: theme.textPrimary, marginBottom: 16 }}>
        Monthly Forecast Trend (₹ Lakhs)
      </div>
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={chartData} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.border} />
          <XAxis dataKey="month" tick={{ fontSize: 11, fill: theme.textSecondary }} />
          <YAxis
            tick={{ fontSize: 11, fill: theme.textSecondary }}
            tickFormatter={v => v.toLocaleString('en-IN')}
          />
          <Tooltip
            formatter={(v, name) => [`₹ ${v.toLocaleString('en-IN', { maximumFractionDigits: 1 })} L`, name]}
            contentStyle={{ fontSize: 12, borderRadius: 6, border: `1px solid ${theme.border}` }}
          />
          {DIVS.map(d => (
            <Line
              key={d}
              type="monotone"
              dataKey={d}
              stroke={DIV_COLORS[d]}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4 }}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>

      {/* Legend */}
      <div style={{ display: 'flex', gap: 20, marginTop: 16, flexWrap: 'wrap' }}>
        {DIVS.map(d => {
          const div = data.divisions.find(x => x.division_name === d)
          return (
            <div key={d} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{ width: 22, height: 3, background: DIV_COLORS[d], borderRadius: 2 }} />
              <span style={{ fontSize: 12, color: theme.textSecondary }}>{d}</span>
              <span style={{ fontSize: 12, fontWeight: 700, color: theme.textPrimary }}>
                ₹{div ? fmt(div.annual_forecast) : '—'}L
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Tab 4: Division Mix ───────────────────────────────────────────────────────

const RADIAN = Math.PI / 180
function CustomLabel({ cx, cy, midAngle, innerRadius, outerRadius, percent }) {
  const radius = innerRadius + (outerRadius - innerRadius) * 0.5
  const x = cx + radius * Math.cos(-midAngle * RADIAN)
  const y = cy + radius * Math.sin(-midAngle * RADIAN)
  if (percent < 0.05) return null
  return (
    <text x={x} y={y} fill="white" textAnchor="middle" dominantBaseline="central" fontSize={11} fontWeight={700}>
      {(percent * 100).toFixed(1)}%
    </text>
  )
}

function DivisionMixTab({ data }) {
  const sorted = [...data.divisions].sort((a, b) => b.annual_forecast - a.annual_forecast)
  const total = data.total_forecast
  const maxFcast = sorted[0]?.annual_forecast || 1

  const pieData = sorted.map(d => ({
    name: d.division_name,
    value: d.annual_forecast,
  }))

  return (
    <div style={{ display: 'flex', gap: 20 }}>
      {/* Pie chart */}
      <div style={{
        background: theme.surface,
        border: `1px solid ${theme.border}`,
        borderRadius: 10,
        padding: '20px 16px',
        boxShadow: '0 1px 4px rgba(27,79,138,0.05)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        width: 280,
        flexShrink: 0,
      }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: theme.textPrimary, marginBottom: 8 }}>
          FY28 Revenue Share
        </div>
        <div style={{ position: 'relative', width: 240, height: 240 }}>
          <PieChart width={240} height={240}>
            <Pie
              data={pieData}
              cx={115}
              cy={115}
              outerRadius={100}
              innerRadius={65}
              dataKey="value"
              labelLine={false}
              label={<CustomLabel />}
            >
              {pieData.map((entry) => (
                <Cell key={entry.name} fill={DIV_COLORS[entry.name]} />
              ))}
            </Pie>
          </PieChart>
          {/* Center label */}
          <div style={{
            position: 'absolute',
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%)',
            textAlign: 'center',
          }}>
            <div style={{ fontSize: 11, color: theme.textMuted, lineHeight: 1.2 }}>Total</div>
            <div style={{ fontSize: 14, fontWeight: 700, color: theme.textPrimary, lineHeight: 1.3 }}>
              ₹{fmt(total)}L
            </div>
          </div>
        </div>
        {/* Legend */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 8, width: '100%' }}>
          {sorted.map(d => (
            <div key={d.division_name} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div style={{ width: 10, height: 10, borderRadius: 2, background: DIV_COLORS[d.division_name], flexShrink: 0 }} />
              <span style={{ fontSize: 12, color: theme.textSecondary, flex: 1 }}>{d.division_name}</span>
              <span style={{ fontSize: 12, fontWeight: 600, color: theme.textPrimary }}>
                {((d.annual_forecast / total) * 100).toFixed(1)}%
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Table */}
      <div style={{
        flex: 1,
        background: theme.surface,
        border: `1px solid ${theme.border}`,
        borderRadius: 10,
        overflow: 'hidden',
        boxShadow: '0 1px 4px rgba(27,79,138,0.05)',
      }}>
        <div style={{ padding: '14px 20px', borderBottom: `1px solid ${theme.border}` }}>
          <span style={{ fontSize: 14, fontWeight: 600, color: theme.textPrimary }}>Division Breakdown</span>
        </div>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ background: theme.surfaceAlt }}>
              {['Division', 'FY27 Base', 'FY28 Plan', 'Growth %', 'Share'].map(h => (
                <th key={h} style={{
                  padding: '10px 16px',
                  textAlign: h === 'Division' ? 'left' : 'right',
                  fontWeight: 600,
                  color: theme.textSecondary,
                  fontSize: 11,
                  letterSpacing: 0.4,
                  borderBottom: `1px solid ${theme.border}`,
                }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((div, idx) => {
              const share = (div.annual_forecast / total) * 100
              return (
                <tr key={div.division_name} style={{ background: idx % 2 === 0 ? theme.surface : theme.surfaceAlt }}>
                  <td style={{ padding: '10px 16px', fontWeight: 700, color: DIV_COLORS[div.division_name] }}>
                    {div.division_name}
                  </td>
                  <td style={{ padding: '10px 16px', textAlign: 'right', color: theme.textSecondary }}>
                    ₹{fmt(div.annual_base)}L
                  </td>
                  <td style={{ padding: '10px 16px', textAlign: 'right', fontWeight: 700, color: theme.primary }}>
                    ₹{fmt(div.annual_forecast)}L
                  </td>
                  <td style={{ padding: '10px 16px', textAlign: 'right' }}>
                    <span style={{
                      background: div.growth_pct >= 0 ? theme.accentLight : '#FEE2E0',
                      color: div.growth_pct >= 0 ? theme.accent : theme.danger,
                      borderRadius: 5,
                      padding: '2px 8px',
                      fontWeight: 700,
                      fontSize: 12,
                    }}>
                      {div.growth_pct >= 0 ? '+' : ''}{div.growth_pct.toFixed(1)}%
                    </span>
                  </td>
                  <td style={{ padding: '10px 16px', textAlign: 'right' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'flex-end' }}>
                      <div style={{ width: 60, height: 8, background: theme.surfaceAlt, borderRadius: 4, overflow: 'hidden' }}>
                        <div style={{
                          height: '100%',
                          width: `${(div.annual_forecast / maxFcast) * 100}%`,
                          background: DIV_COLORS[div.division_name],
                          borderRadius: 4,
                        }} />
                      </div>
                      <span style={{ fontSize: 12, fontWeight: 600, color: theme.textPrimary, minWidth: 38, textAlign: 'right' }}>
                        {share.toFixed(1)}%
                      </span>
                    </div>
                  </td>
                </tr>
              )
            })}
            {/* Total row */}
            <tr style={{ background: '#EEF3FB', borderTop: `2px solid ${theme.border}` }}>
              <td style={{ padding: '10px 16px', fontWeight: 700, color: theme.primary }}>TOTAL</td>
              <td style={{ padding: '10px 16px', textAlign: 'right', fontWeight: 700, color: theme.textSecondary }}>
                ₹{fmt(data.total_base)}L
              </td>
              <td style={{ padding: '10px 16px', textAlign: 'right', fontWeight: 700, color: theme.primary }}>
                ₹{fmt(data.total_forecast)}L
              </td>
              <td style={{ padding: '10px 16px', textAlign: 'right' }}>
                <span style={{
                  background: data.overall_growth_pct >= 0 ? theme.accentLight : '#FEE2E0',
                  color: data.overall_growth_pct >= 0 ? theme.accent : theme.danger,
                  borderRadius: 5, padding: '2px 8px', fontWeight: 700, fontSize: 12,
                }}>
                  {data.overall_growth_pct >= 0 ? '+' : ''}{data.overall_growth_pct.toFixed(1)}%
                </span>
              </td>
              <td style={{ padding: '10px 16px', textAlign: 'right', fontWeight: 700, color: theme.textSecondary }}>
                100.0%
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function DivisionGrowthStructure() {
  const [data, setData] = useState(null)
  const [matrix, setMatrix] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [activeTab, setActiveTab] = useState('matrix')

  useEffect(() => {
    axios.get('/api/division-plan/growth-structure')
      .then(res => {
        setData(res.data)
        setMatrix(res.data.growth_matrix)
      })
      .catch(() => setError('Failed to load growth structure from backend.'))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Header title="Division Growth Structure" />
      <div style={{ flex: 1, overflowY: 'auto', padding: '24px 32px', background: theme.surfaceAlt }}>

        {loading && (
          <div style={{ textAlign: 'center', padding: 60, color: theme.textMuted, fontSize: 14 }}>
            Loading growth structure…
          </div>
        )}

        {error && (
          <div style={{
            background: '#FEF2F2', border: `1px solid ${theme.danger}`, borderRadius: 8,
            padding: '12px 16px', color: theme.danger, fontSize: 13, marginBottom: 20,
          }}>
            {error}
          </div>
        )}

        {data && matrix && (
          <>
            {/* Summary strip */}
            <div style={{
              background: theme.surface,
              border: `1px solid ${theme.border}`,
              borderRadius: 10,
              padding: '16px 22px',
              marginBottom: 18,
              boxShadow: '0 1px 4px rgba(27,79,138,0.05)',
              display: 'flex',
              alignItems: 'center',
              gap: 24,
              flexWrap: 'wrap',
            }}>
              <div>
                <div style={{ fontSize: 11, color: theme.textMuted, fontWeight: 600, letterSpacing: 0.5, marginBottom: 3 }}>TOTAL FY28 PLAN</div>
                <div style={{ fontSize: 22, fontWeight: 700, color: theme.primary }}>
                  ₹ {fmt(data.total_forecast)} L
                </div>
              </div>
              <div style={{ width: 1, height: 36, background: theme.border }} />
              <div>
                <div style={{ fontSize: 11, color: theme.textMuted, fontWeight: 600, letterSpacing: 0.5, marginBottom: 3 }}>OVERALL GROWTH</div>
                <div style={{ fontSize: 20, fontWeight: 700, color: data.overall_growth_pct >= 0 ? theme.accent : theme.danger }}>
                  {data.overall_growth_pct >= 0 ? '+' : ''}{data.overall_growth_pct.toFixed(1)}%
                </div>
              </div>
              <div style={{ width: 1, height: 36, background: theme.border }} />
              {data.divisions.map(div => (
                <div key={div.division_name} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontWeight: 700, color: DIV_COLORS[div.division_name], fontSize: 13 }}>
                    {div.division_name}
                  </span>
                  <span style={{ fontSize: 13, color: theme.textPrimary }}>
                    ₹{fmt(div.annual_forecast)}L
                  </span>
                  <span style={{
                    background: div.growth_pct >= 0 ? theme.accentLight : '#FEE2E0',
                    color: div.growth_pct >= 0 ? theme.accent : theme.danger,
                    borderRadius: 5,
                    padding: '2px 7px',
                    fontWeight: 700,
                    fontSize: 11,
                  }}>
                    {div.growth_pct >= 0 ? '+' : ''}{div.growth_pct.toFixed(1)}%
                  </span>
                </div>
              ))}
            </div>

            {/* Tab bar */}
            <div style={{ display: 'flex', gap: 8, marginBottom: 18 }}>
              {TABS.map(t => (
                <button key={t.id} onClick={() => setActiveTab(t.id)} style={pillBtn(activeTab === t.id)}>
                  {t.label}
                </button>
              ))}
            </div>

            {/* Tab content */}
            {activeTab === 'matrix' && (
              <GrowthMatrixTab data={data} matrix={matrix} setMatrix={setMatrix} setData={setData} />
            )}
            {activeTab === 'forecast' && <ForecastVsBaseTab data={data} />}
            {activeTab === 'trend' && <MonthlyTrendTab data={data} />}
            {activeTab === 'mix' && <DivisionMixTab data={data} />}
          </>
        )}
      </div>
    </div>
  )
}
