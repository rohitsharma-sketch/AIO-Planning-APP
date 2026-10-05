import { useState, useEffect } from 'react'
import { importFestivals } from '../../lib/api'
import { festivalYearTable, loadFestivalReference } from '../../lib/festivalData'

// Bulk festival-to-cluster import, modeled on StoreClusterMappingTab's own
// "upload a template, review a diff before it applies" flow - upload a file,
// see exactly what would change, confirm or cancel. Long-form shape (one row
// per festival+cluster relation), NOT a full replace: unlike store-cluster
// (inherently 1 cluster per store, so a full replace of the mapping makes
// sense), a narrow festival file naming just 2-3 festivals must never touch
// any OTHER cluster's unrelated festivals. Applying is an UPSERT per row.

const KEY_SEP = ''
const csvField = (v) => `"${String(v == null ? '' : v).replace(/"/g, '""')}"`
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function downloadCsv(text, filename) {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/csv' }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

// Compare imported rows (only those whose resolvedCluster is a real cluster)
// against the live profiles - added (no festival of that name in that
// cluster yet) or updated (exists, but some field differs). Never "removed":
// an import only ever adds/updates the rows it explicitly names.
function computeDiff(profiles, rows, clusterNames) {
  const known = new Set(clusterNames)
  const current = new Map()
  for (const p of profiles) {
    for (const f of p.festivals) current.set(`${p.name}${KEY_SEP}${f.name}`, f)
  }
  const added = [], updated = [], unchanged = [], invalid = []
  for (const r of rows) {
    const cluster = r.resolvedCluster || r.cluster
    if (!known.has(cluster)) { invalid.push(r); continue }
    const key = `${cluster}${KEY_SEP}${r.festival}`
    const existing = current.get(key)
    if (!existing) { added.push({ ...r, cluster }); continue }
    const changed = existing.refDate !== r.refDate || existing.futDate !== r.futDate ||
      existing.pre !== r.pre || existing.core !== r.core || existing.post !== r.post ||
      !!existing.independent !== !!r.independent
    if (changed) updated.push({ ...r, cluster, from: existing })
    else unchanged.push({ ...r, cluster })
  }
  return { added, updated, unchanged, invalid }
}

export default function FestivalImportPanel({ profiles, onApply, isPlanner, busy, refYear, futYear }) {
  // "Download Festival Dates" (user, 2026-10-05): every festival with its date in each year of the chosen range -
  // no clusters. Range defaults to the Version Setting years until the user picks their own.
  const [yrFrom, setYrFrom] = useState(null)
  const [yrTo, setYrTo] = useState(null)
  useEffect(() => { if (yrFrom == null && refYear) setYrFrom(Number(refYear)) }, [refYear])  // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (yrTo == null && futYear) setYrTo(Number(futYear)) }, [futYear])      // eslint-disable-line react-hooks/exhaustive-deps
  const [preview, setPreview] = useState(null)
  const [status, setStatus] = useState(null)

  const clusterNames = profiles.map(p => p.name)

  async function handleFile(file) {
    if (!isPlanner || !file) return
    setStatus(null)
    try {
      const result = await importFestivals(file)
      const diff = computeDiff(profiles, result.rows, clusterNames)
      if (!diff.added.length && !diff.updated.length) {
        setPreview(null)
        const skipped = diff.invalid.length ? ` (${diff.invalid.length} row(s) skipped - unknown cluster)` : ''
        setStatus({ ok: false, msg: `Nothing to import - every named (festival, cluster) row already matches${skipped}.` })
        return
      }
      setPreview({ filename: result.filename || file.name, diff })
    } catch (e) {
      setStatus({ ok: false, msg: e.message })
    }
  }

  function confirmImport() {
    if (!isPlanner || !preview) return
    const { added, updated } = preview.diff
    // One shared id counter above every existing id across every cluster, so
    // a newly-added row's id can't collide with one already in use anywhere -
    // same rule handleAddFestival (CalendarisationTab/index.jsx) follows.
    let nextId = 1
    for (const p of profiles) for (const f of p.festivals) nextId = Math.max(nextId, (Number(f.id) || 0) + 1)
    const addByCluster = new Map()
    for (const r of added) {
      if (!addByCluster.has(r.cluster)) addByCluster.set(r.cluster, [])
      addByCluster.get(r.cluster).push(r)
    }
    const updateByKey = new Map(updated.map(r => [`${r.cluster}${KEY_SEP}${r.festival}`, r]))

    const merged = profiles.map(p => {
      let festivals = p.festivals.map(f => {
        const u = updateByKey.get(`${p.name}${KEY_SEP}${f.name}`)
        return u ? { ...f, refDate: u.refDate, futDate: u.futDate, pre: u.pre, core: u.core, post: u.post, independent: u.independent } : f
      })
      const toAdd = addByCluster.get(p.name) || []
      if (toAdd.length) {
        festivals = [...festivals, ...toAdd.map(r => ({
          id: nextId++, name: r.festival, refDate: r.refDate, futDate: r.futDate,
          pre: r.pre, core: r.core, post: r.post, independent: r.independent,
        }))]
      }
      return { ...p, festivals }
    })

    onApply(merged, `Imported ${preview.filename}: ${added.length} added, ${updated.length} updated`)
    setPreview(null)
  }

  function downloadTemplate() {
    const rows = ['Festival,Cluster,Reference Date,Future Date,Pre,Core,Post,Independent']
    for (const p of profiles) {
      for (const f of p.festivals) {
        rows.push([f.name, p.name, f.refDate, f.futDate, f.pre, f.core, f.post, f.independent ? 'TRUE' : 'FALSE']
          .map(csvField).join(','))
      }
    }
    downloadCsv(rows.join('\n'), 'festival_cluster_template.csv')
  }

  async function downloadFestivalDates() {
    const a = Number(yrFrom), b = Number(yrTo)
    if (!a || !b || a > b) { setStatus({ ok: false, msg: 'Pick a From year that is not after the To year.' }); return }
    if (b - a > 20) { setStatus({ ok: false, msg: 'Pick at most 21 years.' }); return }
    await loadFestivalReference()   // the Google reference first, as the calendar itself uses
    const { years, rows } = festivalYearTable(a, b)
    const fmt = iso => { if (!iso) return ''; const [y, m, dd] = iso.split('-'); return `${dd}-${MON[+m - 1]}-${y}` }
    const out = [['Festival', ...years].map(csvField).join(',')]
    rows.forEach(r => out.push([r.name, ...r.dates.map(fmt)].map(csvField).join(',')))
    downloadCsv(out.join('\n'), `festival_dates_${a}-${b}.csv`)
    setStatus({ ok: true, msg: `Downloaded ${rows.length} festivals x ${years.length} year${years.length === 1 ? '' : 's'} (${a}-${b})` })
  }

  const d = preview?.diff

  return (
    <>
      {isPlanner && (
        <label className="btn" style={{ cursor: 'pointer', display: 'inline-flex', alignItems: 'center' }}>
          Import Festivals
          <input type="file" accept=".xlsx,.xlsm,.csv,.txt,.tsv" style={{ display: 'none' }}
            onChange={e => { const f = e.target.files[0]; e.target.value = ''; handleFile(f) }} />
        </label>
      )}
      <button onClick={downloadTemplate} title="Download every cluster's current festivals as one long-form CSV - edit rows or add new ones for other clusters, then re-upload with Import Festivals">
        Download Festival Template (CSV)
      </button>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '12px' }}
        title="Every festival with its date in each year of the range - no clusters">
        Festival dates from
        <input type="number" min="2000" max="2100" value={yrFrom ?? ''} onChange={e => setYrFrom(e.target.value)} style={{ width: '70px' }} />
        to
        <input type="number" min="2000" max="2100" value={yrTo ?? ''} onChange={e => setYrTo(e.target.value)} style={{ width: '70px' }} />
        <button onClick={downloadFestivalDates}>Download Festival Dates (CSV)</button>
      </span>
      {status && (
        <span style={{ color: status.ok ? 'var(--green)' : 'var(--red)', fontSize: '12px' }}>{status.msg}</span>
      )}

      {preview && (
        // flexBasis 100% forces this onto its own line inside the parent's
        // wrapping flex toolbar, instead of squeezing in beside the buttons.
        <div className="card" style={{ flexBasis: '100%' }}>
          <h4 style={{ marginTop: 0 }}>Review festival import from {preview.filename}</h4>
          <div className="scm-toolbar">
            <span className="scm-pill scm-pill-ok">+{d.added.length} added</span>
            <span className="scm-pill scm-pill-warn">{d.updated.length} updated</span>
            {d.invalid.length > 0 && <span className="scm-pill scm-pill-bad">{d.invalid.length} skipped (unknown cluster)</span>}
            {d.unchanged.length > 0 && <span style={{ fontSize: '12px', color: 'var(--muted)' }}>{d.unchanged.length} already up to date</span>}
          </div>
          <div className="scm-mini-wrap">
            <table className="scm-mini">
              <thead><tr><th>Change</th><th>Festival</th><th>Cluster</th><th>Ref Date</th><th>Fut Date</th><th>Pre</th><th>Core</th><th>Post</th><th>Independent</th></tr></thead>
              <tbody>
                {d.added.map((r, i) => (
                  <tr key={`a-${i}`}>
                    <td>Added</td><td style={{ fontWeight: 600 }}>{r.festival}</td><td>{r.cluster}</td>
                    <td>{r.refDate}</td><td>{r.futDate}</td><td>{r.pre}</td><td>{r.core}</td><td>{r.post}</td><td>{r.independent ? 'Yes' : ''}</td>
                  </tr>
                ))}
                {d.updated.map((r, i) => (
                  <tr key={`u-${i}`}>
                    <td>Updated</td><td style={{ fontWeight: 600 }}>{r.festival}</td><td>{r.cluster}</td>
                    <td>{r.refDate}</td><td>{r.futDate}</td><td>{r.pre}</td><td>{r.core}</td><td>{r.post}</td><td>{r.independent ? 'Yes' : ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {d.invalid.length > 0 && (
            <p style={{ fontSize: '11px', color: 'var(--warn)', marginTop: '8px' }}>
              Skipped - cluster name not recognized: {d.invalid.map(r => `${r.festival} (${r.cluster})`).join(', ')}
            </p>
          )}
          <div className="scm-toolbar" style={{ marginTop: '10px', marginBottom: 0 }}>
            <button className="btn" disabled={busy} onClick={confirmImport}>Confirm &amp; Apply</button>
            <button disabled={busy} onClick={() => setPreview(null)}>Cancel</button>
          </div>
        </div>
      )}
    </>
  )
}
