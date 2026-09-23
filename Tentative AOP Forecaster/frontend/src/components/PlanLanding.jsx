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

const THEMES = [
  { id: 'indigo',  label: 'Indigo',    primary: '#312E81', accent: '#4F46E5' },
  { id: 'classic', label: 'Classic',   primary: '#1F3864', accent: '#4472C4' },
  { id: 'emerald', label: 'Emerald',   primary: '#1E293B', accent: '#10B981' },
  { id: 'amber',   label: 'Amber',     primary: '#0F172A', accent: '#F59E0B' },
  { id: 'coral',   label: 'Coral',     primary: '#3B1F6A', accent: '#F4845F' },
  { id: 'forest',  label: 'Forest',    primary: '#14532D', accent: '#D97706' },
]

export default function PlanLanding({ onNewPlan, onResume, theme, onThemeChange }) {
  const [showSaved, setShowSaved] = useState(false)
  const [versionList, setVersionList] = useState([])
  const versions = versionList

  useEffect(() => {
    loadPlanVersions().then(v => setVersionList(v))
  }, [])

  async function handleDelete(id) {
    await deletePlanVersion(id)
    const updated = await loadPlanVersions()
    setVersionList(updated)
    if (updated.length === 0) setShowSaved(false)
  }

  async function handleRename(v) {
    const entered = window.prompt('Rename this plan version:', v.label)
    if (entered === null) return   // cancelled
    const label = entered.trim()
    if (!label || label === v.label) return
    await renamePlanVersion(v, label)
    setVersionList(await loadPlanVersions())
  }

  return (
    <div className="pl-root">
      <div className="pl-header">
        <h1 className="pl-title">AOP Forecaster</h1>
        <p className="pl-sub">FY 2027–28 Annual Operating Plan</p>
      </div>

      <div className={`pl-tiles ${showSaved ? 'pl-tiles--open' : ''}`}>

        {/* ── NEW PLAN TILE ── */}
        <div className="pl-tile pl-tile--new" onClick={() => { setShowSaved(false); onNewPlan() }}>
          <div className="pl-tile-icon">＋</div>
          <div className="pl-tile-body">
            <div className="pl-tile-title">New Plan</div>
            <div className="pl-tile-desc">Start fresh — upload inputs or load from database</div>
          </div>
          <span className="pl-tile-arrow">→</span>
        </div>

        {/* ── EXISTING PLAN TILE ── */}
        <div className={`pl-tile pl-tile--saved ${versions.length === 0 ? 'pl-tile--empty' : ''}`}
             onClick={() => versions.length > 0 && setShowSaved(s => !s)}>
          <div className="pl-tile-icon">📋</div>
          <div className="pl-tile-body">
            <div className="pl-tile-title">Continue with saved</div>
            <div className="pl-tile-desc">
              {versions.length === 0
                ? 'No saved plans yet'
                : `${versions.length} saved plan${versions.length > 1 ? 's' : ''}`}
            </div>
          </div>
          {versions.length > 0 && <span className="pl-tile-arrow">{showSaved ? '↑' : '↓'}</span>}
        </div>
      </div>

      {/* ── THEME PICKER ── */}
      {onThemeChange && (
        <div className="pl-theme-section">
          <div className="pl-theme-label">Appearance</div>
          <div className="pl-theme-swatches">
            {THEMES.map(t => (
              <button
                key={t.id}
                className={`pl-theme-swatch ${t.id === theme ? 'active' : ''}`}
                title={t.label}
                onClick={() => onThemeChange(t.id)}
                style={{ '--sw-primary': t.primary, '--sw-accent': t.accent }}
              >
                <span className="pl-sw-1" />
                <span className="pl-sw-2" />
              </button>
            ))}
          </div>
        </div>
      )}

      {/* ── VERSION LOG ── */}
      {showSaved && versions.length > 0 && (
        <div className="pl-log">
          <div className="pl-log-hd">Saved plan versions</div>
          {versions.map((v, idx) => {
            const avg = _avgGrowth(v.fingerprint || {})
            const date = new Date(v.lastModifiedAt).toLocaleString('en-IN', {
              day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit'
            })
            return (
              <div key={v.id} className="pl-log-row">
                <div className="pl-log-row-info">
                  <span className="pl-log-label">{v.label}</span>
                  <span className="pl-log-meta">
                    {idx === 0 && <span className="pl-log-cur-badge">Current</span>}
                    {avg != null && <span>Avg MAMJ growth: {avg > 0 ? '+' : ''}{avg}%</span>}
                    <span className="pl-log-date">{date}</span>
                  </span>
                </div>
                <div className="pl-row-actions">
                  <button className="pl-load-btn" onClick={() => onResume(v.sessionId)}>
                    Load →
                  </button>
                  <button
                    className="pl-rename-btn"
                    title="Rename this version"
                    onClick={e => { e.stopPropagation(); handleRename(v) }}
                  >
                    Rename
                  </button>
                  <button
                    className="pl-del-btn"
                    title="Delete this version"
                    onClick={e => { e.stopPropagation(); handleDelete(v.id) }}
                  >
                    ✕
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
