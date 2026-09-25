// v2026.09.03
import { useState, useEffect, useRef } from 'react'
import UploadStep from './components/UploadStep'
import ReviewStep from './components/ReviewStep'
import ResultsDashboard from './components/ResultsDashboard'
import PlanningInputsEditor from './components/PlanningInputsEditor'
import PlanLanding, { loadPlanVersions, savePlanVersion, isMajorChangeVsLog } from './components/PlanLanding'
import { loadAutosave, useAutosave, clearAutosave, touchAutosaveIndex } from './lib/autosave'
import { apiUrl } from './lib/apiBase'
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
// Layer a saved run's growth inputs (GET /api/session -> last_run) over the
// session defaults, so reopening a saved version shows what it was run with.
function applyLastRun(r, lastRun) {
  for (const [div, months] of Object.entries(lastRun?.growth_overrides || {}))
    for (const [m, v] of Object.entries(months || {})) if (r[div]) r[div][m] = String(v)
  for (const [m, v] of Object.entries(lastRun?.overall_override || {})) r.Overall[m] = String(v)
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
  const [runKey, setRunKey]       = useState(0)
  const [showEditor, setShowEditor] = useState(false)

  // Landing page: shown initially and after reset; bypassed when a session auto-resumes
  const [showLanding, setShowLanding] = useState(true)
  const [saveMsg, setSaveMsg]         = useState(null)  // {text, ok} | null
  const [inputsNote, setInputsNote]   = useState(null)  // resumed version whose run inputs weren't recorded
  // Save-before-leave dialog state
  const [saveDialog, setSaveDialog]   = useState(null) // {action, rates} | null

  // Lifted review state — survives step navigation
  const [rates,     setRates]     = useState(null)
  const [cellLocks, setCellLocks] = useState(null)
  const initedFor = useRef(null)  // tracks which session_id we've initialised for

  // When this session/plan was last (re)built from the DB — compared against
  // Planning Inputs' "last saved" marker (see below) to detect a stale plan.
  const [sessionBuiltAt, setSessionBuiltAt] = useState(null)
  const [rebuilding, setRebuilding] = useState(false)

  // Initialise once per session upload; never reinitialise on back navigation.
  // Restores an in-progress Review draft (rates + cell locks) if this browser
  // still has one for this exact session — e.g. after a reload.
  useEffect(() => {
    if (!session) return
    if (initedFor.current === session.session_id) return
    initedFor.current = session.session_id
    // 'review2:' - drafts saved before 2026-09-25 could hold the 0% grid a
    // reopened version used to get; a new key drops them instead of trusting them.
    const draft = loadAutosave(`review2:${session.session_id}`)
    if (draft?.rates && draft?.cellLocks) {
      setRates(draft.rates)
      setCellLocks(draft.cellLocks)
    } else {
      setRates(applyLastRun(initRates(session.growth_rates), session.last_run))
      setCellLocks(initLocks())
    }
    touchAutosaveIndex('review2:index', session.session_id, id => `review2:${id}`)
  }, [session])

  // Keep the Review draft saved locally as the user edits, so it survives a reload.
  useAutosave(
    session ? `review2:${session.session_id}` : null,
    { rates, cellLocks },
    { enabled: !!session && !!rates && !!cellLocks }
  )

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
    setSessionBuiltAt(Date.now())
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
      if (rates) await savePlanVersion(session.session_id, rates, session.from_db ? 'db' : 'upload')
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
    setInputsNote(null)
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

  async function handleSaveDialogSave() {
    const { rates: r } = saveDialog
    if (session && r) await savePlanVersion(session.session_id, r, session.from_db ? 'db' : 'upload')
    setSaveDialog(null)
    _doReset()
  }
  function handleSaveDialogDiscard() { setSaveDialog(null); _doReset() }

  // Explicitly save current plan state as a version, then go to Results.
  // If no results yet (on Config step), runs the engine first.
  async function handleSaveVersion() {
    if (!session) return
    let savedLabel = null
    if (rates) {
      try {
        const isMajor = await savePlanVersion(session.session_id, rates, session.from_db ? 'db' : 'upload')
        const versions = await loadPlanVersions()
        savedLabel = versions[0]?.label || 'Plan saved'
        setSaveMsg({ text: `✓ ${savedLabel}`, ok: true })
        setTimeout(() => setSaveMsg(null), 3000)
      } catch {
        setSaveMsg({ text: 'Save failed — check console', ok: false })
        setTimeout(() => setSaveMsg(null), 4000)
      }
    }
    if (results) {
      setStep(2)
    } else {
      await handleRun()
    }
  }

  // Resume a saved plan version from the landing page — always lands on Results (step 3).
  // Always creates a FRESH session from the current DB so base values reflect
  // clean actuals regardless of when the original session was created. Old
  // session files are intentionally bypassed because their inputs.xlsx was
  // snapshotted at creation time and may contain stale actuals.
  // FIXED 2026-09-22: this used to ignore sessionId entirely (it was even
  // named `_sessionId`, the JS convention for "deliberately unused"),
  // building a BRAND NEW session from current DB data and re-running with
  // NO growth_overrides - silently using inputs.xlsx's flat 6% default
  // instead of whatever rates the saved version actually used, then
  // re-pointing that version's own sessionId at this wrong new session.
  // "Load" on a saved version must show EXACTLY what was saved, not a
  // fresh 6%-default re-run wearing that version's label - reading the
  // session's own already-cached results (same GET the ?session_id= dev
  // shortcut above already uses) does that with no re-run and no risk of
  // silently overwriting the version's real data.
  async function handleResumeSaved(sessionId) {
    setError(null)
    setShowLanding(false)
    setRunning(true)
    try {
      const res = await fetch(apiUrl(`/api/results/${sessionId}`))
      if (!res.ok) {
        throw new Error('This saved plan\'s session data is no longer available - it may need to be re-run from Planning Inputs.')
      }
      const data = await res.json()
      // Full session (store counts, default growth, last run's inputs) so
      // Review isn't blank / 0% after opening a saved version (2026-09-25).
      let info = await fetch(apiUrl(`/api/session/${sessionId}`)).then(r => (r.ok ? r.json() : null)).catch(() => null)
      let note = info?.last_run?.derived
        ? "This version was run before its growth inputs were recorded, so they were recovered from its saved forecast. Check them before running again."
        : null
      if (info && !info.last_run) {
        // Run before its inputs were recorded: its saved version still holds
        // the Mar-Jun MENS/LADIES/KIDS growth (fingerprint "DIV|Mon'YY").
        const ver = (await loadPlanVersions()).find(v => v.sessionId === sessionId)
        const go = {}
        for (const [k, val] of Object.entries(ver?.fingerprint || {})) {
          const [div, m] = k.split('|')
          ;(go[div] ??= {})[m] = val
        }
        if (Object.keys(go).length) info = { ...info, last_run: { growth_overrides: go, overall_override: null } }
        note = Object.keys(go).length
          ? "Restored this version's Mar–Jun MENS / LADIES / KIDS growth from its saved record. It was run before full inputs were recorded, so other cells show the Planning Inputs defaults — run and save it once to keep all of them."
          : 'This version was run before its growth inputs were recorded, so Review shows the Planning Inputs defaults. Run and save it once to keep its inputs.'
      }
      setSession(info || { session_id: sessionId })
      setInputsNote(note)
      setSessionBuiltAt(Date.now())
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

  // Planning Inputs Editor (Store Master / Ref Store Mapping / AOP Overrides /
  // NSO tabs) stamps `aop-config-changed-at` in localStorage on every successful
  // save. If that's newer than when this session's data was last built from the
  // DB, the open plan is stale — e.g. a store's ref_store changed after this
  // plan was generated, so its forecast is still shaped by the OLD ref store's
  // pattern. Detected only while looking at Review/Results (not mid-edit on
  // Configure) and auto-rebuilt below — see the effect right after handleRebuild.
  const configChangedAt = Number(localStorage.getItem('aop-config-changed-at') || 0)
  const planIsStale = sessionBuiltAt && configChangedAt > sessionBuiltAt && (step === 1 || step === 2)

  // Rebuild the session fresh from the DB (picks up any Planning Inputs edit,
  // ref_store included) and re-run the forecast with it.
  async function handleRebuild() {
    setRebuilding(true)
    try {
      await handleUseDb()   // fresh session from current DB → adoptSession() → step 1
      await handleRun()     // re-forecast on the fresh session → step 2
    } catch (e) {
      setError(e.message)
    } finally {
      setRebuilding(false)
    }
  }

  // Auto-rebuild: the instant a stale plan is showing (Planning Inputs saved
  // something after this session was built), rebuild it with no click needed.
  // sessionBuiltAt updates synchronously inside handleRebuild → adoptSession(),
  // so planIsStale flips false before this can re-fire — self-limiting, no loop.
  useEffect(() => {
    if (planIsStale && !rebuilding) handleRebuild()
  }, [planIsStale, rebuilding])

  return (
    <div className="app-shell">
      {/* Shown on 8010 too (2026-09-25): the platform shell has no in-app
          navigation, so hiding this left the steps, Save and Plans unreachable. */}
      <header className="app-header">
        <div className="header-inner">
          <button className="logo" onClick={showLanding ? undefined : handleReset} title={showLanding ? undefined : 'Back to saved plans'}>
            <span className="logo-mark">AOP</span>
            <span className="logo-words">
              <span className="logo-text">AOP Forecaster</span>
              <span className="logo-sub">CityKart RS Planning · FY 2027–28</span>
            </span>
          </button>
          {!showLanding && (
            <nav className="stepper">
              {STEPS.map((s, i) => {
                // A step is reachable — from anywhere, not just by walking
                // forward one at a time — once its data already exists, so
                // going back (manual clicks) never forces a walk back through
                // every screen to get forward again.
                const reachable = i === 0 || (i === 1 && session && rates) || (i === 2 && !!results)
                const clickable = reachable && i !== step
                return (
                  <div
                    key={s}
                    className={`step-item ${i === step ? 'active' : ''} ${i < step ? 'done' : ''} ${clickable ? 'clickable' : ''}`}
                    onClick={clickable ? () => setStep(i) : undefined}
                    role={clickable ? 'button' : undefined}
                    tabIndex={clickable ? 0 : undefined}
                    title={clickable ? `Go to ${s}` : undefined}
                  >
                    <span className="step-num">{i < step ? '✓' : i + 1}</span>
                    <span className="step-label">{s}</span>
                    {i < STEPS.length - 1 && <span className="step-sep" />}
                  </div>
                )
              })}
            </nav>
          )}
          <div className="hdr-actions">
            {saveMsg && <span className={`hdr-msg ${saveMsg.ok ? 'ok' : 'err'}`}>{saveMsg.text}</span>}
            {!showLanding && (
              <button className="hdr-btn" onClick={handleReset} title="Back to the saved plans list">
                ← Plans
              </button>
            )}
            {!showLanding && session && (
              <button
                className="hdr-btn hdr-btn--primary"
                onClick={handleSaveVersion}
                disabled={running}
                title="Save this plan as a version and go to Results"
              >
                Save version
              </button>
            )}
          </div>
        </div>
      </header>

      <main className="app-main">
        {error && (
          <div className="error-banner" role="alert">
            <strong>Error:</strong> {error}
            <button className="banner-x" onClick={() => setError(null)} aria-label="Dismiss">×</button>
          </div>
        )}

        {inputsNote && !showLanding && step === 1 && (
          <div className="info-banner">
            {inputsNote}
            <button className="banner-x" onClick={() => setInputsNote(null)} aria-label="Dismiss">×</button>
          </div>
        )}

        {rebuilding && (
          <div className="info-banner">
            Planning Inputs changed since this plan was built — rebuilding automatically with the current data…
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
            onGoToConfig={() => setStep(0)}
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
