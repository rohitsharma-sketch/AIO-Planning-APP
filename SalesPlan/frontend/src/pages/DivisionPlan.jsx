import { useState, useEffect } from 'react'
import axios from 'axios'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { theme } from '../theme'

// Division Plan = the plan BIS shows (user, 2026-09-29): only BIS's months (Mar'27-Jun'27), LY base and plan
// read from the AOP publish BIS plans on - nothing typed here, nothing past Jun'27. Change the plan in BIS.

const btnStyle = (color, textColor = '#fff') => ({
  padding: '8px 18px', borderRadius: 7, border: 'none', background: color, color: textColor,
  fontSize: 13, fontWeight: 600, cursor: 'pointer', letterSpacing: 0.3,
})
const card = {
  background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: 10,
  boxShadow: '0 1px 4px rgba(27,79,138,0.05)',
}
const th = {
  padding: '10px 14px', textAlign: 'left', fontWeight: 600, color: theme.textSecondary, fontSize: 12,
  letterSpacing: 0.4, borderBottom: `1px solid ${theme.border}`, whiteSpace: 'nowrap',
}
const td = { padding: '9px 14px', fontVariantNumeric: 'tabular-nums' }
const L = v => (v ?? 0).toLocaleString('en-IN', { maximumFractionDigits: 2 })
const Cr = v => ((v ?? 0) / 100).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })   // ₹ lakhs -> crores
const pct = v => v == null ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`

export default function DivisionPlan() {
  const [cfg, setCfg] = useState(null)
  const [error, setError] = useState(null)
  const [cmpId, setCmpId] = useState('')      // "Compare with" another saved AOP version (user, 2026-09-30) - view only
  const [cmp, setCmp] = useState(null)

  const load = async () => {
    setError(null)
    try { setCfg((await axios.get('/api/planning/division-plan/config')).data) }
    catch { setError('Failed to load the plan from the backend.') }
  }
  useEffect(() => { load() }, [])
  useEffect(() => {
    setCmp(null)
    if (!cmpId) return
    axios.get(`/api/planning/division-plan/compare/${cmpId}`).then(r => setCmp(r.data))
      .catch(() => { setError('Could not load that version to compare.'); setCmpId('') })
  }, [cmpId])

  const exportCSV = () => {
    const lines = ['AOP Version,Division,Month,LY (Lakhs),Plan (Lakhs),Growth %', ...cfg.divisions.flatMap(d =>
      d.months.map(m => `${cfg.version_label || ''},${d.division_name},${m.month},${m.ly},${m.plan},${m.growth_pct ?? ''}`))]
    const url = URL.createObjectURL(new Blob([lines.join('\n')], { type: 'text/csv' }))
    const a = document.createElement('a')
    a.href = url
    a.download = 'division_plan.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  const totalGrowth = cfg && cfg.total_ly ? (cfg.total_plan / cfg.total_ly - 1) * 100 : null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ flex: 1, overflowY: 'auto', padding: '24px 32px', background: theme.surfaceAlt }}>

        {error && (
          <div style={{ background: '#FEF2F2', border: `1px solid ${theme.danger}`, borderRadius: 8,
            padding: '10px 16px', marginBottom: 18, color: theme.danger, fontSize: 13 }}>{error}</div>
        )}

        {cfg && (<>
          <div style={{ ...card, padding: '12px 18px', marginBottom: 18, display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', fontSize: 13 }}>
            <span style={{ flex: 1, color: theme.textPrimary }}>
              <strong>{cfg.source}</strong> · Mar'27 – Jun'27 · like-for-like stores, as in BIS · {cfg.n_divisions} divisions (KLM)
              <span style={{ color: theme.textMuted, marginLeft: 8 }}>· LY base and plan are fixed by the AOP publish; change the plan in BIS</span>
            </span>
            {cfg.versions?.some(v => v.id !== cfg.aop_publish_id) && (
              <label style={{ display: 'inline-flex', alignItems: 'center', gap: 8, color: theme.textSecondary, fontWeight: 600 }}>
                Compare with
                <select value={cmpId} onChange={e => setCmpId(e.target.value)} aria-label="Compare with another saved AOP version"
                  style={{ height: 34, padding: '0 10px', borderRadius: 7, border: `1px solid ${theme.border}`, background: theme.surface, color: theme.textPrimary, font: 'inherit', fontWeight: 500 }}>
                  <option value="">— none —</option>
                  {cfg.versions.filter(v => v.id !== cfg.aop_publish_id).map(v => (
                    <option key={v.id} value={v.id}>{v.label} (publish {v.id})</option>
                  ))}
                </select>
              </label>
            )}
            <button style={btnStyle(theme.surfaceAlt, theme.primary)} onClick={load}>↺ Refresh</button>
            <button style={btnStyle(theme.accent)} onClick={exportCSV}>⬇ Export CSV</button>
          </div>

          <div style={{ display: 'flex', gap: 16, marginBottom: 22 }}>
            {[
              { label: 'LY Base MAMJ', value: `₹ ${Cr(cfg.total_ly)} Cr`, title: `₹ ${L(cfg.total_ly)} L`, color: theme.textPrimary },
              { label: 'Plan MAMJ', value: `₹ ${Cr(cfg.total_plan)} Cr`, title: `₹ ${L(cfg.total_plan)} L`, color: theme.primary },
              { label: 'Plan Growth', value: pct(totalGrowth), color: theme.accent },
            ].map(c => (
              <div key={c.label} title={c.title} style={{ ...card, flex: 1, padding: '18px 22px' }}>
                <div style={{ fontSize: 12, color: theme.textMuted, fontWeight: 600, letterSpacing: 0.5, marginBottom: 6 }}>{c.label.toUpperCase()}</div>
                <div style={{ fontSize: 26, fontWeight: 700, color: c.color }}>{c.value}</div>
              </div>
            ))}
          </div>

          <div style={{ ...card, marginBottom: 24, overflow: 'hidden' }}>
            <div style={{ padding: '14px 20px', borderBottom: `1px solid ${theme.border}`, fontSize: 14, fontWeight: 600, color: theme.textPrimary }}>
              Division Plan (as in BIS)
            </div>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ background: theme.surfaceAlt }}>
                    <th style={th}>Division</th>
                    {cfg.divisions[0]?.months.map(m => <th key={m.month} style={th}>{m.month} LY / Plan (₹ L)</th>)}
                    <th style={th}>LY Base MAMJ (₹ L)</th>
                    <th style={th}>Plan MAMJ (₹ L)</th>
                    <th style={th}>Growth %</th>
                  </tr>
                </thead>
                <tbody>
                  {cfg.divisions.map((d, idx) => (
                    <tr key={d.division_name} style={{ background: idx % 2 === 0 ? theme.surface : theme.surfaceAlt }}>
                      <td style={{ ...td, fontWeight: 600, color: theme.textPrimary }}>{d.division_name}</td>
                      {d.months.map(m => (
                        <td key={m.month} style={td} title={`${m.month}: LY ₹ ${L(m.ly)} L → plan ₹ ${L(m.plan)} L (${pct(m.growth_pct)})`}>
                          <span style={{ color: theme.textMuted }}>{L(m.ly)}</span> / <strong style={{ color: theme.primary }}>{L(m.plan)}</strong>
                        </td>
                      ))}
                      <td style={td}>{L(d.ly_mamj)}</td>
                      <td style={{ ...td, color: theme.primary, fontWeight: 700 }}>{L(d.plan_mamj)}</td>
                      <td style={td}>
                        <span style={{ background: theme.accentLight, color: theme.accent, borderRadius: 5, padding: '2px 7px', fontWeight: 600, fontSize: 12 }}>
                          {pct(d.growth_pct)}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {cmp && (() => {
            const bis = Object.fromEntries(cfg.divisions.map(d => [d.division_name, d]))
            const diff = (a, b) => a - b
            const dpct = (a, b) => b ? (a / b - 1) * 100 : null
            const col = v => v > 0.005 ? theme.accent : v < -0.005 ? theme.danger : theme.textMuted
            const sign = v => `${v > 0 ? '+' : ''}${L(v)}`
            const rows = cmp.divisions.map(d => ({ d, b: bis[d.division_name] }))
            const tot = rows.reduce((t, { d, b }) => ({ v: t.v + d.plan_mamj, b: t.b + (b?.plan_mamj || 0), ly: t.ly + (b?.ly_mamj || 0) }), { v: 0, b: 0, ly: 0 })
            return (
              <div style={{ ...card, marginBottom: 24, overflow: 'hidden', borderColor: theme.primary }}>
                <div style={{ padding: '14px 20px', borderBottom: `1px solid ${theme.border}`, fontSize: 14, fontWeight: 600, color: theme.textPrimary, display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'baseline' }}>
                  <span>Comparison: {cmp.version_label} vs the BIS plan ({cfg.version_label})</span>
                  <span style={{ fontSize: 12, fontWeight: 400, color: theme.textMuted }}>view only · plan ₹ L, difference = {cmp.version_label.split(' — ')[0]} − BIS plan · growth on this page's LY base</span>
                </div>
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                    <thead>
                      <tr style={{ background: theme.surfaceAlt }}>
                        <th style={th}>Division</th>
                        {cmp.divisions[0]?.months.map(m => <th key={m.month} style={th}>{m.month} plan / diff</th>)}
                        <th style={th}>Plan MAMJ</th>
                        <th style={th}>BIS plan MAMJ</th>
                        <th style={th}>Difference</th>
                        <th style={th}>Growth %</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map(({ d, b }, idx) => (
                        <tr key={d.division_name} style={{ background: idx % 2 === 0 ? theme.surface : theme.surfaceAlt }}>
                          <td style={{ ...td, fontWeight: 600, color: theme.textPrimary }}>{d.division_name}</td>
                          {d.months.map((m, i) => {
                            const bp = b?.months[i]?.plan || 0, dv = diff(m.plan, bp)
                            return (
                              <td key={m.month} style={td} title={`${m.month}: ${cmp.version_label} ₹ ${L(m.plan)} L vs BIS plan ₹ ${L(bp)} L (${pct(dpct(m.plan, bp))})`}>
                                <strong style={{ color: theme.textPrimary }}>{L(m.plan)}</strong> <span style={{ color: col(dv), fontSize: 12 }}>{sign(dv)}</span>
                              </td>
                            )
                          })}
                          <td style={{ ...td, fontWeight: 700 }}>{L(d.plan_mamj)}</td>
                          <td style={{ ...td, color: theme.primary }}>{L(b?.plan_mamj)}</td>
                          <td style={{ ...td, color: col(diff(d.plan_mamj, b?.plan_mamj || 0)), fontWeight: 600 }}>{sign(diff(d.plan_mamj, b?.plan_mamj || 0))} <span style={{ fontSize: 12 }}>({pct(dpct(d.plan_mamj, b?.plan_mamj))})</span></td>
                          <td style={td}>{pct(dpct(d.plan_mamj, b?.ly_mamj))}</td>
                        </tr>
                      ))}
                      <tr style={{ borderTop: `1px solid ${theme.border}`, fontWeight: 700 }}>
                        <td style={td}>Total</td>
                        {cmp.divisions[0]?.months.map(m => <td key={m.month} style={td}></td>)}
                        <td style={td}>{L(tot.v)}</td>
                        <td style={{ ...td, color: theme.primary }}>{L(tot.b)}</td>
                        <td style={{ ...td, color: col(tot.v - tot.b) }}>{sign(tot.v - tot.b)} <span style={{ fontSize: 12 }}>({pct(dpct(tot.v, tot.b))})</span></td>
                        <td style={td}>{pct(dpct(tot.v, tot.ly))}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            )
          })()}
          <div style={{ fontSize: 13, fontWeight: 600, color: theme.textMuted, letterSpacing: 0.7, textTransform: 'uppercase', marginBottom: 14 }}>
            Monthly Plan by Division
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: 18 }}>
            {cfg.divisions.map(d => (
              <div key={d.division_name} style={{ ...card, padding: '16px 18px' }}>
                <div style={{ fontSize: 14, fontWeight: 700, color: theme.textPrimary, marginBottom: 4 }}>{d.division_name}</div>
                <div style={{ fontSize: 12, color: theme.textSecondary, marginBottom: 14 }}>
                  Plan MAMJ: <strong>₹ {L(d.plan_mamj)} L</strong> · {pct(d.growth_pct)} on LY ₹ {L(d.ly_mamj)} L
                </div>
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={d.months} margin={{ top: 0, right: 0, left: -10, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={theme.border} />
                    <XAxis dataKey="month" tick={{ fontSize: 11, fill: theme.textSecondary }} />
                    <YAxis tick={{ fontSize: 11, fill: theme.textSecondary }} />
                    <Tooltip formatter={(v, n) => [`₹ ${L(v)} L`, n]}
                      contentStyle={{ fontSize: 12, borderRadius: 6, border: `1px solid ${theme.border}` }} />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Bar dataKey="ly" name="LY" fill={theme.textMuted} fillOpacity={0.45} radius={[3, 3, 0, 0]} />
                    <Bar dataKey="plan" name="Plan" fill={theme.primary} radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ))}
          </div>
        </>)}
      </div>
    </div>
  )
}
