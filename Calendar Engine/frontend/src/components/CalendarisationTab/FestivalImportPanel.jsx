import { useState, useRef, forwardRef, useImperativeHandle } from 'react'
import { importFestivals } from '../../lib/api'

// Bulk festival-to-cluster import, modeled on StoreClusterMappingTab's own
// "upload a template, review a diff before it applies" flow - upload a file,
// see exactly what would change, confirm or cancel. Long-form shape (one row
// per festival+cluster relation), NOT a full replace: unlike store-cluster
// (inherently 1 cluster per store, so a full replace of the mapping makes
// sense), a narrow festival file naming just 2-3 festivals must never touch
// any OTHER cluster's unrelated festivals. Applying is an UPSERT per row.

const KEY_SEP = ''
const csvField = (v) => `"${String(v == null ? '' : v).replace(/"/g, '""')}"`

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

// The triggers (Import Festivals / Download Festival Template) live in the
// Festival tools menu (index.jsx) and call in through this ref; the file input,
// status and review panel stay here, outside the menu, so they show while it is closed.
const FestivalImportPanel = forwardRef(function FestivalImportPanel({ profiles, onApply, isPlanner, busy }, ref) {
  const [preview, setPreview] = useState(null)
  const [status, setStatus] = useState(null)
  const fileRef = useRef(null)
  useImperativeHandle(ref, () => ({ pickFile: () => fileRef.current?.click(), downloadTemplate }))

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

  const d = preview?.diff

  return (
    <>
      {isPlanner && (
        <input ref={fileRef} type="file" accept=".xlsx,.xlsm,.csv,.txt,.tsv" style={{ display: 'none' }}
          onChange={e => { const f = e.target.files[0]; e.target.value = ''; handleFile(f) }} />
      )}
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
})

export default FestivalImportPanel
