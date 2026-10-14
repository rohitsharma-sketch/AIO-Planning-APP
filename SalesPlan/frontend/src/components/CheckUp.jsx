import { useState, useEffect, Fragment } from 'react'
import { theme, alpha } from '../theme'

// Full check-up (user, 2026-10-14: "a full check up from Calendar APP where the sales are being brought in ... aligned with
// AOP forecast (version name) and BIS (version Name) on what all levels - Div/Dep/MRP/UDF ... Qtys should be there for all
// values which are projected ... validated at your end and then signed off otherwise there should be a button which
// rectifies by churning the whole system again") - GET /api/planning/reconciliation/checkup (engines/plan_checkup.py)
const API = '/api/planning/reconciliation/checkup'
const ST = {
  pass: ['PASS', '#15803D'], fail: ['FAIL', '#B91C1C'], warn: ['CHECK', '#B45309'], info: ['INFO', '#475569'],
}
const VER = [['calendar', 'Calendar'], ['aop', 'AOP Forecaster'], ['bis', 'BIS'], ['plan', 'Department plan'], ['mrp', 'MRP Cont %'],
  ['asp', 'ASP master'], ['display_run', 'Display Type run'], ['qty_run', 'Qty run']]
const mmss = v => `${Math.floor(v / 60)}:${String(Math.round(v % 60)).padStart(2, '0')}`
const fmtv = v => (typeof v === 'number' ? (Math.abs(v) >= 1000 ? v.toLocaleString('en-IN', { maximumFractionDigits: 2 }) : v.toLocaleString('en-IN', { maximumFractionDigits: 6 })) : String(v ?? ''))

function Pill({ s }) {
  const [t, c] = ST[s] || ST.info
  return <span style={{ fontSize: 10.5, fontWeight: 800, letterSpacing: 0.6, padding: '2px 8px', borderRadius: 4, color: c, background: alpha(c, '16'), border: `1px solid ${alpha(c, '40')}` }}>{t}</span>
}

export default function CheckUp() {
  const [r, setR] = useState(null)
  const [busy, setBusy] = useState('')
  const [err, setErr] = useState('')
  const [open, setOpen] = useState(() => new Set())
  const call = async (what, method = 'GET', path = '') => {
    setBusy(what); setErr('')
    try {
      const res = await fetch(API + path, { method })
      const j = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(j.detail || `HTTP ${res.status}`)
      if (j.ok === false) throw new Error(j.error)
      setR(j)
    } catch (e) { setErr(e.message) } finally { setBusy('') }
  }
  useEffect(() => { call('check') }, [])   // the kept result - instant while nothing changed
  // the running check / Rectify, read from the server every half second (user, 2026-10-14: "give me a progress bar,
  // elapsed time and remaining time true to the progress bar") - the bar is elapsed / (elapsed + remaining)
  const [prog, setProg] = useState(null)
  useEffect(() => {
    if (busy !== 'check' && busy !== 'fix') { setProg(null); return }
    let live = true
    const tick = async () => {
      const p = await fetch(API + '/progress').then(r => r.ok ? r.json() : null).catch(() => null)
      if (!live) return
      setProg(p?.running ? p : null)
      setTimeout(tick, 500)
    }
    tick()
    return () => { live = false }
  }, [busy])
  const toggle = k => setOpen(o => { const n = new Set(o); n.has(k) ? n.delete(k) : n.add(k); return n })
  const checks = r?.checks || []
  const stages = [...new Set(checks.map(c => c.stage))]
  const fails = checks.filter(c => c.status === 'fail')
  const so = r?.signoff
  const card = { background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: 10, marginBottom: 18 }
  const btn = (on, bg, fg = '#fff') => ({ padding: '8px 16px', borderRadius: 7, border: 'none', fontSize: 13, fontWeight: 600, cursor: on ? 'pointer' : 'not-allowed', background: on ? bg : theme.surfaceAlt, color: on ? fg : theme.textMuted })
  const th = { padding: '8px 12px', textAlign: 'left', fontSize: 11, fontWeight: 700, color: theme.textMuted, textTransform: 'uppercase', letterSpacing: 0.4, borderBottom: `1px solid ${theme.border}`, whiteSpace: 'nowrap' }
  const td = { padding: '8px 12px', fontSize: 12.5, borderBottom: `1px solid ${theme.border}`, verticalAlign: 'top' }
  const head = !r ? null : r.status === 'pass' ? ['Every check passes', '#15803D'] : fails.length ? [`${fails.length} check${fails.length > 1 ? 's' : ''} fail`, '#B91C1C'] : ['Passes - with points to look at', '#B45309']
  return (
    <div>
      <div style={{ ...card, padding: '14px 18px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 260 }}>
            <div style={{ fontSize: 15, fontWeight: 700 }}>Full check-up — the plan tied back to Calendar, AOP, BIS, the re-apportionment and the ASP master</div>
            <div style={{ fontSize: 12, color: theme.textMuted, marginTop: 3 }}>
              {busy === 'check' ? 'Checking…' : busy === 'fix' ? 'Re-running the chain (plan → MRP Cont % → Display Type → Qty), then checking…' : r ? <>Checked {r.checked_at} in {r.seconds} s{r.cached ? ' - nothing it reads has changed since' : ''}{head && <> · <b style={{ color: head[1] }}>{head[0]}</b></>}</> : ''}
            </div>
          </div>
          <button style={btn(!busy, theme.surfaceAlt, theme.primary)} disabled={!!busy} onClick={() => call('check', 'GET', '?fresh=1')}>↺ Check again</button>
          <button style={btn(!busy && r, r?.fixable ? '#B91C1C' : 'var(--st-accent,#4F7A66)')} disabled={!!busy || !r} onClick={() => call('fix', 'POST', '/rectify')}
            title="Regenerate the plan on today's inputs, rebuild the MRP Cont % from the master in use, re-run Display Type and Qty - then check again. Your inputs (BIS, AOP, master, ASP) are not changed.">
            {busy === 'fix' ? 'Rectifying…' : '⟳ Rectify - re-run the chain'}
          </button>
          <button style={btn(!busy && r && !fails.length, '#15803D')} disabled={!!busy || !r || fails.length > 0} onClick={() => call('sign', 'POST', '/signoff')}
            title={fails.length ? 'Sign off needs every check to pass' : 'Record that this plan was checked against these versions'}>✓ Sign off</button>
          <a href={`${API}/export`} style={{ ...btn(true, theme.accent), textDecoration: 'none' }}
            title="One Excel file: Summary (failures first, with their fix), Versions, and one sheet per issue with every row - to fix them all at one go">⬇ Issues report</a>
        </div>
        {prog && (
          <div style={{ marginTop: 12 }} role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(prog.pct)}
            aria-label={`${prog.kind === 'rectify' ? 'Rectify' : 'Check-up'} progress`}>
            <div style={{ height: 8, borderRadius: 4, background: theme.surfaceAlt, overflow: 'hidden', border: `1px solid ${theme.border}` }}>
              <div style={{ height: '100%', width: `${prog.pct}%`, background: 'var(--st-accent,#4F7A66)', transition: 'width 0.5s linear' }} />
            </div>
            <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginTop: 6, fontSize: 12, color: theme.textMuted }}>
              <span style={{ flex: 1, minWidth: 220 }}>Step {prog.i} of {prog.n}: <b style={{ color: theme.textPrimary }}>{prog.step}</b></span>
              <span style={{ fontFamily: theme.fontMono }}>{Math.round(prog.pct)}%</span>
              <span>Elapsed <b style={{ fontFamily: theme.fontMono, color: theme.textPrimary }}>{mmss(prog.elapsed)}</b></span>
              <span>Remaining about <b style={{ fontFamily: theme.fontMono, color: theme.textPrimary }}>{mmss(prog.remaining)}</b></span>
            </div>
          </div>
        )}
        {err && <div style={{ marginTop: 8, fontSize: 12.5, color: theme.danger }}>{err}</div>}
        {so && (
          <div style={{ marginTop: 10, padding: '8px 12px', borderRadius: 8, fontSize: 12.5, background: alpha(so.current ? '#15803D' : '#B45309', '10'), border: `1px solid ${alpha(so.current ? '#15803D' : '#B45309', '44')}` }}>
            {so.current ? <><b>Signed off</b> by {so.by} on {so.at} - the plan and its sources are as they were then.</>
              : <><b>Signed off</b> by {so.by} on {so.at}, but a source changed since (plan, AOP, BIS, Calendar, MRP Cont %, ASP or the Display Type run) - check and sign off again.</>}
          </div>
        )}
        {r?.log && (
          <div style={{ marginTop: 10, fontSize: 12.5, background: theme.surfaceAlt, borderRadius: 8, padding: '8px 12px' }}>
            <b>Rectify ran:</b> {r.log.map((l, i) => <div key={i}>· {l}</div>)}
            {r.needs_input && <div style={{ marginTop: 4, color: '#B45309' }}>What is left needs an input from you (marked "your input" below) - a re-run can't make it up.</div>}
          </div>
        )}
        {r?.versions && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 8, marginTop: 12 }}>
            {VER.map(([k, t]) => (
              <div key={k} style={{ fontSize: 12, padding: '6px 10px', borderRadius: 7, background: theme.surfaceAlt }}>
                <div style={{ fontSize: 10.5, fontWeight: 700, color: theme.textMuted, textTransform: 'uppercase', letterSpacing: 0.4 }}>{t}</div>
                <div style={{ marginTop: 2 }}>{r.versions[k] || '—'}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      {stages.map(sg => (
        <div key={sg} style={{ ...card, overflow: 'hidden' }}>
          <div style={{ padding: '10px 16px', borderBottom: `1px solid ${theme.border}`, fontSize: 13.5, fontWeight: 700, display: 'flex', gap: 10, alignItems: 'center' }}>
            {sg}
            <span style={{ fontSize: 11.5, fontWeight: 400, color: theme.textMuted }}>
              {checks.filter(c => c.stage === sg && c.status === 'pass').length} of {checks.filter(c => c.stage === sg && c.status !== 'info').length} pass
            </span>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead><tr style={{ background: theme.surfaceAlt }}>
                {['', 'Level', 'Check', 'Cells', 'Off', 'Largest gap (₹L)', 'Fix'].map(h => <th key={h} style={th}>{h}</th>)}
              </tr></thead>
              <tbody>{checks.filter(c => c.stage === sg).map(c => {
                const k = c.stage + c.key, isOpen = open.has(k), cols = c.rows?.length ? Object.keys(c.rows[0]) : []
                return (
                  <Fragment key={k}>
                    <tr onClick={() => c.rows?.length && toggle(k)} style={{ cursor: c.rows?.length ? 'pointer' : 'default', background: c.status === 'fail' ? alpha('#B91C1C', '06') : undefined }}>
                      <td style={{ ...td, width: 64 }}><Pill s={c.status} /></td>
                      <td style={{ ...td, color: theme.textMuted, whiteSpace: 'nowrap' }}>{c.level}</td>
                      <td style={td}>
                        <div style={{ fontWeight: 600 }}>{c.rows?.length ? (isOpen ? '▾ ' : '▸ ') : ''}{c.title}</div>
                        {c.note && <div style={{ fontSize: 11.5, color: theme.textMuted, marginTop: 2 }}>{c.note}</div>}
                        {c.where && c.status !== 'pass' && <div style={{ fontSize: 11.5, color: theme.textMuted }}>Largest at {c.where}</div>}
                      </td>
                      <td style={{ ...td, fontFamily: theme.fontMono, textAlign: 'right' }}>{c.cells ? c.cells.toLocaleString('en-IN') : c.rows?.length ? `${c.rows.length} rows` : '—'}</td>
                      <td style={{ ...td, fontFamily: theme.fontMono, textAlign: 'right', color: c.off ? '#B91C1C' : theme.textMuted, fontWeight: c.off ? 700 : 400 }}>{c.off ? c.off.toLocaleString('en-IN') : '0'}</td>
                      <td style={{ ...td, fontFamily: theme.fontMono, textAlign: 'right' }}>{c.largest ? fmtv(c.largest) : '0'}</td>
                      <td style={{ ...td, whiteSpace: 'nowrap', fontSize: 12, color: c.fix === 'rerun' ? '#B91C1C' : c.fix === 'input' ? '#B45309' : theme.textMuted }}>
                        {c.fix === 'rerun' ? 'Rectify fixes it' : c.fix === 'input' ? 'your input' : '—'}
                      </td>
                    </tr>
                    {isOpen && (
                      <tr><td colSpan={7} style={{ padding: 0, borderBottom: `1px solid ${theme.border}` }}>
                        <div style={{ maxHeight: 360, overflow: 'auto', background: theme.surfaceAlt }}>
                          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                            <thead style={{ position: 'sticky', top: 0, background: theme.surfaceAlt }}><tr>{cols.map(h => <th key={h} style={th}>{h}</th>)}</tr></thead>
                            <tbody>{c.rows.map((row, i) => <tr key={i}>{cols.map(h => <td key={h} style={{ ...td, padding: '5px 12px', fontFamily: typeof row[h] === 'number' ? theme.fontMono : 'inherit', textAlign: typeof row[h] === 'number' ? 'right' : 'left' }}>{fmtv(row[h])}</td>)}</tr>)}</tbody>
                          </table>
                          {c.all_rows > c.rows.length && <div style={{ padding: '6px 12px', fontSize: 11.5, color: theme.textMuted }}>First {c.rows.length} of {c.all_rows} - all in the Excel.</div>}
                        </div>
                      </td></tr>
                    )}
                  </Fragment>
                )
              })}</tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  )
}
