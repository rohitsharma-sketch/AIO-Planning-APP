import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { theme, alpha } from '../theme'
import GrainPanel from '../components/GrainPanel'
import BisCompare from '../components/BisCompare'
import { ENGINE_META, startPipeline } from '../pipelineState'
import ExcelFilter, { FilterButton } from '../components/ExcelFilter'
import { useGrain } from '../grain'

const DIVISIONS = ['KIDS', 'LADIES', 'MENS']   // GM / RETAIL out of the Sales Plan engine (user, 2026-10-13)

const DIV_COLOR = {
  KIDS: '#C85A12', LADIES: '#7420B8', MENS: '#077A4A', GM: '#1E54C0', RETAIL: '#B22620',
}

const ATTR_STYLE = {
  'REGULAR':    { bg: '#EEF1FD', color: '#4338CA' },
  'SUMMER':     { bg: '#FFF4E8', color: '#C2410C' },
  'PREWINTER':  { bg: '#ECFDF3', color: '#15803D' },
  'LT WINTER':  { bg: '#EFF6FF', color: '#1D4ED8' },
  'HVY WINTER': { bg: '#EFF6FF', color: '#2563EB' },
  'OCCASIONAL': { bg: '#F5EEFD', color: '#7E22CE' },
}

function cellBg(val) {
  const v = parseFloat(val)
  if (isNaN(v) || v === 100) return 'transparent'
  if (v > 100) return `rgba(0,168,107,${Math.min((v - 100) / 30, 1) * 0.18 + 0.05})`
  return `rgba(217,79,61,${Math.min((100 - v) / 30, 1) * 0.18 + 0.05})`
}

function cellColor(val) {
  const v = parseFloat(val)
  if (isNaN(v) || v === 100) return theme.textPrimary
  return v > 100 ? '#15803D' : '#B42318'
}

function buildMonthGroups(periods) {
  const groups = []
  for (let i = 0; i < periods.length; i += 2) {
    const label = periods[i].replace(' P1', '')
    groups.push({ label, p1: periods[i], p2: periods[i + 1] })
  }
  return groups
}

export default function DepartmentGrowthMatrix() {
  const [activeDiv, setActiveDiv]     = useState('KIDS')
  const [data, setData]               = useState(null)
  const [loading, setLoading]         = useState(true)
  // Excel-style column filters (user, 2026-10-13: "add the same Excel filters to the Growth Matrix page"):
  // {column: [values]} - department, attribute or a period (its growth index); cleared when the division changes
  const [xf, setXf]                   = useState({})
  const [xfEdit, setXfEdit]           = useState(null)   // {col, title, anchor} - the list open now
  const [xs, setXs]                   = useState(null)   // {col, dir: 'az' | 'za'} - Excel's Sort, one column at a time
  useEffect(() => { setXf({}); setXfEdit(null); setXs(null) }, [activeDiv])
  const [activeMonths, setActiveMonths] = useState(new Set())
  const [saving, setSaving]           = useState(false)
  const [lastSaved, setLastSaved]     = useState(null)
  const [generating, setGenerating]   = useState(false)
  const [genMsg, setGenMsg]           = useState('')
  const [showPipelineModal, setShowPipelineModal] = useState(false)
  const [pipelineChecked, setPipelineChecked] = useState({ 'attr-correction': false, 'base-correction': false })
  const [grain] = useGrain()
  const corrOff = grain === 'cluster'   // Attr / Base Correction are store-level: off in Cluster view (2026-10-12)
  const [genStores, setGenStores] = useState(null)
  const navigate = useNavigate()

  // Buyer upload state
  const [showUpload, setShowUpload]     = useState(false)
  const [uploadFile, setUploadFile]     = useState(null)
  const [uploading, setUploading]       = useState(false)
  const [uploadResult, setUploadResult] = useState(null)
  const [buyerMeta, setBuyerMeta]       = useState({})

  // Buyer sync state
  const [buyerSyncing, setBuyerSyncing] = useState(false)
  const [buyerSyncResult, setBuyerSyncResult] = useState(null)
  const fileInputRef = useRef(null)

  const pendingRef  = useRef({})
  const debounceRef = useRef(null)

  const fetchMatrix = useCallback(async (div) => {
    setLoading(true)
    try {
      const r = await fetch(`/api/planning/department-plan/growth-matrix/${div}`)
      const d = await r.json()
      setData(d)
    } finally {
      setLoading(false)
    }
  }, [])

  const fetchBuyerMeta = useCallback(async () => {
    const r = await fetch('/api/planning/department-plan/buyer-upload-meta')
    const d = await r.json()
    setBuyerMeta(d)
  }, [])

  useEffect(() => {
    pendingRef.current = {}
    fetchMatrix(activeDiv)
  }, [activeDiv, fetchMatrix])

  useEffect(() => { fetchBuyerMeta() }, [fetchBuyerMeta])

  useEffect(() => {
    fetch('/api/planning/dept-sales/actuals/status')
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (d?.available_ty_months?.length) {
          setActiveMonths(new Set(d.available_ty_months))
        }
      })
      .catch(() => {})
  }, [])

  const handleChange = (deptName, period, val) => {
    setData(prev => {
      if (!prev) return prev
      return {
        ...prev,
        departments: prev.departments.map(d =>
          d.name === deptName
            ? { ...d, periods: { ...d.periods, [period]: val === '' ? '' : parseFloat(val) || 100 } }
            : d
        ),
      }
    })
    pendingRef.current[deptName] = pendingRef.current[deptName] || {}
    pendingRef.current[deptName][period] = val === '' ? 100 : parseFloat(val) || 100

    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(async () => {
      const batch = { ...pendingRef.current }
      pendingRef.current = {}
      setSaving(true)
      await fetch('/api/planning/department-plan/growth-matrix', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ division: activeDiv, updates: batch }),
      })
      setSaving(false)
      setLastSaved(new Date().toLocaleTimeString())
    }, 800)
  }

  const handleGenerateBase = async () => {
    setGenerating(true); setGenMsg('')
    try {
      const r = await fetch('/api/planning/dept-sales/generate-base', { method: 'POST' })
      const d = await r.json()
      if (d.ok) {
        setGenMsg(`✓ ${d.stores} stores`)
        setGenStores(d.stores)
        setShowPipelineModal(true)
      } else {
        setGenMsg('Error generating plan')
      }
    } catch {
      setGenMsg('Network error')
    } finally {
      setGenerating(false)
    }
  }

  const handleStartPipeline = (only) => {
    // engines run in the pipeline's own order (Attr -> Base); `only` runs just that one. New departments come from
    // BIS (BIS > New departments) and are already in the base plan (user, 2026-10-12)
    const queue = corrOff ? [] : only ? [only] : Object.keys(ENGINE_META).filter(k => pipelineChecked[k])
    if (queue.length === 0) {
      navigate('/department-plan/final-results')
      return
    }
    startPipeline(queue)
    navigate(ENGINE_META[queue[0]].route)
  }

  const handleReset = async () => {
    // danger action (user, 2026-10-07: "add confirm to both")
    if (!window.confirm(`Reset every ${activeDiv} department's growth to 100 (LY)? Your edits in this division will be lost.`)) return
    setSaving(true)
    await fetch('/api/planning/department-plan/growth-matrix/reset', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ division: activeDiv }),
    })
    setSaving(false)
    fetchMatrix(activeDiv)
  }

  const handleFillColumn = (period) => {
    const val = parseFloat(prompt(`Set all depts to % for ${period}:`, '100'))
    if (isNaN(val)) return
    setData(prev => ({
      ...prev,
      departments: prev.departments.map(d => d.active === false ? d : ({   // inactive departments are left as they are
        ...d,
        periods: { ...d.periods, [period]: val },
      })),
    }))
    const batch = {}
    data?.departments.forEach(d => { if (d.active !== false) batch[d.name] = { [period]: val } })
    pendingRef.current = deepMerge(pendingRef.current, batch)
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(async () => {
      const b = { ...pendingRef.current }; pendingRef.current = {}
      setSaving(true)
      await fetch('/api/planning/department-plan/growth-matrix', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ division: activeDiv, updates: b }),
      })
      setSaving(false)
      setLastSaved(new Date().toLocaleTimeString())
    }, 100)
  }

  const handleUpload = async () => {
    if (!uploadFile) return
    setUploading(true)
    setUploadResult(null)
    const form = new FormData()
    form.append('file', uploadFile)
    form.append('division', activeDiv)
    try {
      const r = await fetch('/api/planning/department-plan/growth-matrix/import', { method: 'POST', body: form })
      const result = await r.json()
      setUploadResult(result)
      if (result.ok) {
        setUploadFile(null)
        if (fileInputRef.current) fileInputRef.current.value = ''
        await fetchMatrix(activeDiv)
        await fetchBuyerMeta()
      }
    } catch (e) {
      setUploadResult({ ok: false, error: String(e) })
    } finally {
      setUploading(false)
    }
  }

  const depts      = data?.departments || []
  const allPeriods = data?.periods || []
  // Months with at least one live value from Buyer's Input Sheet — a month
  // stays hidden here until real work has landed in BIS for it (standing
  // instruction: don't show a column nobody's touched yet).
  const buyerMonths = new Set(data?.buyer_available_months || [])

  // Restrict to months that have actuals AND (once BIS has anything at all)
  // to months present in Buyer's Input — either filter is skipped while its
  // own source is empty, so this degrades to "show everything" the same way
  // it always did before either live source existed.
  const shownPeriods = allPeriods.filter(p => {
    const month = p.replace(/ P[12]$/, '')
    if (activeMonths.size > 0 && !activeMonths.has(month)) return false
    if (buyerMonths.size > 0 && !buyerMonths.has(month)) return false
    return true
  })
  // the Month filter picks which of those month columns show (2026-10-13)
  const monthsAvail = [...new Set(shownPeriods.map(p => p.replace(/ P[12]$/, '')))]
  const activePeriods = shownPeriods.filter(p => !xf.month || xf.month.includes(p.replace(/ P[12]$/, '')))
  const monthGroups = buildMonthGroups(activePeriods)

  const base = depts
  // a cell as its filter lists it: the name, the attribute, Active / Inactive, or the period's growth index as shown
  const cellVal = (d, col) => (col === 'department' ? d.name : col === 'attribute' ? d.attribute
    : col === 'status' ? (d.active === false ? 'Inactive' : 'Active') : String(+(+(d.periods[col] ?? 100)).toFixed(2)))
  // Month filters the columns, not the rows
  const passXf = (d, skip) => Object.entries(xf).every(([c, vals]) => c === skip || c === 'month' || vals.includes(cellVal(d, c)))
  const isNum = col => !['department', 'attribute', 'status', 'month'].includes(col)
  const filtered = base.filter(d => passXf(d))
  if (xs) {   // Excel's Sort A to Z / Smallest to Largest on that column (view only)
    const k = d => cellVal(d, xs.col)
    filtered.sort((a, b) => (isNum(xs.col) ? +k(a) - +k(b) : k(a).localeCompare(k(b))) * (xs.dir === 'za' ? -1 : 1))
  }
  // a column's list = the values left by the OTHER columns' filters, as Excel does (numbers in numeric order)
  const xfValues = col => {
    if (col === 'month') return monthsAvail
    const v = [...new Set(base.filter(d => passXf(d, col)).map(d => cellVal(d, col)))]
    return isNum(col) ? v.sort((a, b) => +a - +b) : v.sort()
  }
  // the Filters row - one multi-select per field, as Final Results (user, 2026-10-13: "add the same filters row")
  const GM_FIELDS = [['department', 'Department'], ['attribute', 'Attribute'], ['status', 'Status'], ['month', 'Month']]
  const caption = c => (!xf[c] ? '(All)' : xf[c].length === 1 ? xf[c][0] : `(Multiple Items) ${xf[c].length}`)
  const nXf = Object.keys(xf).length
  const fb = (col, title) => (
    <FilterButton active={!!xf[col]} sorted={xs && xs.col === col ? xs.dir : null}
      label={`Filter ${title}${xf[col] ? ` (${xf[col].length} picked)` : ''}`} title={xf[col] ? `Filtered: ${xf[col].join(', ')}` : `Filter / sort ${title}`}
      onClick={el => setXfEdit(x => (x && x.col === col ? null : { col, title, anchor: el }))} />
  )

  const divMeta = buyerMeta[activeDiv]

  return (
    <div style={{ padding: '28px 32px', minHeight: '100vh' }}>

      {/* Pipeline modal */}
      {showPipelineModal && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)',
          zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <div style={{
            background: theme.surface, borderRadius: 14, border: `1px solid ${theme.border}`,
            padding: '28px 32px', width: 420, boxShadow: '0 8px 40px rgba(0,0,0,0.4)',
          }}>
            <div style={{ fontSize: 17, fontWeight: 700, color: theme.textPrimary, marginBottom: 6 }}>
              Base plan ready{genStores ? ` — ${genStores} stores` : ''}. What next?
            </div>
            <div style={{ fontSize: 13, color: theme.textMuted, marginBottom: 22 }}>
              New departments from BIS are already in this plan. Tick one or more optional engines - they run in this order,
              each taking you to the next - or run just one with <b>Only this</b>. Or opt out and go straight to the final results.
            </div>

            {corrOff && <div style={{ fontSize: 12.5, color: theme.warning, marginBottom: 10 }}>You are in Cluster view: Attr and Base Correction work store by store, so they are off here - switch to Store view (top bar) to run them.</div>}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 24 }}>
              {Object.entries(ENGINE_META).map(([key, meta]) => (
                <label key={key} title={corrOff ? 'Store-level - switch to Store view (top bar) to run it' : undefined} style={{
                  display: 'flex', alignItems: 'flex-start', gap: 12, cursor: corrOff ? 'not-allowed' : 'pointer', opacity: corrOff ? 0.5 : 1,
                  padding: '10px 14px', borderRadius: 9,
                  background: pipelineChecked[key] ? `${alpha(theme.primary,'12')}` : theme.surfaceAlt,
                  border: `1px solid ${pipelineChecked[key] ? theme.primary : theme.border}`,
                  transition: 'all 0.12s',
                }}>
                  <input
                    type="checkbox"
                    checked={!corrOff && !!pipelineChecked[key]} disabled={corrOff}
                    onChange={e => setPipelineChecked(prev => ({ ...prev, [key]: e.target.checked }))}
                    style={{ marginTop: 2, accentColor: theme.primary }}
                  />
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: theme.textPrimary }}>{meta.label}</div>
                    <div style={{ fontSize: 11, color: theme.textMuted, marginTop: 2 }}>{meta.desc}</div>
                  </div>
                  <button type="button" disabled={corrOff} onClick={e => { e.preventDefault(); setShowPipelineModal(false); handleStartPipeline(key) }}
                    style={{ alignSelf: 'center', fontSize: 11.5, fontWeight: 600, padding: '4px 10px', borderRadius: 6, cursor: 'pointer',
                             background: 'none', border: `1px solid ${theme.border}`, color: theme.textSecondary, whiteSpace: 'nowrap' }}>
                    Only this →
                  </button>
                </label>
              ))}
            </div>

            <div style={{ display: 'flex', gap: 10 }}>
              <button
                onClick={() => { setShowPipelineModal(false); navigate('/department-plan/final-results') }}
                style={{ flex: 1, padding: '9px 0', borderRadius: 8, fontSize: 13, fontWeight: 500, cursor: 'pointer', background: 'none', border: `1px solid ${theme.border}`, color: theme.textMuted }}
              >Opt out — see Final Results</button>
              <button
                onClick={() => { setShowPipelineModal(false); handleStartPipeline() }}
                disabled={!Object.values(pipelineChecked).some(Boolean)}
                style={{ flex: 1, padding: '9px 0', borderRadius: 8, fontSize: 13, fontWeight: 700, background: 'var(--st-btn,#A8CBB7)', border: 'none', color: 'var(--st-btn-text,#1F4D3A)',
                         cursor: Object.values(pipelineChecked).some(Boolean) ? 'pointer' : 'default', opacity: Object.values(pipelineChecked).some(Boolean) ? 1 : 0.5 }}
              >
                {(() => { const n = Object.values(pipelineChecked).filter(Boolean).length; return n ? `Run ${n} selected →` : 'Tick an engine to run' })()}
              </button>
            </div>
          </div>
        </div>
      )}

      <style>{`@keyframes spin { from { transform: rotate(0deg) } to { transform: rotate(360deg) } }`}</style>

      <div className="sp-sub">
        P1 / P2 growth index per department per month — baseline 100. Buyer inputs can be uploaded from Matrix tools ▾.
      </div>

      {/* Division tabs */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 18, flexWrap: 'wrap' }}>
        {DIVISIONS.map(div => (
          <button key={div} onClick={() => setActiveDiv(div)} style={{
            padding: '8px 18px', borderRadius: 7, cursor: 'pointer',
            border: activeDiv === div ? `2px solid ${DIV_COLOR[div]}` : `2px solid transparent`,
            background: activeDiv === div ? DIV_COLOR[div] : theme.surface,
            color: activeDiv === div ? '#fff' : theme.textPrimary,
            fontWeight: 600, fontSize: 13, outline: 'none',
            boxShadow: activeDiv === div ? `0 2px 8px ${alpha(DIV_COLOR[div],'44')}` : 'none',
          }}>{div}</button>
        ))}
      </div>

      {/* Panel */}
      <div style={{ background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: 10 }}>

        {/* Toolbar */}
        <div style={{
          padding: '13px 20px', borderBottom: `1px solid ${theme.border}`,
          display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
        }}>
          <div style={{ width: 10, height: 10, borderRadius: '50%', background: DIV_COLOR[activeDiv] }} />
          <span style={{ fontWeight: 700, fontSize: 14 }}>{activeDiv}</span>
          <span style={{ fontSize: 12, color: theme.textSecondary }}>
            {depts.length} departments · {monthGroups.length} months
            {activeMonths.size > 0 && activeMonths.size < 13 && (
              <span style={{ marginLeft: 6, fontSize: 10, color: theme.accent, fontWeight: 600 }}>
                (actuals uploaded)
              </span>
            )}
          </span>

          {/* the menu closes on click, so its own "Syncing…" label isn't seen (audit 2026-10-07) */}
          {buyerSyncing && <span role="status" style={{ fontSize: 11, color: theme.textMuted }}>Syncing from Buyer's Input Sheet…</span>}
          {saving && <span style={{ fontSize: 11, color: theme.textMuted }}>Saving…</span>}
          {!saving && lastSaved && <span style={{ fontSize: 11, color: theme.accent }}>✓ Saved {lastSaved}</span>}
          {buyerSyncResult && (
            <span style={{
              fontSize: 11, padding: '3px 10px', borderRadius: 5,
              background: buyerSyncResult.ok ? `${alpha(theme.success,'14')}` : '#FEE2E2',
              color: buyerSyncResult.ok ? theme.success : '#991B1B',
              border: `1px solid ${buyerSyncResult.ok ? theme.success + '44' : '#F7C1BC'}`,
            }}>
              {buyerSyncResult.msg}
            </span>
          )}

          <div style={{ flex: 1 }} />

          {genMsg && <span style={{ fontSize: 12, color: theme.success, fontWeight: 600 }}>{genMsg}</span>}

          <button
            onClick={() => navigate('/department-plan/new-depts')}
            title="New departments flow from BIS - check or change their reference department and % here and see the result"
            style={{ padding: '6px 12px', borderRadius: 6, fontSize: 12, cursor: 'pointer', background: 'none',
                     border: `1px solid ${theme.border}`, color: theme.textSecondary, fontWeight: 600 }}
          >⚙ New depts config</button>

          <button
            onClick={handleGenerateBase}
            disabled={generating}
            style={{
              padding: '6px 16px', borderRadius: 6, fontSize: 12, cursor: generating ? 'default' : 'pointer',
              background: 'var(--st-btn,#A8CBB7)', border: 'none', color: 'var(--st-btn-text,#1F4D3A)',
              fontWeight: 700, opacity: generating ? 0.7 : 1, display: 'flex', alignItems: 'center', gap: 6,
            }}
          >
            {generating ? 'Generating…' : '▶ Generate Base Plan & continue'}
          </button>

          <details className="sp-menu">
            <summary>Matrix tools ▾</summary>
            <div className="sp-menu-pop">
              {/* Buyer upload toggle */}
              <button onClick={() => { setShowUpload(v => !v); setUploadResult(null) }}>
                ↑ Buyer Input
                {showUpload && <span style={{ fontSize: 10, color: theme.textMuted }}>(open)</span>}
                {divMeta && !showUpload && (
                  <span style={{
                    fontSize: 9, fontWeight: 700, padding: '1px 5px', borderRadius: 10,
                    background: '#00A86B', color: '#fff', marginLeft: 2,
                  }}>linked</span>
                )}
              </button>
          <button
            onClick={async () => {
              setBuyerSyncing(true); setBuyerSyncResult(null)
              try {
                const r = await fetch('/api/planning/department-plan/sync-from-buyer', { method: 'POST' })
                const d = await r.json()
                setBuyerSyncResult({ ok: r.ok, msg: r.ok ? d.message : (d.detail || 'Error') })
                if (r.ok) { await fetchMatrix(activeDiv); await fetchBuyerMeta() }
              } catch (e) { setBuyerSyncResult({ ok: false, msg: String(e) }) }
              finally { setBuyerSyncing(false) }
            }}
            disabled={buyerSyncing}
          >
            <span style={buyerSyncing ? { animation: 'spin 0.9s linear infinite', display: 'inline-block' } : {}}>↺</span>
            {buyerSyncing ? 'Syncing…' : 'Sync from Buyer\'s Input Sheet'}
          </button>
              <hr />
              <button className="sp-danger" onClick={handleReset}>↺ Reset to 100</button>
            </div>
          </details>

          {/* Legend (was its own row) */}
          <details className="sp-info">
            <summary aria-label="Legend">ⓘ</summary>
            <div className="sp-menu-pop" style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <span style={{ fontWeight: 700, letterSpacing: 0.4 }}>LEGEND</span>
              <span>
                <span style={{ display: 'inline-block', width: 10, height: 10, background: 'rgba(0,168,107,0.18)', borderRadius: 2, marginRight: 4 }} />
                Above 100 (growth)
              </span>
              <span>
                <span style={{ display: 'inline-block', width: 10, height: 10, background: 'rgba(217,79,61,0.18)', borderRadius: 2, marginRight: 4 }} />
                Below 100 (decline)
              </span>
              <span>
                <span style={{ display: 'inline-block', width: 10, height: 10, background: 'transparent', border: '1px solid #D6E0EF', borderRadius: 2, marginRight: 4 }} />
                100 = baseline
              </span>
              <span>
                🔗 <span style={{ color: '#1D4ED8' }}>Live from Buyer's Input</span> — read-only here, edit there
              </span>
              {/* User, 2026-09-26: GM / RETAIL stay editable with every month - BIS doesn't cover them, so the
                  "hide months BIS hasn't recorded" rule applies to KIDS / LADIES / MENS only. */}
              {data?.division && !['KIDS', 'LADIES', 'MENS'].includes(String(data.division).toUpperCase()) && (
                <span>
                  Buyer's Input covers KIDS, LADIES and MENS only — every {String(data.division).toUpperCase()} month is entered here
                </span>
              )}
              <span style={{ fontStyle: 'italic' }}>
                Click a P1/P2 header to fill entire column
              </span>
            </div>
          </details>
        </div>

        {/* Buyer Upload Panel */}
        {showUpload && (
          <div style={{
            borderBottom: `1px solid ${theme.border}`,
            background: theme.surfaceAlt,
            padding: '18px 24px',
          }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 32, flexWrap: 'wrap' }}>

              {/* Upload area */}
              <div style={{ flex: 1, minWidth: 280 }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: theme.textPrimary, marginBottom: 6 }}>
                  Upload Buyer Growth Input — {activeDiv}
                </div>
                <div style={{ fontSize: 12, color: theme.textSecondary, marginBottom: 14, lineHeight: 1.6 }}>
                  Upload an <strong>Excel (.xlsx)</strong> or <strong>CSV</strong> file.<br />
                  Required columns: <code style={{ background: '#EEF1FD', padding: '1px 5px', borderRadius: 3, fontSize: 11, color: '#4338CA' }}>Department</code> + any period columns (e.g. <code style={{ background: '#EEF1FD', padding: '1px 5px', borderRadius: 3, fontSize: 11, color: '#4338CA' }}>Apr'27 P1</code>).<br />
                  Values are growth % — use <strong>100</strong> for no change, <strong>110</strong> for +10%.
                </div>

                <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
                  <label style={{
                    padding: '7px 16px', borderRadius: 6, fontSize: 12, cursor: 'pointer',
                    background: theme.surface, border: `1px dashed ${DIV_COLOR[activeDiv]}`,
                    color: DIV_COLOR[activeDiv], fontWeight: 600,
                    display: 'inline-flex', alignItems: 'center', gap: 6,
                  }}>
                    📎 Choose file
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".xlsx,.xls,.csv"
                      style={{ display: 'none' }}
                      onChange={e => { setUploadFile(e.target.files[0] || null); setUploadResult(null) }}
                    />
                  </label>

                  {uploadFile && (
                    <span style={{ fontSize: 12, color: theme.textPrimary, fontWeight: 500 }}>
                      {uploadFile.name}
                      <button onClick={() => { setUploadFile(null); if (fileInputRef.current) fileInputRef.current.value = '' }}
                        style={{ marginLeft: 8, background: 'none', border: 'none', cursor: 'pointer', color: '#D94F3D', fontSize: 14, fontWeight: 700 }}>×</button>
                    </span>
                  )}

                  <button
                    onClick={handleUpload}
                    disabled={!uploadFile || uploading}
                    style={{
                      padding: '7px 20px', borderRadius: 6, fontSize: 12, fontWeight: 700,
                      cursor: uploadFile && !uploading ? 'pointer' : 'not-allowed',
                      background: uploadFile && !uploading ? DIV_COLOR[activeDiv] : '#D1D5DB',
                      color: '#fff', border: 'none',
                    }}>
                    {uploading ? 'Uploading…' : 'Upload & Apply'}
                  </button>
                </div>

                {/* Result feedback */}
                {uploadResult && (
                  <div style={{
                    marginTop: 12, padding: '10px 14px', borderRadius: 7, fontSize: 12,
                    background: uploadResult.ok ? '#ECFDF3' : '#FEF3F2',
                    border: `1px solid ${uploadResult.ok ? '#A6E3BD' : '#4D1515'}`,
                    color: uploadResult.ok ? '#15803D' : '#B42318',
                  }}>
                    {uploadResult.ok ? (
                      <>
                        ✓ Applied successfully — <strong>{uploadResult.depts_processed}</strong> departments,{' '}
                        <strong>{uploadResult.values_updated}</strong> values updated across{' '}
                        <strong>{uploadResult.periods_matched?.length}</strong> periods.
                        {uploadResult.values_skipped > 0 && ` (${uploadResult.values_skipped} blank cells skipped)`}
                      </>
                    ) : (
                      <>✗ {uploadResult.error}</>
                    )}
                  </div>
                )}
              </div>

              {/* Format guide */}
              <div style={{ minWidth: 240 }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: theme.textMuted, letterSpacing: 0.4, marginBottom: 8 }}>EXPECTED FORMAT</div>
                <table style={{ fontSize: 11, borderCollapse: 'collapse', color: theme.textSecondary }}>
                  <thead>
                    <tr style={{ background: '#EEF1FD' }}>
                      {["Department", "Apr'27 P1", "Apr'27 P2", "May'27 P1", "…"].map(h => (
                        <th key={h} style={{ padding: '4px 8px', border: `1px solid ${theme.border}`, fontWeight: 600, color: '#4338CA', fontSize: 10 }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {[["KB_BERMUDA", "105", "108", "110", "…"], ["KG_FROCK", "100", "100", "102", "…"]].map((row, i) => (
                      <tr key={i} style={{ background: i % 2 === 0 ? theme.surface : theme.surfaceAlt }}>
                        {row.map((cell, j) => (
                          <td key={j} style={{ padding: '4px 8px', border: `1px solid ${theme.border}`, fontFamily: 'monospace', fontSize: 10, color: theme.textSecondary }}>{cell}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>

                {/* Last upload info */}
                {divMeta && (
                  <div style={{ marginTop: 12, padding: '8px 10px', borderRadius: 6, background: '#ECFDF3', border: '1px solid #A6E3BD', fontSize: 11, color: '#15803D' }}>
                    <div style={{ fontWeight: 700, marginBottom: 2 }}>Last buyer upload</div>
                    <div>{divMeta.filename}</div>
                    <div style={{ opacity: 0.8, marginTop: 2 }}>{divMeta.uploaded_at} · {divMeta.depts_updated} depts · {divMeta.periods_updated} periods</div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Filters - one multi-select dropdown per field, as Final Results (user, 2026-10-13) */}
        <div data-no-undo style={{
          padding: '10px 20px', borderBottom: `1px solid ${theme.border}`,
          display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap',
        }}>
          <span style={{ fontSize: 12, fontWeight: 700, color: theme.textMuted, textTransform: 'uppercase', letterSpacing: 0.6, marginRight: 4 }}>Filters</span>
          {GM_FIELDS.map(([c, label]) => (
            <button key={c} type="button" aria-haspopup="dialog" onClick={e => { const el = e.currentTarget; setXfEdit(x => (x && x.col === c ? null : { col: c, title: label, anchor: el })) }}
              title={xf[c] ? xf[c].join(', ') : `All ${label.toLowerCase()}`}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '3px 8px', borderRadius: 4, fontSize: 12, cursor: 'pointer', maxWidth: 260,
                       border: `1px solid ${xf[c] ? theme.primary : theme.border}`, background: xf[c] ? alpha(theme.primary, '12') : theme.surface, color: theme.textPrimary }}>
              <span style={{ color: theme.textMuted }}>{label}</span>
              <b style={{ fontWeight: xf[c] ? 700 : 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{caption(c)}</b>
              <span aria-hidden="true" style={{ color: theme.textMuted, fontSize: 10 }}>▾</span>
            </button>
          ))}
          {nXf > 0 && (<>
            <span style={{ fontSize: 11, color: theme.textMuted, marginLeft: 4 }}>showing {filtered.length} of {depts.length}</span>
            <button type="button" onClick={() => setXf({})} style={{ all: 'unset', cursor: 'pointer', fontSize: 12, color: theme.textMuted, textDecoration: 'underline', marginLeft: 4 }}>Clear all</button>
          </>)}
        </div>

        {loading ? (
          <div style={{ padding: 40, textAlign: 'center', color: theme.textSecondary, fontSize: 13 }}>
            Loading {activeDiv} growth matrix…
          </div>
        ) : depts.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: theme.textMuted, fontSize: 13 }}>
            No departments in {activeDiv} yet. Add them in Master Setup.
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ borderCollapse: 'collapse', fontSize: 11, fontVariantNumeric: 'tabular-nums', minWidth: '100%' }}>
              <thead>
                <tr style={{ background: theme.surfaceUp }}>
                  <th style={{ ...stickyTh, width: 220, minWidth: 220, borderRight: `2px solid ${theme.border}` }} rowSpan={2}>
                    Department{fb('department', 'Department')}
                  </th>
                  <th style={{ ...stickyTh, width: 100, minWidth: 100, borderRight: `2px solid ${theme.border}` }} rowSpan={2}>
                    Attribute{fb('attribute', 'Attribute')}
                  </th>
                  {monthGroups.map(mg => (
                    <th key={mg.label} colSpan={2} style={{
                      padding: '6px 4px', textAlign: 'center',
                      fontSize: 10.5, fontWeight: 700, color: theme.primary,
                      borderBottom: `1px solid ${theme.border}`,
                      borderRight: `1px solid ${theme.border}`,
                      letterSpacing: 0.3,
                    }}>
                      {mg.label}
                    </th>
                  ))}
                </tr>
                <tr style={{ background: theme.surfaceAlt }}>
                  {monthGroups.map(mg => (
                    [mg.p1, mg.p2].map((p, pi) => (
                      <th key={p} onClick={() => handleFillColumn(p)} style={{
                        padding: '5px 3px', textAlign: 'center',
                        fontSize: 10, fontWeight: 700,
                        color: pi === 0 ? '#1D4ED8' : '#7E22CE',
                        borderBottom: `2px solid ${theme.border}`,
                        borderRight: pi === 1 ? `1px solid ${theme.border}` : 'none',
                        cursor: 'pointer', userSelect: 'none',
                        letterSpacing: 0.3,
                      }}>
                        {pi === 0 ? 'P1' : 'P2'}{fb(p, `${p} (growth index)`)}
                      </th>
                    ))
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((dept, i) => {
                  const as = ATTR_STYLE[dept.attribute] || { bg: '#F3F4F6', color: '#374151' }
                  // Inactive in Department Master Setup → greyed out and read-only (user, 2026-09-26); the plan gives it TY 0
                  const inactive = dept.active === false
                  return (
                    <tr key={dept.name} style={{
                      borderBottom: `1px solid #EEF2F8`,
                      background: inactive ? 'rgba(var(--st-ink-rgb,30,39,35),0.06)' : i % 2 === 0 ? 'transparent' : 'rgba(var(--st-ink-rgb,30,39,35),0.025)',
                      opacity: inactive ? 0.45 : 1,
                    }} title={inactive ? 'Inactive in Department Master Setup - not planned' : undefined}>
                      <td style={{
                        padding: '5px 10px 5px 20px',
                        fontWeight: 500, fontSize: 11.5,
                        color: theme.textPrimary,
                        borderRight: `2px solid ${theme.border}`,
                        whiteSpace: 'nowrap', maxWidth: 220,
                        overflow: 'hidden', textOverflow: 'ellipsis',
                      }} title={dept.name}>
                        {dept.name}
                        {inactive && <span style={{ marginLeft: 6, fontSize: 9, fontWeight: 700, letterSpacing: 0.4, padding: '1px 4px',
                          borderRadius: 3, border: `1px solid ${theme.border}`, color: theme.textSecondary }}>INACTIVE</span>}
                      </td>
                      <td style={{ padding: '5px 8px', borderRight: `2px solid ${theme.border}`, whiteSpace: 'nowrap' }}>
                        <span style={{
                          fontSize: 9.5, fontWeight: 600, letterSpacing: 0.4,
                          padding: '2px 5px', borderRadius: 3,
                          background: as.bg, color: as.color,
                        }}>{dept.attribute}</span>
                      </td>
                      {activePeriods.map((p, pi) => {
                        const val = dept.periods[p] ?? 100
                        const isP2 = pi % 2 === 1
                        const fromBuyer = dept.buyer_periods?.includes(p)
                        return (
                          <td key={p} style={{
                            padding: '3px 2px',
                            background: fromBuyer ? 'rgba(96,165,250,0.10)' : cellBg(val),
                            borderRight: isP2 ? `1px solid ${theme.border}` : 'none',
                            textAlign: 'center',
                          }} title={fromBuyer ? "Live from Buyer's Input Sheet — edit there, not here" : undefined}>
                            <div style={{ display: 'inline-flex', alignItems: 'center', gap: 1 }}>
                              {fromBuyer && <span style={{ fontSize: 9, color: '#1D4ED8' }}>🔗</span>}
                              <input
                                type="number"
                                step={0.1}
                                value={val}
                                readOnly={fromBuyer || inactive}
                                onChange={e => !fromBuyer && !inactive && handleChange(dept.name, p, e.target.value)}
                                style={{
                                  width: 40, textAlign: 'right',
                                  border: '1px solid transparent', borderRadius: 3,
                                  fontSize: 11, padding: '2px 1px',
                                  background: 'transparent',
                                  color: fromBuyer ? '#1D4ED8' : cellColor(val),
                                  fontFamily: theme.fontMono,
                                  fontVariantNumeric: 'tabular-nums',
                                  fontWeight: val !== 100 ? 600 : 400,
                                  outline: 'none',
                                  cursor: fromBuyer || inactive ? 'not-allowed' : 'text',
                                }}
                                onFocus={e => !fromBuyer && !inactive && (e.target.style.borderColor = theme.primary)}
                                onBlur={e => e.target.style.borderColor = 'transparent'}
                              />
                              <span style={{ fontSize: 10, color: fromBuyer ? '#1D4ED8' : cellColor(val), opacity: 0.7, userSelect: 'none' }}>%</span>
                            </div>
                          </td>
                        )
                      })}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
      {xfEdit && <ExcelFilter key={xfEdit.col + JSON.stringify(xf) + JSON.stringify(xs)} title={xfEdit.title} anchor={xfEdit.anchor} picked={xf[xfEdit.col]}
        load={() => xfValues(xfEdit.col)} numeric={isNum(xfEdit.col)}
        sort={xs && xs.col === xfEdit.col ? xs.dir : null} onSort={xfEdit.col === 'month' ? undefined : dir => setXs(dir ? { col: xfEdit.col, dir } : null)}
        onDone={vals => {
          if (vals !== undefined) setXf(f => { const n = { ...f }; if (vals.length) n[xfEdit.col] = vals; else delete n[xfEdit.col]; return n })
          setXfEdit(null)
        }} />}
      <BisCompare division={activeDiv} />
      <GrainPanel stage="department" division={activeDiv} title={`${activeDiv} department plan`} />
    </div>
  )
}

const stickyTh = {
  padding: '8px 10px 8px 20px',
  textAlign: 'left',
  fontSize: 10.5,
  fontWeight: 600,
  color: theme.textMuted,
  letterSpacing: 0.4,
  borderBottom: `2px solid ${theme.border}`,
  background: theme.surfaceAlt,
  whiteSpace: 'nowrap',
}

function deepMerge(a, b) {
  const out = { ...a }
  for (const k of Object.keys(b)) {
    out[k] = a[k] ? { ...a[k], ...b[k] } : { ...b[k] }
  }
  return out
}
