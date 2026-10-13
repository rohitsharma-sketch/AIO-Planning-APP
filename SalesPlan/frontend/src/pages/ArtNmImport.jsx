import { useEffect, useRef, useState } from 'react'
import { theme } from '../theme'
import { FiltersRow } from '../components/ExcelFilter'

// Article Name Plan · Buyer's Input - the counterpart of MRP Plan's (user, 2026-10-13: "the article name should be a MRP
// counterpart ... think of it as another parallel branch to MRP"): the buyers' Art Nm Cont % (one % per Department x
// Article Name for the block, with each department's MC TAG). Import / Export only (user, 2026-10-13: "give me an import
// and export function not this" - the folder sync is gone): Export gives the file in use as imported, or a template.
const API = '/api/planning/art-nm'
const DIV_COLOR = { KIDS: '#C85A12', LADIES: '#7420B8', MENS: '#077A4A' }
const TAG_NOTE = {
  'EXISTING ACTIVE MC': 'LY mix x your % (deviation capped 50-150%)',
  'NEW ACTIVE MC': 'your % as it is',
  'NEW SPLIT MC': 'your % as it is, on each split part by article tier',
  'IN-ACTIVE MC': 'LY mix x your % (deviation capped 50-150%)',
}
const card = { background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: 12, padding: '16px 20px' }
const btn = primary => ({ padding: '8px 16px', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer',
  border: `1px solid ${primary ? theme.primary : theme.border}`, background: primary ? theme.primary : theme.surface, color: primary ? '#fff' : theme.textPrimary })

async function readErr(r) {
  if (r.status === 401) return 'Not signed in - sign in again on Landing, then come back'
  try { return (await r.json()).detail || r.statusText } catch { return r.statusText }
}

export default function ArtNmImport() {
  const [cont, setCont] = useState(null)     // the file in use, as read
  const [msg, setMsg] = useState(null)
  const [busy, setBusy] = useState(false)
  const [f, setF] = useState({})
  const [open, setOpen] = useState(null)
  const fileRef = useRef(null)

  const reload = () => {
    fetch(`${API}/cont`)
      .then(async r => { if (r.status === 401) throw new Error(await readErr(r)); return r.ok ? r.json() : null })
      .then(setCont).catch(e => { setCont(null); setMsg({ ok: false, text: e.message }) })
  }
  useEffect(reload, [])

  const upload = async file => {
    if (!file) return
    setBusy(true); setMsg(null)
    try {
      const fd = new FormData(); fd.append('file', file)
      const r = await fetch(`${API}/import`, { method: 'POST', body: fd })
      if (!r.ok) { setMsg({ ok: false, text: await readErr(r) }); return }
      const d = await r.json()
      setMsg({ ok: !d.warnings.length, text: `Imported ${d.source_file}: ${d.departments} departments, ${d.articles} articles, block ${d.block || '?'} · `
        + Object.entries(d.tags).map(([k, v]) => `${v} ${k}`).join(', ') + (d.warnings.length ? ` · ${d.warnings.length} not adding to 100%` : ' · every department adds to 100%') })
      reload()
    } catch (e) { setMsg({ ok: false, text: String(e) }) } finally { setBusy(false); if (fileRef.current) fileRef.current.value = '' }
  }

  const rows = Object.entries(cont?.depts || {}).map(([dept, d]) => {
    const sum = Object.values(d.arts).reduce((s, v) => s + v, 0)
    return { dept, ...d, sum, check: sum === 0 ? 'All 0% (LY mix used)' : Math.abs(sum - 100) > 0.5 ? '≠ 100%' : 'OK' }
  }).sort((a, b) => a.division.localeCompare(b.division) || a.dept.localeCompare(b.dept))
  const val = (r, k) => (k === 'division' ? r.division : k === 'department' ? r.dept : k === 'tag' ? r.tag : r.check)
  const pass = (r, skip) => Object.entries(f).every(([k, v]) => k === skip || v.includes(val(r, k)))
  const shown = rows.filter(r => pass(r))
  const values = k => [...new Set(rows.filter(r => pass(r, k)).map(r => val(r, k)))].sort()
  const th = { padding: '7px 10px', fontSize: 10.5, fontWeight: 700, color: theme.textMuted, textTransform: 'uppercase', letterSpacing: 0.4, textAlign: 'left', borderBottom: `1px solid ${theme.border}`, background: theme.surfaceUp }
  const td = { padding: '6px 10px', fontSize: 12, borderBottom: `1px solid ${theme.border}` }

  return (
    <div style={{ padding: '28px 32px', minHeight: '100vh', background: theme.surfaceAlt }}>
      <div style={{ marginBottom: 14 }}>
        <span style={{ fontSize: 10, fontWeight: 700, padding: '3px 9px', borderRadius: 4, letterSpacing: 0.6, color: theme.primary, border: `1px solid ${theme.border}` }}>ARTICLE NAME PLAN SOURCE</span>
        <p style={{ margin: '8px 0 0', fontSize: 13, color: theme.textMuted }}>
          The buyers' Art Nm Cont % - one % per Department × Article Name for the block (e.g. MAMJ), with each department's MC TAG.
          Plan Output splits the department plan over Article Names with it, by store or cluster as the header's Plan by.
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 2fr) minmax(260px, 1fr)', gap: 16, alignItems: 'start' }}>
        <div style={{ display: 'grid', gap: 16 }}>
          <div style={card}>
            <div style={{ fontSize: 12, fontWeight: 700, color: theme.textMuted, textTransform: 'uppercase', letterSpacing: 0.6, marginBottom: 10 }}>Art Nm Cont %</div>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
              <input ref={fileRef} type="file" accept=".xlsx,.xls" style={{ display: 'none' }} onChange={e => upload(e.target.files[0])} />
              <button type="button" disabled={busy} onClick={() => fileRef.current?.click()} style={{ ...btn(true), minWidth: 150 }}>{busy ? 'Reading…' : '⬆ Import'}</button>
              <button type="button" disabled={busy} onClick={() => window.open(`${API}/export`, '_blank')} style={{ ...btn(false), minWidth: 150 }}
                title={cont ? 'The file in use, exactly as imported - edit it and Import it back' : 'A template: every plan department and its LY articles, filled with the chain LY Art Nm cont %'}>
                ⬇ Export {cont ? 'file in use' : 'template'}
              </button>
              <span style={{ fontSize: 12, color: theme.textMuted }}>
                {cont ? <>In use: <b style={{ color: theme.textPrimary }}>{cont.source_file}</b> · imported {cont.imported_at} · block {cont.block || '?'}</> : 'Nothing imported yet'}
              </span>
            </div>
            {msg && <div style={{ fontSize: 12.5, marginTop: 10, color: msg.ok ? theme.success : theme.danger }}>{msg.text}</div>}
          </div>

          <div style={card}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap', marginBottom: 10 }}>
              <b style={{ fontSize: 14 }}>In use</b>
              <span style={{ fontSize: 12, color: theme.textMuted }}>
                {cont ? `${rows.length} departments` : 'Nothing imported yet - until it is, every department is split on its LY mix.'}
              </span>
            </div>
            {cont && (<>
              <FiltersRow fields={[['division', 'Division'], ['department', 'Department'], ['tag', 'MC Tag'], ['check', 'Check']]}
                filters={f} onChange={setF} values={values} style={{ marginBottom: 10 }}>
                <span style={{ fontSize: 11, color: theme.textMuted }}>{shown.length} of {rows.length}</span>
              </FiltersRow>
              <div style={{ overflow: 'auto', maxHeight: 560, border: `1px solid ${theme.border}`, borderRadius: 8 }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead><tr><th style={th}>Department</th><th style={th}>Division</th><th style={th}>MC Tag</th><th style={th}>How Plan Output uses it</th>
                    <th style={{ ...th, textAlign: 'right' }}>Articles</th><th style={{ ...th, textAlign: 'right' }}>Σ %</th><th style={th}>Check</th></tr></thead>
                  <tbody>{shown.map(r => [
                    <tr key={r.dept} onClick={() => setOpen(o => (o === r.dept ? null : r.dept))} style={{ cursor: 'pointer' }}>
                      <td style={{ ...td, fontWeight: 700, color: DIV_COLOR[r.division] || theme.textPrimary }}>{open === r.dept ? '▾' : '▸'} {r.dept}</td>
                      <td style={td}>{r.division}</td><td style={td}>{r.tag}</td>
                      <td style={{ ...td, color: theme.textMuted }}>{TAG_NOTE[r.tag] || '-'}</td>
                      <td style={{ ...td, textAlign: 'right' }}>{Object.keys(r.arts).length}</td>
                      <td style={{ ...td, textAlign: 'right', fontFamily: theme.fontMono }}>{r.sum.toFixed(1)}%</td>
                      <td style={{ ...td, fontWeight: 600, color: r.check === 'OK' ? theme.success : theme.warning }}>{r.check}</td>
                    </tr>,
                    ...(open === r.dept ? Object.entries(r.arts).map(([a, v]) => (
                      <tr key={r.dept + a}><td style={{ ...td, paddingLeft: 30, fontFamily: theme.fontMono }} colSpan={5}>{a}</td>
                        <td style={{ ...td, textAlign: 'right', fontFamily: theme.fontMono }}>{v.toFixed(1)}%</td><td style={td} /></tr>)) : []),
                  ])}</tbody>
                </table>
              </div>
            </>)}
          </div>
        </div>

        <div style={card}>
          <div style={{ fontSize: 12, fontWeight: 700, color: theme.textMuted, textTransform: 'uppercase', letterSpacing: 0.6, marginBottom: 10 }}>How it works</div>
          {[['Export', 'Export gives the file in use exactly as imported - or, before the first import, a template with every plan department and its LY articles.'],
            ['Import', 'Edit it and Import it back. It is checked first; a bad file changes nothing.'],
            ['Plan Output', "Article Name Plan → Plan Output splits the department plan over Article Names, by store or cluster as the header's Plan by."]].map(([h, t]) => (
            <div key={h} style={{ marginBottom: 12 }}><b style={{ fontSize: 13 }}>{h}</b><div style={{ fontSize: 12.5, color: theme.textMuted, marginTop: 2 }}>{t}</div></div>
          ))}
          <div style={{ borderTop: `1px solid ${theme.border}`, paddingTop: 10, fontSize: 12.5, color: theme.textMuted, lineHeight: 1.6 }}>
            <b style={{ color: theme.textPrimary, fontSize: 12 }}>EXPECTED FILE FORMAT</b><br />
            DIVISION · DEPARTMENT · NEW ARTICLE_NAME · BUYERS INPUT AT <i>block</i> (e.g. AT MAMJ) · MC TAG<br />
            The input as a fraction (0.61) or a % (61). Per department it should add to 100%.<br />
            MC TAG: EXISTING ACTIVE MC, NEW ACTIVE MC, NEW SPLIT MC (a split department under its old name), IN-ACTIVE MC.
          </div>
        </div>
      </div>
    </div>
  )
}
