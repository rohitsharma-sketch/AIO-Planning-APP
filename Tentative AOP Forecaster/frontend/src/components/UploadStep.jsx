import { useState } from 'react'
import DbSyncPanel from './DbSyncPanel'
import './UploadStep.css'

const THEMES = [
  { id: 'indigo',  label: 'Indigo',    primary: '#312E81', accent: '#4F46E5' },
  { id: 'classic', label: 'Classic',   primary: '#1F3864', accent: '#4472C4' },
  { id: 'emerald', label: 'Emerald',   primary: '#1E293B', accent: '#10B981' },
  { id: 'amber',   label: 'Amber',     primary: '#0F172A', accent: '#F59E0B' },
  { id: 'coral',   label: 'Coral',     primary: '#3B1F6A', accent: '#F4845F' },
  { id: 'forest',  label: 'Forest',    primary: '#14532D', accent: '#22C55E' },
]

export default function UploadStep({ onUseDb, onEditInputs, theme, onThemeChange }) {
  const [err, setErr]       = useState(null)
  const [dbBusy, setDbBusy] = useState(false)

  async function useDb() {
    setDbBusy(true); setErr(null)
    try { await onUseDb() } catch (e) { setErr(e.message) } finally { setDbBusy(false) }
  }

  return (
    <div className="us-wrap">

      {/* ── Hero banner ───────────────────────────────── */}
      <div className="us-hero">
        <div className="us-hero-left">
          <div className="us-hero-badge">FY 2027</div>
          <h1 className="us-hero-title">AOP Forecaster</h1>
          <p className="us-hero-sub">
            Annual Operating Plan · Build the store-level revenue forecast from synced actuals and growth levers.
          </p>
        </div>
        <div className="us-hero-art">
          <div className="us-hero-ring us-ring-1" />
          <div className="us-hero-ring us-ring-2" />
          <div className="us-hero-icon-wrap">
            <span className="us-hero-icon-letter">A</span>
          </div>
        </div>
      </div>

      {/* ── Action cards ──────────────────────────────── */}
      <div className="us-cards">
        <button className="us-card us-card-primary" onClick={useDb} disabled={dbBusy}>
          <div className="us-card-header">
            <span className="us-card-chip">Recommended</span>
          </div>
          <div className="us-card-icon">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14c0 1.66 4.03 3 9 3s9-1.34 9-3V5"/>
              <path d="M3 12c0 1.66 4.03 3 9 3s9-1.34 9-3"/>
            </svg>
          </div>
          <div className="us-card-body">
            <div className="us-card-title">
              {dbBusy ? 'Building forecast…' : 'Continue from Database'}
            </div>
            <div className="us-card-desc">
              Load store counts, actuals, and growth rates from the synced data lake. Ready in seconds.
            </div>
          </div>
          <div className="us-card-footer">
            <span className="us-card-cta">Get started →</span>
          </div>
        </button>

        <button className="us-card us-card-secondary" onClick={onEditInputs}>
          <div className="us-card-header">
            <span className="us-card-chip us-chip-outline">Advanced</span>
          </div>
          <div className="us-card-icon">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>
            </svg>
          </div>
          <div className="us-card-body">
            <div className="us-card-title">Edit Growth % / NSO / AOP</div>
            <div className="us-card-desc">
              Adjust growth rates, ramp schedules, and AOP overrides before generating the plan.
            </div>
          </div>
          <div className="us-card-footer">
            <span className="us-card-cta">Open editor →</span>
          </div>
        </button>
      </div>

      {err && <p className="us-err">{err}</p>}

      {/* ── Sync status ───────────────────────────────── */}
      <div className="us-sync-section">
        <div className="us-sync-label">Data Sources</div>
        <DbSyncPanel onSynced={useDb} />
      </div>

      {/* ── Appearance ────────────────────────────────── */}
      {onThemeChange && (
        <div className="pl-theme-section">
          <span className="pl-theme-label">Appearance</span>
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

    </div>
  )
}
