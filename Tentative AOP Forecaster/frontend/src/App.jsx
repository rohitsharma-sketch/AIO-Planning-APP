import { useState, useEffect, useRef } from 'react'
import UploadStep from './components/UploadStep'
import ReviewStep from './components/ReviewStep'
import ResultsDashboard from './components/ResultsDashboard'
import PlanningInputsEditor from './components/PlanningInputsEditor'
import PlanLanding, { loadPlanVersions, savePlanVersion, isMajorChangeVsLog } from './components/PlanLanding'
import { loadAutosave, useAutosave, clearAutosave, touchAutosaveIndex } from './lib/autosave'
import { apiUrl } from './lib/apiBase'
import ThemeSelector from './components/ThemeSelector'
import './App.css'
import './components/PlanLanding.css'

const STEPS = ['Configure', 'Review', 'Results']

const MONTHS   = ["Mar'27","Apr'27","May'27","Jun'27","Jul'27","Aug'27","Sep'27","Oct'27","Nov'27","Dec'27","Jan'28","Feb'28","Mar'28"]
const ALL_ROWS = ['GM','KIDS','LADIES','MENS','RETAIL','Overall']

function initRates(growth_rates) {
  const r = {}
  for (const row of ALL_ROWS) {
    r[row] = {}
    const src = row === 'Overall' ? 'GM' : row
    for (const m of MONTHS) r[row][m] = String(growth_rates?.[src]?.[m] ?? 0)
  }
  return r
}
function initLocks() {
  const l = {}
  for (const row of ALL_ROWS) { l[row] = {}; for (const m of MONTHS) l[row][m] = true }
  return l
}

export default function App() {
  const [step, setStep]           = useState(0)
  const [session, setSession]     = useState(null)
  const [results, setResults]     = useState(null)
  const [running, setRunning]     = useState(false)
  const [error, setError]         = useState(null)
  const [theme, setTheme]         = useState(() => localStorage.getItem('aop-theme') || 'classic')
  const [runKey, setRunKey]       = useState(0)
  const [showEditor, setShowEditor] = useState(false)

  // Landing page: shown initially and after reset; bypassed when a session auto-resumes
  const [showLanding, setShowLanding] = useState(true)
  // Save-before-leave dialog state
  const [saveDialog, setSaveDialog]   = useState(null) // {action, rates} | null

  // Lifted review state — survives step navigation
  const [rates,     setRates]     = useState(null)
  const [cellLocks, setCellLocks] = useState(null)
  const initedFor = useRef(null)  // tracks which session_id we've initialised for

  // Initialise once per session upload; never reinitialise on back navigation.
  // Restores an in-progress Review draft (rates + cell locks) if this browser
  // still has one for this exact session — e.g. after a reload.
  useEffect(() => {
    if (!session) return
    if (initedFor.current === session.session_id) return
    initedFor.current = session.session_id
    const draft = loadAutosave(`review:${session.session_id}`)
    if (draft?.rates && draft?.cellLocks) {
      setRates(draft.rates)
      setCellLocks(draft.cellLocks)
    } else {
      setRates(initRates(session.growth_rates))
      setCellLocks(initLocks())
    }
    touchAutosaveIndex('review:index', session.session_id, id => `review:${id}`)
  }, [session])

  // Keep the Review draft saved locally as the user edits, so it survives a reload.
  useAutosave(
    session ? `review:${session.session_id}` : null,
    { rates, cellLocks },
    { enabled: !!session && !!rates && !!cellLocks }
  )

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('aop-theme', theme)
  }, [theme])

  // Dev shortcut: ?session_id=xxx jumps to results (skips landing)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const sid = params.get('session_id')
    if (!sid) return
    fetch(apiUrl(`/api/results/${sid}`))
      .then(r => r.json())
      .then(data => { setSession({ session_id: sid }); setResults(data); setStep(2); setShowLanding(false) })
      .catch(() => {})
  }, [])

  // Resume the last active session across a plain reload (no ?session_id= needed).
  // Skipped when the URL already names a session — that takes priority.
  // Shows the landing page rather than silently auto-resuming so the user can
  // choose whether to continue or start fresh.
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get('session_id')) return
    // Leave showLanding = true; the landing "Continue" tile will offer to load it.
  }, [])

  // Remember which session/step is active so a reload can resume it (see effect above).
  useAutosave('currentSession', { session, step }, { enabled: !!session && step >= 1 })

  function adoptSession(data) {
    // New session → reset lifted state
    initedFor.current = null
    setRates(null)
    setCellLocks(null)
    setSession(data)
    setShowLanding(false)
    setStep(1)
  }

  // Start a session sourced entirely from Postgres (rs_planning) — no levers.json
  async function handleUseDb() {
    setError(null)
    const res = await fetch(apiUrl('/api/config/session-from-db'), { method: 'POST' })
    if (!res.ok) {
      const err = await res.json()
      throw new Error(typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail))
    }
    adoptSession(await res.json())
  }

  async function handleRun(palette = 'classic', includeDebug = false, growthOverrides = null, overallOverride = null) {
    setError(null)
    setRunning(true)
    try {
      const res = await fetch(apiUrl(`/api/run/${session.session_id}`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ palette, include_debug: includeDebug, growth_overrides: growthOverrides, overall_override: overallOverride }),
      })
      if (!res.ok) {
        const err = await res.json()
        const detail = err.detail
        const msg = Array.isArray(detail)
          ? detail.map(d => d.msg || JSON.stringify(d)).join('; ')
          : (typeof detail === 'string' ? detail : JSON.stringify(detail) || 'Engine error')
        throw new Error(msg)
      }
      const data = await res.json()
      setResults(data)
      setRunKey(k => k + 1)
      setStep(2)
      // Record this run in the plan version log (only if rates are ready)
      if (rates) savePlanVersion(session.session_id, rates, session.from_db ? 'db' : 'upload')
    } catch (e) {
      setError(e.message)
    } finally {
      setRunning(false)
    }
  }

  function handleDownload() {
    window.open(apiUrl(`/api/download/${session.session_id}`), '_blank')
  }

  function _doReset() {
    // Keep session files on the server — "← Plans" preserves them so "Load →"
    // on the version list can reload results without re-running the engine.
    // Sessions are temp files and will be cleaned up on server restart.
    clearAutosave('currentSession')
    initedFor.current = null
    setSession(null); setResults(null); setRates(null); setCellLocks(null)
    setStep(0); setError(null); setShowLanding(true)
  }

  function handleReset() {
    // If the user has made major changes since the last saved run, offer to save first
    if (rates && isMajorChangeVsLog(rates)) {
      setSaveDialog({ action: 'reset', rates })
    } else {
      _doReset()
    }
  }

  function handleSaveDialogSave() {
    const { rates: r } = saveDialog
    if (session && r) savePlanVersion(session.session_id, r, session.from_db ? 'db' : 'upload')
    setSaveDialog(null)
    _doReset()
  }
  function handleSaveDialogDiscard() { setSaveDialog(null); _doReset() }

  // Explicitly save current plan state as a version, then go to Results.
  // If no results yet (on Config step), runs the engine first.
  async function handleSaveVersion() {
    if (!session) return
    if (results) {
      // Already have results — just record the version and show Results
      if (rates) savePlanVersion(session.session_id, rates, session.from_db ? 'db' : 'upload')
      setStep(2)
    } else {
      // On Config step — save + run → Results
      if (rates) savePlanVersion(session.session_id, rates, session.from_db ? 'db' : 'upload')
      await handleRun()
    }
  }

  // Resume a saved plan version from the landing page — always lands on Results (step 3).
  // Priority chain:
  //   1. GET /api/results/{old_id}       — cached results still on server
  //   2. POST /api/run/{old_id}          — session files still exist, just re-run
  //   3. POST /api/config/session-from-db + run — server was restarted; create fresh session
  async function handleResumeSaved(sessionId) {
    if (!sessionId) return
    setError(null)
    setShowLanding(false)
    setRunning(true)
    try {
      // 1. Cached results?
      const r = await fetch(apiUrl(`/api/results/${sessionId}`))
      if (r.ok) {
        const data = await r.json()
        setSession({ session_id: sessionId, from_db: true })
        setResults(data)
        setStep(2)
        return
      }

      // 2. Re-run stale session
      const runRes = await fetch(apiUrl(`/api/run/${sessionId}`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ palette: 'classic' }),
      })
      if (runRes.ok) {
        const data = await runRes.json()
        setSession({ session_id: sessionId, from_db: true })
        setResults(data)
        setRunKey(k => k + 1)
        setStep(2)
        return
      }

      // 3. Server restarted — create a fresh DB session and run it
      const sessionRes = await fetch(apiUrl('/api/config/session-from-db'), { method: 'POST' })
      if (!sessionRes.ok) {
        const err = await sessionRes.json()
        throw new Error(typeof err.detail === 'string' ? err.detail : 'Could not create session from DB')
      }
      const newSession = await sessionRes.json()
      const freshRun = await fetch(apiUrl(`/api/run/${newSession.session_id}`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ palette: 'classic' }),
      })
      if (!freshRun.ok) {
        const err = await freshRun.json()
        throw new Error(typeof err.detail === 'string' ? err.detail : 'Engine run failed')
      }
      const data = await freshRun.json()
      // Update version log so future loads use the fresh session_id
      if (rates) savePlanVersion(newSession.session_id, rates, 'db')
      setSession({ ...newSession })
      setResults(data)
      setRunKey(k => k + 1)
      setStep(2)
    } catch (e) {
      setError(`Could not load saved plan: ${e.message}`)
      setShowLanding(true)
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="header-inner">
          <div className="logo">
            <span className="logo-mark">A</span>
            <span className="logo-text">AOP Forecaster</span>
          </div>
          {!showLanding && (
            <nav className="stepper">
              {STEPS.map((s, i) => (
                <div key={s} className={`step-item ${i === step ? 'active' : ''} ${i < step ? 'done' : ''}`}>
                  <span className="step-num">{i < step ? 'OK' : i + 1}</span>
                  <span className="step-label">{s}</span>
                  {i < STEPS.length - 1 && <span className="step-sep" />}
                </div>
              ))}
            </nav>
          )}
          <div style={{display:'flex', alignItems:'center', gap:8, flexShrink:0}}>
            {!showLanding && session && (
              <button
                className="btn-outline"
                onClick={handleSaveVersion}
                disabled={running}
                style={{fontSize:12, display:'flex', alignItems:'center', gap:4}}
                title="Save this plan as a version and go to Results"
              >
                💾 Save
              </button>
            )}
            {!showLanding && (
              <button className="btn-outline" onClick={handleReset} style={{fontSize:12}}>
                ← Plans
              </button>
            )}
            <ThemeSelector current={theme} onChange={setTheme} />
          </div>
        </div>
      </header>

      <main className="app-main">
        {error && (
          <div className="error-banner">
            <strong>Error:</strong> {error}
            <button onClick={() => setError(null)} style={{marginLeft:12,background:'none',color:'inherit',border:'none',cursor:'pointer',fontSize:16}}>×</button>
          </div>
        )}

        {/* ── LANDING PAGE ── */}
        {showLanding && (
          <PlanLanding
            onNewPlan={() => { setShowLanding(false); setStep(0) }}
            onResume={handleResumeSaved}
          />
        )}

        {!showLanding && step === 0 && (showEditor
          ? <PlanningInputsEditor onBack={() => setShowEditor(false)} onContinue={handleUseDb} />
          : <UploadStep onUseDb={handleUseDb} onEditInputs={() => setShowEditor(true)} />
        )}

        {!showLanding && step === 1 && session && rates && (
          <ReviewStep
            session={session}
            running={running}
            onRun={handleRun}
            rates={rates}
            setRates={setRates}
            cellLocks={cellLocks}
            setCellLocks={setCellLocks}
            onBack={results ? () => setStep(2) : null}
          />
        )}

        {/* Keep ResultsDashboard mounted once results exist so OutputTab filter state
            survives the Results→Review→Results round-trip. Hidden via CSS, not unmounted. */}
        {results && (
          <div style={{ display: (!showLanding && step === 2) ? '' : 'none' }}>
            <ResultsDashboard
              results={results}
              session={session}
              runKey={runKey}
              onDownload={handleDownload}
              onRunAgain={() => setStep(1)}
            />
          </div>
        )}
      </main>

      {/* ── SAVE-BEFORE-LEAVE DIALOG ── */}
      {saveDialog && (
        <div className="pl-save-dialog-backdrop" onClick={() => setSaveDialog(null)}>
          <div className="pl-save-dialog" onClick={e => e.stopPropagation()}>
            <h3>Save changes?</h3>
            <p>
              You've made significant changes to this plan since the last saved version.
              Would you like to save them as a new version before leaving?
            </p>
            <div className="pl-save-dialog-btns">
              <button onClick={handleSaveDialogDiscard}>Don't save</button>
              <button className="pl-btn-save" onClick={handleSaveDialogSave}>Save new version</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
