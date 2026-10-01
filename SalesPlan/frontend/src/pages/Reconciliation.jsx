import { useState, useEffect } from 'react'
import axios from 'axios'
import { theme } from '../theme'

// Reconciliation (user, 2026-09-30: "embed the matrix to give me the least apportioned difference"): every apportioned
// total in the plan vs the sum of its parts, to 8 decimals. Off = a difference that shows at 8 decimals.

const card = { background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: 10, boxShadow: '0 1px 4px rgba(27,79,138,0.05)' }
const th = { padding: '10px 14px', textAlign: 'left', fontWeight: 600, color: theme.textSecondary, fontSize: 12, letterSpacing: 0.4, borderBottom: `1px solid ${theme.border}`, whiteSpace: 'nowrap' }
const td = { padding: '9px 14px', fontVariantNumeric: 'tabular-nums', borderBottom: `1px solid ${theme.border}` }
const btn = (bg, fg = '#fff') => ({ padding: '8px 18px', borderRadius: 7, border: 'none', background: bg, color: fg, fontSize: 13, fontWeight: 600, cursor: 'pointer' })
const d8 = v => (v ?? 0).toFixed(8)
const N = v => (v ?? 0).toLocaleString('en-IN')
const L2 = v => (v ?? 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

export default function Reconciliation() {
  const [r, setR] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const load = async () => {
    setBusy(true); setError(null)
    try { setR((await axios.get('/api/planning/reconciliation')).data) }
    catch { setError('Could not run the reconciliation.') }
    setBusy(false)
  }
  useEffect(() => { load() }, [])

  const storeCells = r ? r.summary.filter(s => s.level.startsWith('Store')).reduce((t, s) => t + s.cells, 0) : 0
  const allOk = r && storeCells > 0 && r.summary.every(s => s.off === 0)

  return (
    <div style={{ height: '100%', overflowY: 'auto', padding: '24px 32px', background: theme.surfaceAlt }}>
      {error && <div style={{ background: '#FEF2F2', border: `1px solid ${theme.danger}`, borderRadius: 8, padding: '10px 16px', marginBottom: 18, color: theme.danger, fontSize: 13 }}>{error}</div>}

      <div style={{ ...card, padding: '12px 18px', marginBottom: 18, display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', fontSize: 13 }}>
        <span style={{ flex: 1, color: theme.textPrimary }}>
          <strong>Every apportioned total vs the sum of its parts, to 8 decimals.</strong>
          {r?.source ? <span style={{ color: theme.textMuted }}> · checks {r.source} (generated {r.generated_at})</span>
            : r && <span style={{ color: theme.textMuted }}> · no plan generated yet</span>}
        </span>
        <button style={btn(theme.surfaceAlt, theme.primary)} onClick={load} disabled={busy}>{busy ? 'Checking…' : '↺ Refresh'}</button>
        <a href="/api/planning/reconciliation/export" style={{ ...btn(theme.accent), textDecoration: 'none' }}>⬇ Download Excel</a>
      </div>

      {r && r.summary.length > 0 && (
        <div style={{ ...card, marginBottom: 20, overflow: 'hidden' }}>
          <div style={{ padding: '14px 20px', borderBottom: `1px solid ${theme.border}`, fontSize: 14, fontWeight: 600, color: allOk ? theme.accent : storeCells === 0 ? theme.textSecondary : theme.danger }}>
            {storeCells === 0 ? `The saved plan (${r.source}, ${r.generated_at}) has no plan months to check - generate it (Department Plan → Growth Matrix → ▶ Generate Base Plan) and refresh.`
              : allOk ? 'Every check adds back exactly — 0.00000000' : `${N(r.off_count)} cells are off at 8 decimals`}
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead><tr style={{ background: theme.surfaceAlt }}>
                <th style={th}>Check</th><th style={th}>Cells checked</th><th style={th}>Off at 8 dp</th><th style={th}>Largest difference</th><th style={th}>Where</th>
              </tr></thead>
              <tbody>{r.summary.map(s => (
                <tr key={s.level}>
                  <td style={{ ...td, color: theme.textPrimary, fontWeight: 600 }}>{s.level}</td>
                  <td style={td}>{N(s.cells)}</td>
                  <td style={{ ...td, color: s.off ? theme.danger : theme.accent, fontWeight: 700 }}>{N(s.off)}</td>
                  <td style={{ ...td, fontFamily: theme.fontMono }}>{d8(s.largest)}</td>
                  <td style={{ ...td, color: theme.textMuted }}>{s.largest > 0 ? s.where : '—'}</td>
                </tr>))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {r && r.off.length > 0 && (
        <div style={{ ...card, marginBottom: 20, overflow: 'hidden' }}>
          <div style={{ padding: '14px 20px', borderBottom: `1px solid ${theme.border}`, fontSize: 14, fontWeight: 600, color: theme.textPrimary }}>
            Off at 8 decimals{r.off_count > r.off.length ? ` — first ${N(r.off.length)} of ${N(r.off_count)} (all in the Excel)` : ''}
          </div>
          <div style={{ overflowX: 'auto', maxHeight: 420 }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
              <thead><tr style={{ background: theme.surfaceAlt }}>{['Check', 'Store', 'Division', 'Department', 'Month', 'Total', 'Sum of parts', 'Difference'].map(h => <th key={h} style={th}>{h}</th>)}</tr></thead>
              <tbody>{r.off.map((o, i) => (
                <tr key={i}>
                  <td style={td}>{o.Level}</td><td style={td}>{o.Store}</td><td style={td}>{o.Division}</td><td style={td}>{o.Department}</td><td style={td}>{o.Month}</td>
                  <td style={td}>{d8(o.Total)}</td><td style={td}>{d8(o['Sum of parts'])}</td><td style={{ ...td, color: theme.danger, fontWeight: 600 }}>{d8(o.Difference)}</td>
                </tr>))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {r && r.uncovered?.length > 0 && (
        <div style={{ ...card, overflow: 'hidden' }}>
          <div style={{ padding: '14px 20px', borderBottom: `1px solid ${theme.border}`, fontSize: 14, fontWeight: 600, color: theme.textPrimary }}>
            Not split to MRPs — ₹ {L2(r.uncovered_total)} L has no MRP shares
            <div style={{ fontSize: 12, fontWeight: 400, color: theme.textMuted, marginTop: 3 }}>Not a rounding difference: the MRP plan has no shares for these departments / months. Add them in the MRP plan (Buyer's Input) to split them.</div>
          </div>
          <div style={{ overflowX: 'auto', maxHeight: 420 }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
              <thead><tr style={{ background: theme.surfaceAlt }}>{['Division', 'Department', 'Why', 'TY not split (₹ L)'].map(h => <th key={h} style={th}>{h}</th>)}</tr></thead>
              <tbody>{r.uncovered.map((u, i) => (
                <tr key={i}><td style={td}>{u.Division}</td><td style={td}>{u.Department}</td><td style={{ ...td, color: theme.textMuted }}>{u.Why}</td><td style={td}>{L2(u['TY not split to MRPs (₹ L)'])}</td></tr>))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
