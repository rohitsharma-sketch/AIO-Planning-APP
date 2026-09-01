import { useState, useEffect, useRef } from 'react'
import UploadStep from './components/UploadStep'
import ReviewStep from './components/ReviewStep'
import ResultsDashboard from './components/ResultsDashboard'
import PlanningInputsEditor from './components/PlanningInputsEditor'
import { loadAutosave, useAutosave, clearAutosave, touchAutosaveIndex } from './lib/autosave'
import { apiUrl } from './lib/apiBase'
import ThemeSelector from './components/ThemeSelector'
import './App.css'

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

  // Dev shortcut: ?session_id=xxx jumps to results
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const sid = params.get('session_id')
    if (!sid) return
    fetch(apiUrl(`/api/results/${sid}`))
      .then(r => r.json())
      .then(data => { setSession({ session_id: sid }); setResults(data); setStep(2) })
      .catch(() => {})
  }, [])

  // Resume the last active session across a plain reload (no ?session_id= needed).
  // Skipped when the URL already names a session — that takes priority.
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get('session_id')) return
    const saved = loadAutosave('currentSession')
    if (!saved?.session?.session_id || !saved.step) return
    if (saved.step === 2) {
      fetch(apiUrl(`/api/results/${saved.session.session_id}`))
        .then(r => r.ok ? r.json() : Promise.reject())
        .then(data => { setSession(saved.session); setResults(data); setStep(2) })
        .catch(() => { setSession(saved.session); setStep(1) })   // run output gone — the inputs may still be fine, drop back to Review
    } else {
      setSession(saved.session); setStep(1)
    }
  }, [])

  // Remember which session/step is active so a reload can resume it (see effect above).
  useAutosave('currentSession', { session, step }, { enabled: !!session && step >= 1 })

  function adoptSession(data) {
    // New session → reset lifted state
    initedFor.current = null
    setRates(null)
    setCellLocks(null)
    setSession(data)
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
    } catch (e) {
      setError(e.message)
    } finally {
      setRunning(false)
    }
  }

  function handleDownload() {
    window.open(apiUrl(`/api/download/${session.session_id}`), '_blank')
  }

  function handleReset() {
    if (session) {
      fetch(apiUrl(`/api/sessions/${session.session_id}`), { method: 'DELETE' })
      clearAutosave(`review:${session.session_id}`)
    }
    clearAutosave('currentSession')
    initedFor.current = null
    setSession(null); setResults(null); setRates(null); setCellLocks(null)
    setStep(0); setError(null)
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="header-inner">
          <div className="logo">
            <span className="logo-mark">A</span>
            <span className="logo-text">AOP Forecaster</span>
          </div>
          <nav className="stepper">
            {STEPS.map((s, i) => (
              <div key={s} className={`step-item ${i === step ? 'active' : ''} ${i < step ? 'done' : ''}`}>
                <span className="step-num">{i < step ? 'OK' : i + 1}</span>
                <span className="step-label">{s}</span>
                {i < STEPS.length - 1 && <span className="step-sep" />}
              </div>
            ))}
          </nav>
          <div style={{display:'flex', alignItems:'center', gap:8, flexShrink:0}}>
            {step > 0 && (
              <button className="btn-outline" onClick={handleReset} style={{fontSize:12}}>
                New forecast
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

        {step === 0 && (showEditor
          ? <PlanningInputsEditor onBack={() => setShowEditor(false)} onContinue={handleUseDb} />
          : <UploadStep onUseDb={handleUseDb} onEditInputs={() => setShowEditor(true)} />
        )}

        {step === 1 && session && rates && (
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
          <div style={{ display: step === 2 ? '' : 'none' }}>
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
    </div>
  )
}
