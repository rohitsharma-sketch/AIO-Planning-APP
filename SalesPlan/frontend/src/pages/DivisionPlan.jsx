import { useState, useEffect } from 'react'
import axios from 'axios'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import Header from '../components/Header'
import { theme } from '../theme'

const inputStyle = {
  border: `1px solid ${theme.border}`,
  borderRadius: 6,
  padding: '6px 10px',
  fontSize: 13,
  color: theme.textPrimary,
  background: theme.surface,
  width: '100%',
  outline: 'none',
  boxSizing: 'border-box',
}

const btnStyle = (color, textColor = '#fff') => ({
  padding: '8px 18px',
  borderRadius: 7,
  border: 'none',
  background: color,
  color: textColor,
  fontSize: 13,
  fontWeight: 600,
  cursor: 'pointer',
  letterSpacing: 0.3,
})

export default function DivisionPlan() {
  const [planName, setPlanName] = useState('FY28 Division Plan')
  const [planYear, setPlanYear] = useState(2027)
  const [rows, setRows] = useState([])
  const [results, setResults] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [configMeta, setConfigMeta] = useState(null)

  useEffect(() => {
    loadConfig()
  }, [])

  const loadConfig = async () => {
    setError(null)
    try {
      const res = await axios.get('/api/division-plan/config')
      setRows(res.data.divisions.map(d => ({ ...d })))
      setConfigMeta({ totalStores: res.data.total_stores, source: res.data.source })
    } catch {
      setError('Failed to load config from backend.')
    }
  }

  const updateRow = (idx, field, value) => {
    setRows(prev => prev.map((r, i) => i === idx ? { ...r, [field]: value } : r))
  }

  const addRow = () => {
    setRows(prev => [...prev, {
      division_name: '',
      base_sales: 0,
      growth_pct: 10,
      seasonality_index: 1.0,
      fy_start_month: 4,
    }])
  }

  const removeRow = (idx) => {
    setRows(prev => prev.filter((_, i) => i !== idx))
  }

  const calculate = async () => {
    setLoading(true)
    setError(null)
    try {
      const payload = {
        divisions: rows.map(r => ({
          ...r,
          base_sales: parseFloat(r.base_sales) || 0,
          growth_pct: parseFloat(r.growth_pct) || 0,
          seasonality_index: parseFloat(r.seasonality_index) || 1,
          fy_start_month: parseInt(r.fy_start_month) || 4,
        })),
        plan_year: planYear,
        plan_name: planName,
      }
      const res = await axios.post('/api/division-plan/calculate', payload)
      setResults(res.data)
    } catch {
      setError('Calculation failed. Check that the backend is running.')
    } finally {
      setLoading(false)
    }
  }

  const exportCSV = async () => {
    try {
      const res = await axios.get('/api/division-plan/export', { responseType: 'blob' })
      const url = URL.createObjectURL(res.data)
      const a = document.createElement('a')
      a.href = url
      a.download = 'division_plan.csv'
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      setError('Export failed.')
    }
  }

  const peakMonth = (breakdown) => {
    return breakdown.reduce((a, b) => a.planned_sales > b.planned_sales ? a : b).month
  }

  const avgGrowth = results
    ? (rows.reduce((s, r) => s + parseFloat(r.growth_pct || 0), 0) / rows.length).toFixed(1)
    : null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Header title="Division Based Plan" />
      <div style={{ flex: 1, overflowY: 'auto', padding: '24px 32px', background: theme.surfaceAlt }}>

        {configMeta && (
          <div style={{
            background: theme.accentLight,
            border: `1px solid ${theme.accent}`,
            borderRadius: 8,
            padding: '10px 16px',
            marginBottom: 18,
            fontSize: 13,
            color: theme.textPrimary,
            display: 'flex',
            alignItems: 'center',
            gap: 10,
          }}>
            <span style={{ fontSize: 16 }}>📂</span>
            <span>
              Loaded from <strong>{configMeta.source}</strong> — <strong>{configMeta.totalStores} stores</strong> × 5 divisions
            </span>
          </div>
        )}

        {error && (
          <div style={{
            background: '#FEF2F2', border: `1px solid ${theme.danger}`, borderRadius: 8,
            padding: '10px 16px', marginBottom: 18, color: theme.danger, fontSize: 13,
          }}>
            {error}
          </div>
        )}

        <div style={{
          background: theme.surface,
          border: `1px solid ${theme.border}`,
          borderRadius: 10,
          padding: '18px 20px',
          marginBottom: 22,
          display: 'flex',
          alignItems: 'center',
          gap: 14,
          flexWrap: 'wrap',
          boxShadow: '0 1px 4px rgba(27,79,138,0.05)',
        }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <label style={{ fontSize: 11, fontWeight: 600, color: theme.textMuted, letterSpacing: 0.5 }}>PLAN NAME</label>
            <input
              style={{ ...inputStyle, width: 220 }}
              value={planName}
              onChange={e => setPlanName(e.target.value)}
            />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <label style={{ fontSize: 11, fontWeight: 600, color: theme.textMuted, letterSpacing: 0.5 }}>PLAN YEAR</label>
            <select
              style={{ ...inputStyle, width: 100 }}
              value={planYear}
              onChange={e => setPlanYear(parseInt(e.target.value))}
            >
              <option value={2025}>2025</option>
              <option value={2026}>2026</option>
              <option value={2027}>2027</option>
            </select>
          </div>
          <div style={{ display: 'flex', gap: 10, marginTop: 16 }}>
            <button style={btnStyle(theme.surfaceAlt, theme.primary)} onClick={loadConfig}>
              ↺ Load Config
            </button>
            <button
              style={btnStyle(theme.primary)}
              onClick={calculate}
              disabled={loading}
            >
              {loading ? 'Calculating…' : '⚡ Calculate Plan'}
            </button>
            <button style={btnStyle(theme.accent)} onClick={exportCSV}>
              ⬇ Export CSV
            </button>
          </div>
        </div>

        <div style={{
          background: theme.surface,
          border: `1px solid ${theme.border}`,
          borderRadius: 10,
          marginBottom: 24,
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
            <span style={{ fontSize: 14, fontWeight: 600, color: theme.textPrimary }}>Division Inputs</span>
            <button style={btnStyle(theme.primaryLight)} onClick={addRow}>+ Add Row</button>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ background: theme.surfaceAlt }}>
                  {['Division Name', 'Base Sales (₹ Lakhs)', 'Growth %', 'Seasonality Index', 'FY Start Month', ''].map(h => (
                    <th key={h} style={{
                      padding: '10px 14px',
                      textAlign: 'left',
                      fontWeight: 600,
                      color: theme.textSecondary,
                      fontSize: 12,
                      letterSpacing: 0.4,
                      borderBottom: `1px solid ${theme.border}`,
                      whiteSpace: 'nowrap',
                    }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, idx) => (
                  <tr
                    key={idx}
                    style={{ background: idx % 2 === 0 ? theme.surface : theme.surfaceAlt }}
                  >
                    <td style={{ padding: '8px 14px' }}>
                      <input
                        style={inputStyle}
                        value={row.division_name}
                        onChange={e => updateRow(idx, 'division_name', e.target.value)}
                        placeholder="Division name"
                      />
                    </td>
                    <td style={{ padding: '8px 14px' }}>
                      <input
                        style={{ ...inputStyle, width: 130 }}
                        type="number"
                        value={row.base_sales}
                        onChange={e => updateRow(idx, 'base_sales', e.target.value)}
                      />
                    </td>
                    <td style={{ padding: '8px 14px' }}>
                      <input
                        style={{ ...inputStyle, width: 90 }}
                        type="number"
                        step="0.1"
                        value={row.growth_pct}
                        onChange={e => updateRow(idx, 'growth_pct', e.target.value)}
                      />
                    </td>
                    <td style={{ padding: '8px 14px' }}>
                      <input
                        style={{ ...inputStyle, width: 110 }}
                        type="number"
                        step="0.01"
                        value={row.seasonality_index}
                        onChange={e => updateRow(idx, 'seasonality_index', e.target.value)}
                      />
                    </td>
                    <td style={{ padding: '8px 14px' }}>
                      <select
                        style={{ ...inputStyle, width: 90 }}
                        value={row.fy_start_month}
                        onChange={e => updateRow(idx, 'fy_start_month', e.target.value)}
                      >
                        {Array.from({ length: 12 }, (_, i) => (
                          <option key={i + 1} value={i + 1}>{i + 1}</option>
                        ))}
                      </select>
                    </td>
                    <td style={{ padding: '8px 14px' }}>
                      <button
                        onClick={() => removeRow(idx)}
                        style={{
                          background: 'none',
                          border: 'none',
                          cursor: 'pointer',
                          fontSize: 16,
                          color: theme.danger,
                          padding: '2px 6px',
                        }}
                        title="Remove row"
                      >🗑</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {results && (
          <div>
            <div style={{ display: 'flex', gap: 16, marginBottom: 24 }}>
              {[
                { label: 'Total Plan Value', value: `₹ ${results.total_planned_sales.toLocaleString('en-IN', { maximumFractionDigits: 1 })} L`, color: theme.primary },
                { label: 'No. of Divisions', value: results.divisions.length, color: theme.primaryLight },
                { label: 'Avg Growth %', value: `${avgGrowth}%`, color: theme.accent },
              ].map(card => (
                <div key={card.label} style={{
                  flex: 1,
                  background: theme.surface,
                  border: `1px solid ${theme.border}`,
                  borderRadius: 10,
                  padding: '18px 22px',
                  boxShadow: '0 1px 4px rgba(27,79,138,0.05)',
                }}>
                  <div style={{ fontSize: 12, color: theme.textMuted, fontWeight: 600, letterSpacing: 0.5, marginBottom: 6 }}>{card.label.toUpperCase()}</div>
                  <div style={{ fontSize: 26, fontWeight: 700, color: card.color }}>{card.value}</div>
                </div>
              ))}
            </div>

            <div style={{ marginBottom: 24 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: theme.textMuted, letterSpacing: 0.7, textTransform: 'uppercase', marginBottom: 14 }}>
                Monthly Distribution by Division
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 18 }}>
                {results.divisions.map(div => (
                  <div key={div.division_name} style={{
                    background: theme.surface,
                    border: `1px solid ${theme.border}`,
                    borderRadius: 10,
                    padding: '16px 18px',
                    boxShadow: '0 1px 4px rgba(27,79,138,0.05)',
                  }}>
                    <div style={{ fontSize: 14, fontWeight: 700, color: theme.textPrimary, marginBottom: 4 }}>{div.division_name}</div>
                    <div style={{ fontSize: 12, color: theme.textSecondary, marginBottom: 14 }}>
                      Annual Target: <strong>₹ {div.annual_target.toLocaleString('en-IN', { maximumFractionDigits: 1 })} L</strong>
                    </div>
                    <ResponsiveContainer width="100%" height={180}>
                      <BarChart data={div.monthly_breakdown} margin={{ top: 0, right: 0, left: -10, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke={theme.border} />
                        <XAxis dataKey="month" tick={{ fontSize: 11, fill: theme.textSecondary }} />
                        <YAxis tick={{ fontSize: 11, fill: theme.textSecondary }} />
                        <Tooltip
                          formatter={(v) => [`₹ ${v.toLocaleString('en-IN', { maximumFractionDigits: 1 })} L`, 'Planned']}
                          contentStyle={{ fontSize: 12, borderRadius: 6, border: `1px solid ${theme.border}` }}
                        />
                        <Bar dataKey="planned_sales" fill={theme.primary} radius={[3, 3, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                ))}
              </div>
            </div>

            <div style={{
              background: theme.surface,
              border: `1px solid ${theme.border}`,
              borderRadius: 10,
              overflow: 'hidden',
              boxShadow: '0 1px 4px rgba(27,79,138,0.05)',
            }}>
              <div style={{ padding: '14px 20px', borderBottom: `1px solid ${theme.border}` }}>
                <span style={{ fontSize: 14, fontWeight: 600, color: theme.textPrimary }}>Summary Table</span>
              </div>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ background: theme.surfaceAlt }}>
                    {['Division', 'Annual Target (₹ L)', 'Peak Month', 'Growth %'].map(h => (
                      <th key={h} style={{
                        padding: '10px 18px',
                        textAlign: 'left',
                        fontWeight: 600,
                        color: theme.textSecondary,
                        fontSize: 12,
                        letterSpacing: 0.4,
                        borderBottom: `1px solid ${theme.border}`,
                      }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {results.divisions.map((div, idx) => {
                    const inputRow = rows.find(r => r.division_name === div.division_name)
                    return (
                      <tr key={div.division_name} style={{ background: idx % 2 === 0 ? theme.surface : theme.surfaceAlt }}>
                        <td style={{ padding: '10px 18px', fontWeight: 600, color: theme.textPrimary }}>{div.division_name}</td>
                        <td style={{ padding: '10px 18px', color: theme.primary, fontWeight: 700 }}>
                          {div.annual_target.toLocaleString('en-IN', { maximumFractionDigits: 1 })}
                        </td>
                        <td style={{ padding: '10px 18px', color: theme.textSecondary }}>{peakMonth(div.monthly_breakdown)}</td>
                        <td style={{ padding: '10px 18px' }}>
                          <span style={{
                            background: theme.accentLight,
                            color: theme.accent,
                            borderRadius: 5,
                            padding: '3px 8px',
                            fontWeight: 600,
                            fontSize: 12,
                          }}>
                            {inputRow ? `${parseFloat(inputRow.growth_pct).toFixed(1)}%` : '—'}
                          </span>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
