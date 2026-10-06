import { useState, useEffect } from 'react'
import './PlanLanding.css'
import { apiUrl } from '../lib/apiBase'

// Version list lives in the DB — visible on every machine that shares the DB.
// A fingerprint cache stays in localStorage for the sync isMajorChangeVsLog check.
const PLAN_LOG_FP_KEY = 'aop.autosave.plan_fp'
const MAMJ_KEYS       = ["Mar'27","Apr'27","May'27","Jun'27"]
const PLAN_DIVS       = ['MENS','LADIES','KIDS']

export async function loadPlanVersions() {
  try {
    const r = await fetch(apiUrl('/api/plan-versions'), { cache: 'no-store' })
    if (!r.ok) throw new Error('api')
    return await r.json()
  } catch {
    return []
  }
}

export async function savePlanVersion(sessionId, rates, baseSource, labelOverride = null) {
  const versions = await loadPlanVersions()
  const fp  = _fingerprint(rates)
  const now = new Date().toISOString()

  // FIXED 2026-09-23: this used to be versions[0] - the globally
  // most-recently-modified version, with no connection to which version's
  // session is actually being saved. If the user loaded an OLDER version,
  // edited it, and the edit's fingerprint delta happened to look "minor"
  // relative to whatever version was most-recently-modified elsewhere, the
  // save would silently overwrite that UNRELATED top version's sessionId/
  // fingerprint - corrupting a different saved plan. sessionId is already
  // this function's own argument - look up the version that actually
  // matches the session being saved, not just "whichever is newest."
  const existing = versions.find(v => v.sessionId === sessionId)
  const isMajor  = !existing || _isMajorChange(existing.fingerprint, fp)

  let entry
  if (existing && !isMajor) {
    entry = { ...existing, sessionId, fingerprint: fp, lastModifiedAt: now }
  } else {
    const n = versions.length + 1
    const label = labelOverride ||
      `Version ${n} — ${new Date().toLocaleDateString('en-IN', { day:'2-digit', month:'short', year:'numeric' })}`
    entry = { id: crypto.randomUUID(), label, sessionId, baseSource, fingerprint: fp, createdAt: now, lastModifiedAt: now }
  }

  await fetch(apiUrl('/api/plan-versions'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(entry),
  }).catch(() => {})

  try { localStorage.setItem(PLAN_LOG_FP_KEY, JSON.stringify(fp)) } catch {}
  return isMajor
}

// True when a run of this session with these rates would be saved as a NEW version while the session already belongs
// to a saved one - the run then goes on a forked copy so the saved version's files stay its own (audit 2026-10-06)
export async function needsFork(sessionId, rates) {
  if (!rates) return false
  const existing = (await loadPlanVersions()).find(v => v.sessionId === sessionId)
  return !!existing && _isMajorChange(existing.fingerprint, _fingerprint(rates))
}

export async function deletePlanVersion(id) {
  await fetch(apiUrl(`/api/plan-versions/${id}`), { method: 'DELETE' }).catch(() => {})
}

// The POST endpoint is an upsert (ON CONFLICT id DO UPDATE) - renaming is just
// re-posting the SAME stored object with its label swapped, same id, no
// dedicated rename endpoint needed.
export async function renamePlanVersion(version, newLabel) {
  await fetch(apiUrl('/api/plan-versions'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...version, label: newLabel, lastModifiedAt: new Date().toISOString() }),
  }).catch(() => {})
}

export function isMajorChangeVsLog(rates) {
  // Sync — reads local fp cache only (used for save-before-leave dialog)
  try {
    const fp = JSON.parse(localStorage.getItem(PLAN_LOG_FP_KEY) || 'null')
    if (!fp) return false
    return _isMajorChange(fp, _fingerprint(rates))
  } catch { return false }
}

function _fingerprint(rates) {
  if (!rates) return {}
  const fp = {}
  for (const div of PLAN_DIVS) {
    for (const m of MAMJ_KEYS) fp[`${div}|${m}`] = parseFloat(rates[div]?.[m] ?? 0)
  }
  return fp
}

function _isMajorChange(fpOld, fpNew) {
  if (!fpOld) return true
  let changed = 0, totalDelta = 0
  for (const k of Object.keys(fpNew)) {
    const delta = Math.abs((fpNew[k] || 0) - (fpOld[k] || 0))
    if (delta > 0.01) { changed++; totalDelta += delta }
  }
  // Major if more than 3 cells changed OR total delta across MAMJ cells > 5 pp
  return changed > 3 || totalDelta > 5
}

function _avgGrowth(fp) {
  const vals = Object.values(fp).filter(v => v !== 0)
  if (!vals.length) return null
  return (vals.reduce((a, v) => a + v, 0) / vals.length).toFixed(1)
}

// ─────────────────────────────────────────────────────────────────────────────

const fmtWhen = iso => new Date(iso).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
const signed  = v => (v > 0 ? '+' : '') + v

export default function PlanLanding({ onNewPlan, onResume }) {
  const [versions, setVersions] = useState([])
  const [loaded, setLoaded] = useState(false)

  // {version label -> latest publish} from /api/config/aop-versions. Its
  // lfl_growth_pct is target / base (2026-09-25) - the same growth AOP's
  // Summary and BIS show, so the card can never disagree with either.
  const [publishByLabel, setPublishByLabel] = useState({})
  useEffect(() => {
    loadPlanVersions().then(v => { setVersions(v); setLoaded(true) })
    fetch(apiUrl('/api/config/aop-versions'), { cache: 'no-store' })
      .then(r => (r.ok ? r.json() : { versions: [] }))
      .then(d => setPublishByLabel(Object.fromEntries((d.versions || []).map(p => [p.version_label, p]))))
      .catch(() => {})
  }, [])

  async function handleDelete(v) {
    if (!window.confirm(`Delete "${v.label}"? This removes the saved version for everyone and cannot be undone.`)) return
    await deletePlanVersion(v.id)
    setVersions(await loadPlanVersions())
  }

  async function handleRename(v) {
    const entered = window.prompt('Rename this plan version:', v.label)
    if (entered === null) return   // cancelled
    const label = entered.trim()
    if (!label || label === v.label) return
    await renamePlanVersion(v, label)
    setVersions(await loadPlanVersions())
  }

  const latest = versions[0]

  return (
    <div className="pl-root">
      <div className="pl-header">
        <span className="pl-eyebrow">Annual Operating Plan</span>
        <h1 className="pl-title">FY 2027–28 AOP Forecaster</h1>
        <p className="pl-sub">Forecast store × division sales for Mar'27 – Mar'28, review growth, and publish the Mar–Jun targets to the Buyer's Input Sheet.</p>
      </div>

      <div className="pl-tiles">
        <button className="pl-tile pl-tile--new" onClick={onNewPlan}>
          <span className="pl-tile-icon" aria-hidden>＋</span>
          <span className="pl-tile-body">
            <span className="pl-tile-title">New plan</span>
            <span className="pl-tile-desc">Build a fresh forecast from the database or uploaded inputs</span>
          </span>
          <span className="pl-tile-arrow" aria-hidden>→</span>
        </button>

        <button className="pl-tile pl-tile--saved" disabled={!latest} onClick={() => latest && onResume(latest.sessionId)}>
          <span className="pl-tile-icon" aria-hidden>↻</span>
          <span className="pl-tile-body">
            <span className="pl-tile-title">{latest ? 'Continue latest' : 'Continue'}</span>
            <span className="pl-tile-desc">{latest ? latest.label : loaded ? 'No saved plans yet' : 'Loading…'}</span>
          </span>
          {latest && <span className="pl-tile-arrow" aria-hidden>→</span>}
        </button>
      </div>

      {versions.length > 0 && (
        <section className="pl-log">
          <div className="pl-log-hd">
            <span>Saved plan versions</span>
            <span className="pl-log-count">{versions.length}</span>
          </div>
          {versions.map((v, idx) => {
            const pub = publishByLabel[v.label]
            const pubGrowth = pub?.lfl_growth_pct ?? pub?.growth_pct
            const avg = pubGrowth != null ? pubGrowth.toFixed(1) : _avgGrowth(v.fingerprint || {})
            const totalCr = pub?.total_mamj_lakhs ? (pub.total_mamj_lakhs / 100).toFixed(1) : null
            return (
              <div key={v.id} className="pl-log-row">
                <div className="pl-log-row-info">
                  <span className="pl-log-label">
                    {v.label}
                    {idx === 0 && <span className="pl-log-cur-badge">Latest</span>}
                  </span>
                  <span className="pl-log-meta">
                    {avg != null && (pubGrowth != null
                      ? <span className="pl-chip pl-chip--growth" title="Mar–Jun LfL growth of this version's publish: AOP target ÷ base − 1 (same as AOP Summary and BIS)">MAMJ growth {signed(avg)}%</span>
                      : <span className="pl-chip" title="Not published yet - simple average of the growth inputs saved with this version">Avg input {signed(avg)}%</span>)}
                    {totalCr && <span className="pl-chip" title="Published Mar–Jun target, MENS + LADIES + KIDS">₹{totalCr} Cr MAMJ</span>}
                    <span className="pl-log-date">{pub ? 'Published ' + fmtWhen(pub.published_at) : 'Saved ' + fmtWhen(v.lastModifiedAt)}</span>
                  </span>
                </div>
                <div className="pl-row-actions">
                  <button className="pl-load-btn" onClick={() => onResume(v.sessionId)}>Open</button>
                  <button className="pl-rename-btn" title="Rename this version" onClick={() => handleRename(v)}>Rename</button>
                  <button className="pl-del-btn" title="Delete this version" aria-label={`Delete ${v.label}`} onClick={() => handleDelete(v)}>✕</button>
                </div>
              </div>
            )
          })}
        </section>
      )}
    </div>
  )
}
