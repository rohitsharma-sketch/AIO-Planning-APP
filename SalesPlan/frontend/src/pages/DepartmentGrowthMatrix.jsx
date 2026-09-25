import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { theme } from '../theme'
import { ENGINE_META, startPipeline } from '../pipelineState'
import SearchSlicer from '../components/SearchSlicer'

const DIVISIONS = ['KIDS', 'LADIES', 'MENS', 'GM', 'RETAIL']

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
  const [deptFilters, setDeptFilters] = useState(new Set())
  const [attrFilter, setAttrFilter]   = useState(null)
  const [activeMonths, setActiveMonths] = useState(new Set())
  const [saving, setSaving]           = useState(false)
  const [lastSaved, setLastSaved]     = useState(null)
  const [generating, setGenerating]   = useState(false)
  const [genMsg, setGenMsg]           = useState('')
  const [showPipelineModal, setShowPipelineModal] = useState(false)
  const [pipelineChecked, setPipelineChecked] = useState({ 'new-depts': false, 'attr-correction': false, 'base-correction': true })
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
    setAttrFilter(null)
    setDeptFilters(new Set())
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
        setGenMsg(`✓ ${d.stores} stores — select engines below`)
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

  const handleStartPipeline = () => {
    const queue = Object.keys(pipelineChecked).filter(k => pipelineChecked[k])
    if (queue.length === 0) {
      navigate('/department-plan/final-results')
      return
    }
    startPipeline(queue)
    navigate(ENGINE_META[queue[0]].route)
  }

  const handleReset = async () => {
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
      departments: prev.departments.map(d => ({
        ...d,
        periods: { ...d.periods, [period]: val },
      })),
    }))
    const batch = {}
    data?.departments.forEach(d => { batch[d.name] = { [period]: val } })
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
  const activePeriods = allPeriods.filter(p => {
    const month = p.replace(/ P[12]$/, '')
    if (activeMonths.size > 0 && !activeMonths.has(month)) return false
    if (buyerMonths.size > 0 && !buyerMonths.has(month)) return false
    return true
  })
  const monthGroups = buildMonthGroups(activePeriods)

  const attrCounts = {}
  depts.forEach(d => { attrCounts[d.attribute] = (attrCounts[d.attribute] || 0) + 1 })

  const deptNames = depts.map(d => d.name)

  const filtered = depts.filter(d => {
    const matchDept = deptFilters.size === 0 || deptFilters.has(d.name)
    const matchAttr = !attrFilter || d.attribute === attrFilter
    return matchDept && matchAttr
  })

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
            <div style={{ fontSize: 17, fontWeight: 700, color: theme.textPrimary, marginBottom: 6 }}>Base plan ready</div>
            <div style={{ fontSize: 13, color: theme.textMuted, marginBottom: 22 }}>
              Select optional engines to run before viewing the final output.
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 24 }}>
              {Object.entries(ENGINE_META).map(([key, meta]) => (
                <label key={key} style={{
                  display: 'flex', alignItems: 'flex-start', gap: 12, cursor: 'pointer',
                  padding: '10px 14px', borderRadius: 9,
                  background: pipelineChecked[key] ? `${theme.primary}12` : theme.surfaceAlt,
                  border: `1px solid ${pipelineChecked[key] ? theme.primary : theme.border}`,
                  transition: 'all 0.12s',
                }}>
                  <input
                    type="checkbox"
                    checked={!!pipelineChecked[key]}
                    onChange={e => setPipelineChecked(prev => ({ ...prev, [key]: e.target.checked }))}
                    style={{ marginTop: 2, accentColor: theme.primary }}
                  />
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 600, color: theme.textPrimary }}>{meta.label}</div>
                    <div style={{ fontSize: 11, color: theme.textMuted, marginTop: 2 }}>{meta.desc}</div>
                  </div>
                </label>
              ))}
            </div>

            <div style={{ display: 'flex', gap: 10 }}>
              <button
                onClick={() => { setShowPipelineModal(false); navigate('/department-plan/final-results') }}
                style={{ flex: 1, padding: '9px 0', borderRadius: 8, fontSize: 13, fontWeight: 500, cursor: 'pointer', background: 'none', border: `1px solid ${theme.border}`, color: theme.textMuted }}
              >Skip to Final Results</button>
              <button
                onClick={() => { setShowPipelineModal(false); handleStartPipeline() }}
                style={{ flex: 1, padding: '9px 0', borderRadius: 8, fontSize: 13, fontWeight: 700, cursor: 'pointer', background: '#A8CBB7', border: 'none', color: '#1F4D3A' }}
              >
                {Object.values(pipelineChecked).some(Boolean) ? 'Run Pipeline →' : 'Go to Final Results'}
              </button>
            </div>
          </div>
        </div>
      )}

      <style>{`@keyframes spin { from { transform: rotate(0deg) } to { transform: rotate(360deg) } }`}</style>

      {/* Header */}
      <div style={{ marginBottom: 22, display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16 }}>
        <div>
          <div style={{ fontSize: 22, fontWeight: 700, color: theme.textPrimary }}>Department Growth Matrix</div>
          <div style={{ fontSize: 13, color: theme.textSecondary, marginTop: 4 }}>
            P1 / P2 growth index per department per month — baseline 100. Buyer inputs can be uploaded below.
          </div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6 }}>
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
            style={{
              padding: '8px 18px', borderRadius: 8, border: `1.5px solid ${theme.success}`,
              background: buyerSyncing ? 'transparent' : `${theme.success}12`,
              color: theme.success, fontWeight: 700, fontSize: 12, cursor: buyerSyncing ? 'default' : 'pointer',
              display: 'flex', alignItems: 'center', gap: 7,
            }}
          >
            <span style={buyerSyncing ? { animation: 'spin 0.9s linear infinite', display: 'inline-block' } : {}}>↺</span>
            {buyerSyncing ? 'Syncing…' : 'Sync from Buyer\'s Input Sheet'}
          </button>
          {buyerSyncResult && (
            <div style={{
              fontSize: 11, padding: '4px 10px', borderRadius: 5,
              background: buyerSyncResult.ok ? `${theme.success}14` : '#FEE2E2',
              color: buyerSyncResult.ok ? theme.success : '#991B1B',
              border: `1px solid ${buyerSyncResult.ok ? theme.success + '44' : '#F7C1BC'}`,
            }}>
              {buyerSyncResult.msg}
            </div>
          )}
        </div>
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
            boxShadow: activeDiv === div ? `0 2px 8px ${DIV_COLOR[div]}44` : 'none',
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

          <div style={{
            padding: '3px 10px', borderRadius: 20, fontSize: 11, fontWeight: 600,
            background: '#EFF6FF', color: '#1D4ED8',
          }}>
            Baseline 100
          </div>

          {saving && <span style={{ fontSize: 11, color: theme.textMuted }}>Saving…</span>}
          {!saving && lastSaved && <span style={{ fontSize: 11, color: theme.accent }}>✓ Saved {lastSaved}</span>}

          <div style={{ flex: 1 }} />

          {genMsg && <span style={{ fontSize: 12, color: theme.success, fontWeight: 600 }}>{genMsg}</span>}
          <button
            onClick={handleGenerateBase}
            disabled={generating}
            style={{
              padding: '6px 16px', borderRadius: 6, fontSize: 12, cursor: generating ? 'default' : 'pointer',
              background: '#A8CBB7', border: 'none', color: '#1F4D3A',
              fontWeight: 700, opacity: generating ? 0.7 : 1, display: 'flex', alignItems: 'center', gap: 6,
            }}
          >
            {generating ? 'Generating…' : '▶ Generate Base Plan'}
          </button>

          <SearchSlicer
            items={deptNames}
            selected={deptFilters}
            onChange={setDeptFilters}
            label="All Departments"
            placeholder="Search department…"
            width={170}
          />

          {/* Buyer upload toggle */}
          <button onClick={() => { setShowUpload(v => !v); setUploadResult(null) }} style={{
            padding: '6px 14px', borderRadius: 6, fontSize: 12, cursor: 'pointer',
            background: showUpload ? DIV_COLOR[activeDiv] : theme.surfaceAlt,
            border: `1px solid ${showUpload ? DIV_COLOR[activeDiv] : theme.border}`,
            color: showUpload ? '#fff' : theme.textSecondary, fontWeight: 600,
            display: 'flex', alignItems: 'center', gap: 6,
          }}>
            ↑ Buyer Input
            {divMeta && !showUpload && (
              <span style={{
                fontSize: 9, fontWeight: 700, padding: '1px 5px', borderRadius: 10,
                background: '#00A86B', color: '#fff', marginLeft: 2,
              }}>linked</span>
            )}
          </button>

          <button onClick={handleReset} style={{
            padding: '6px 14px', borderRadius: 6, fontSize: 12, cursor: 'pointer',
            background: theme.surfaceAlt, border: `1px solid ${theme.border}`,
            color: theme.textSecondary, fontWeight: 500,
          }}>↺ Reset to 100</button>
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

        {/* Attribute filter chips */}
        <div style={{
          padding: '10px 20px', borderBottom: `1px solid ${theme.border}`,
          display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap',
        }}>
          <span style={{ fontSize: 11, color: theme.textMuted, fontWeight: 600, letterSpacing: 0.4, marginRight: 4 }}>FILTER</span>
          <button onClick={() => setAttrFilter(null)} style={{
            padding: '3px 10px', borderRadius: 20, fontSize: 11, fontWeight: 600,
            cursor: 'pointer', border: 'none', outline: 'none',
            background: !attrFilter ? DIV_COLOR[activeDiv] : theme.surfaceAlt,
            color: !attrFilter ? '#fff' : theme.textSecondary,
          }}>
            All <span style={{ opacity: 0.7 }}>({depts.length})</span>
          </button>
          {Object.entries(ATTR_STYLE).map(([attr, s]) => {
            const count = attrCounts[attr] || 0
            if (count === 0) return null
            const isActive = attrFilter === attr
            return (
              <button key={attr} onClick={() => setAttrFilter(isActive ? null : attr)} style={{
                padding: '3px 10px', borderRadius: 20, fontSize: 11, fontWeight: 600,
                cursor: 'pointer', outline: 'none',
                border: isActive ? 'none' : `1px solid ${s.bg === '#1E3A5F' ? '#37423C' : theme.border}`,
                background: isActive ? s.color : s.bg,
                color: isActive ? (s.bg === '#1E3A5F' ? '#1E3A5F' : '#fff') : s.color,
              }}>
                {attr} <span style={{ opacity: 0.7 }}>({count})</span>
              </button>
            )
          })}
          {attrFilter && (
            <span style={{ fontSize: 11, color: theme.textMuted, marginLeft: 4 }}>
              showing {filtered.length} of {depts.length}
            </span>
          )}
        </div>

        {/* Legend */}
        <div style={{
          padding: '8px 20px', borderBottom: `1px solid ${theme.border}`,
          display: 'flex', gap: 18, alignItems: 'center', fontSize: 11,
        }}>
          <span style={{ color: theme.textMuted, fontWeight: 600, letterSpacing: 0.4 }}>LEGEND</span>
          <span style={{ color: theme.textMuted }}>
            <span style={{ display: 'inline-block', width: 10, height: 10, background: 'rgba(0,168,107,0.18)', borderRadius: 2, marginRight: 4 }} />
            Above 100 (growth)
          </span>
          <span style={{ color: theme.textMuted }}>
            <span style={{ display: 'inline-block', width: 10, height: 10, background: 'rgba(217,79,61,0.18)', borderRadius: 2, marginRight: 4 }} />
            Below 100 (decline)
          </span>
          <span style={{ color: theme.textMuted }}>
            <span style={{ display: 'inline-block', width: 10, height: 10, background: 'transparent', border: '1px solid #D6E0EF', borderRadius: 2, marginRight: 4 }} />
            100 = baseline
          </span>
          <span style={{ color: theme.textMuted }}>
            🔗 <span style={{ color: '#1D4ED8' }}>Live from Buyer's Input</span> — read-only here, edit there
          </span>
          <span style={{ marginLeft: 'auto', color: theme.textMuted, fontStyle: 'italic' }}>
            Click a P1/P2 header to fill entire column
          </span>
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
                    Department
                  </th>
                  <th style={{ ...stickyTh, width: 100, minWidth: 100, borderRight: `2px solid ${theme.border}` }} rowSpan={2}>
                    Attribute
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
                        {pi === 0 ? 'P1' : 'P2'}
                      </th>
                    ))
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((dept, i) => {
                  const as = ATTR_STYLE[dept.attribute] || { bg: '#F3F4F6', color: '#374151' }
                  return (
                    <tr key={dept.name} style={{
                      borderBottom: `1px solid #EEF2F8`,
                      background: i % 2 === 0 ? 'transparent' : 'rgba(30,39,35,0.025)',
                    }}>
                      <td style={{
                        padding: '5px 10px 5px 20px',
                        fontWeight: 500, fontSize: 11.5,
                        color: theme.textPrimary,
                        borderRight: `2px solid ${theme.border}`,
                        whiteSpace: 'nowrap', maxWidth: 220,
                        overflow: 'hidden', textOverflow: 'ellipsis',
                      }} title={dept.name}>
                        {dept.name}
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
                                readOnly={fromBuyer}
                                onChange={e => !fromBuyer && handleChange(dept.name, p, e.target.value)}
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
                                  cursor: fromBuyer ? 'not-allowed' : 'text',
                                }}
                                onFocus={e => !fromBuyer && (e.target.style.borderColor = theme.primary)}
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
