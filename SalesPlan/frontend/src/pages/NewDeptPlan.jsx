import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { theme } from '../theme'
import PipelineBanner from '../components/PipelineBanner'
import { currentEngineKey, advancePipeline } from '../pipelineState'

const DIVISIONS = ['KIDS', 'LADIES', 'MENS', 'GM', 'RETAIL']

const DIV_COLOR = {
  KIDS:   '#C85A12',
  LADIES: '#7420B8',
  MENS:   '#077A4A',
  GM:     '#1E54C0',
  RETAIL: '#B22620',
}

const CELL = {
  fontFamily: theme.fontMono,
  fontSize: 12,
  textAlign: 'right',
  padding: '6px 10px',
  whiteSpace: 'nowrap',
}

// Shared checkbox visual used in both pivot components
function PivotCheckbox({ checked, color = theme.primary }) {
  return (
    <div style={{
      width: 15, height: 15, flexShrink: 0, borderRadius: 3,
      border: `1.5px solid ${checked ? color : '#445'}`,
      background: checked ? color : 'transparent',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      transition: 'all 0.12s',
    }}>
      {checked && (
        <svg width="9" height="7" viewBox="0 0 9 7" fill="none">
          <path d="M1 3.5L3.5 6L8 1" stroke="#fff" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      )}
    </div>
  )
}

// Pivot-style single-select for choosing reference dept per row
function PivotSelect({ options, value, onChange }) {
  const [open, setOpen]   = useState(false)
  const [query, setQuery] = useState('')
  const [pos, setPos]     = useState({ top: 0, left: 0 })
  const triggerRef        = useRef(null)
  const panelRef          = useRef(null)

  const filtered = query
    ? options.filter(o => o.toLowerCase().includes(query.toLowerCase()))
    : options

  const handleOpen = () => {
    if (triggerRef.current) {
      const rect       = triggerRef.current.getBoundingClientRect()
      const panelH     = Math.min(120 * 33 + 130, 430)
      const spaceBelow = window.innerHeight - rect.bottom
      const spaceAbove = rect.top
      const openBelow  = spaceBelow >= panelH || spaceBelow >= spaceAbove
      const rawTop     = openBelow ? rect.bottom + 4 : rect.top - panelH - 4
      setPos({
        top:  Math.max(8, Math.min(rawTop, window.innerHeight - panelH - 8)),
        left: Math.max(8, Math.min(rect.left, window.innerWidth - 318)),
      })
    }
    setOpen(true)
    setQuery('')
  }

  useEffect(() => {
    const h = e => {
      if (panelRef.current && !panelRef.current.contains(e.target) &&
          triggerRef.current && !triggerRef.current.contains(e.target)) {
        setOpen(false); setQuery('')
      }
    }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])

  return (
    <>
      <button
        ref={triggerRef}
        onClick={handleOpen}
        style={{
          display: 'flex', alignItems: 'center', gap: 6,
          background: value ? `${theme.primary}15` : theme.surfaceUp,
          border: `1px solid ${value ? theme.primary : theme.border}`,
          borderRadius: 6, padding: '5px 8px 5px 10px',
          color: value ? theme.textPrimary : theme.textMuted,
          fontFamily: theme.fontMono, fontSize: 11.5,
          cursor: 'pointer', width: 210, justifyContent: 'space-between',
          textAlign: 'left',
        }}
      >
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>
          {value || 'Select reference dept…'}
        </span>
        <span style={{ fontSize: 8, opacity: 0.5, flexShrink: 0, marginLeft: 4 }}>▼</span>
      </button>

      {open && (
        <div ref={panelRef} style={{
          position: 'fixed', zIndex: 9999,
          top: pos.top, left: pos.left,
          width: 310, background: '#1a2124',
          border: `1px solid ${theme.borderStrong}`,
          borderRadius: 10, overflow: 'hidden',
          boxShadow: '0 8px 32px rgba(0,0,0,0.65)',
        }}>
          <div style={{ padding: '10px 12px 8px', background: '#FAF9F6', borderBottom: `1px solid ${theme.border}` }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: theme.textMuted, letterSpacing: 0.9, marginBottom: 7 }}>
              REFERENCE DEPARTMENT
            </div>
            <input
              autoFocus
              placeholder="Search…"
              value={query}
              onChange={e => setQuery(e.target.value)}
              style={{
                width: '100%', boxSizing: 'border-box',
                background: theme.surface, border: `1px solid ${theme.border}`,
                borderRadius: 6, padding: '5px 10px',
                fontSize: 12, color: theme.textPrimary,
                fontFamily: theme.fontMono, outline: 'none',
              }}
            />
          </div>

          <div style={{ maxHeight: 270, overflowY: 'auto' }}>
            {filtered.length === 0 && (
              <div style={{ padding: '16px 12px', textAlign: 'center', fontSize: 12, color: theme.textMuted }}>
                No match
              </div>
            )}
            {filtered.map(opt => (
              <div
                key={opt}
                onMouseDown={() => { onChange(opt); setOpen(false); setQuery('') }}
                style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '7px 12px', cursor: 'pointer' }}
                onMouseEnter={e => e.currentTarget.style.background = `${theme.primary}18`}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              >
                <PivotCheckbox checked={opt === value} />
                <span style={{
                  fontFamily: theme.fontMono, fontSize: 11.5,
                  color: opt === value ? theme.textPrimary : theme.textSecondary,
                  fontWeight: opt === value ? 600 : 400,
                }}>
                  {opt}
                </span>
              </div>
            ))}
          </div>

          <div style={{
            display: 'flex', justifyContent: 'flex-end', gap: 8,
            padding: '8px 12px', borderTop: `1px solid ${theme.border}`, background: '#FAF9F6',
          }}>
            <button
              onMouseDown={() => { setOpen(false); setQuery('') }}
              style={{ padding: '4px 14px', borderRadius: 6, background: 'none', border: `1px solid ${theme.border}`, color: theme.textMuted, fontSize: 12, cursor: 'pointer' }}
            >Cancel</button>
            <button
              onMouseDown={() => { setOpen(false); setQuery('') }}
              style={{ padding: '4px 14px', borderRadius: 6, background: '#A8CBB7', color: '#1F4D3A', border: 'none', fontSize: 12, fontWeight: 600, cursor: 'pointer' }}
            >OK</button>
          </div>
        </div>
      )}
    </>
  )
}

// Pivot-style multi-select filter — above table, filters rows by ref dept
function PivotFilter({ label, options, selected, onChange }) {
  const [open, setOpen]   = useState(false)
  const [query, setQuery] = useState('')
  const [draft, setDraft] = useState(new Set())
  const [pos, setPos]     = useState({ top: 0, left: 0 })
  const triggerRef        = useRef(null)
  const panelRef          = useRef(null)

  const filtered = query
    ? options.filter(o => o.toLowerCase().includes(query.toLowerCase()))
    : options

  const handleOpen = () => {
    setDraft(selected.size === 0 ? new Set(options) : new Set(selected))
    if (triggerRef.current) {
      const rect   = triggerRef.current.getBoundingClientRect()
      const panelH = Math.min(options.length * 33 + 140, 420)
      const rawTop = rect.bottom + 4
      setPos({
        top:  Math.max(8, Math.min(rawTop, window.innerHeight - panelH - 8)),
        left: Math.max(8, Math.min(rect.left, window.innerWidth - 318)),
      })
    }
    setOpen(true)
    setQuery('')
  }

  useEffect(() => {
    const h = e => {
      if (panelRef.current && !panelRef.current.contains(e.target) &&
          triggerRef.current && !triggerRef.current.contains(e.target)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])

  const allChecked  = draft.size === options.length
  const toggleAll   = () => setDraft(allChecked ? new Set() : new Set(options))
  const toggleItem  = opt => setDraft(prev => {
    const next = new Set(prev)
    next.has(opt) ? next.delete(opt) : next.add(opt)
    return next
  })
  const handleOK    = () => {
    onChange(draft.size === options.length ? new Set() : new Set(draft))
    setOpen(false)
  }

  const filterActive = selected.size > 0 && selected.size < options.length

  if (options.length === 0) return null

  return (
    <>
      <button
        ref={triggerRef}
        onClick={handleOpen}
        style={{
          display: 'flex', alignItems: 'center', gap: 7,
          padding: '6px 12px',
          background: filterActive ? `${theme.primary}15` : theme.surface,
          border: `1px solid ${filterActive ? theme.primary : theme.border}`,
          borderRadius: 7, cursor: 'pointer',
          color: filterActive ? theme.primary : theme.textSecondary,
          fontSize: 12, fontWeight: filterActive ? 600 : 400,
        }}
      >
        <span style={{ fontSize: 12 }}>⊞</span>
        <span>{label}</span>
        {filterActive && (
          <span style={{ fontSize: 10, background: '#A8CBB7', color: '#1F4D3A', borderRadius: 8, padding: '1px 6px', fontWeight: 700 }}>
            {selected.size}/{options.length}
          </span>
        )}
        <span style={{ fontSize: 8, opacity: 0.5, marginLeft: 2 }}>▼</span>
      </button>

      {open && (
        <div ref={panelRef} style={{
          position: 'fixed', zIndex: 9999,
          top: pos.top, left: pos.left,
          width: 310, background: '#1a2124',
          border: `1px solid ${theme.borderStrong}`,
          borderRadius: 10, overflow: 'hidden',
          boxShadow: '0 8px 32px rgba(0,0,0,0.65)',
        }}>
          <div style={{ padding: '10px 12px 8px', background: '#FAF9F6', borderBottom: `1px solid ${theme.border}` }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: theme.textMuted, letterSpacing: 0.9, marginBottom: 7 }}>
              FILTER — {label.toUpperCase()}
            </div>
            <input
              autoFocus
              placeholder="Search…"
              value={query}
              onChange={e => setQuery(e.target.value)}
              style={{
                width: '100%', boxSizing: 'border-box',
                background: theme.surface, border: `1px solid ${theme.border}`,
                borderRadius: 6, padding: '5px 10px',
                fontSize: 12, color: theme.textPrimary,
                fontFamily: theme.fontMono, outline: 'none',
              }}
            />
          </div>

          {/* Select All */}
          <div
            onMouseDown={toggleAll}
            style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px', cursor: 'pointer', borderBottom: `1px solid rgba(30,39,35,0.05)` }}
            onMouseEnter={e => e.currentTarget.style.background = 'rgba(30,39,35,0.04)'}
            onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
          >
            <PivotCheckbox checked={allChecked} />
            <span style={{ fontSize: 12, fontWeight: 600, color: theme.textPrimary, fontStyle: 'italic' }}>(Select All)</span>
          </div>

          <div style={{ maxHeight: 230, overflowY: 'auto' }}>
            {filtered.map(opt => (
              <div
                key={opt}
                onMouseDown={() => toggleItem(opt)}
                style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '7px 12px', cursor: 'pointer' }}
                onMouseEnter={e => e.currentTarget.style.background = 'rgba(30,39,35,0.04)'}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              >
                <PivotCheckbox checked={draft.has(opt)} />
                <span style={{ fontFamily: theme.fontMono, fontSize: 11.5, color: theme.textSecondary }}>{opt}</span>
              </div>
            ))}
          </div>

          <div style={{
            display: 'flex', justifyContent: 'flex-end', gap: 8,
            padding: '8px 12px', borderTop: `1px solid ${theme.border}`, background: '#FAF9F6',
          }}>
            <button
              onMouseDown={() => setOpen(false)}
              style={{ padding: '4px 14px', borderRadius: 6, background: 'none', border: `1px solid ${theme.border}`, color: theme.textMuted, fontSize: 12, cursor: 'pointer' }}
            >Cancel</button>
            <button
              onMouseDown={handleOK}
              style={{ padding: '4px 14px', borderRadius: 6, background: '#A8CBB7', color: '#1F4D3A', border: 'none', fontSize: 12, fontWeight: 600, cursor: 'pointer' }}
            >OK</button>
          </div>
        </div>
      )}
    </>
  )
}

// Unlimited % input — no min or max cap, negative values allowed
function PctInput({ value, onChange, placeholder = '0', color = theme.textPrimary, width = 60 }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 3 }}>
      <input
        type="number"
        step="0.5"
        placeholder={placeholder}
        value={value}
        onChange={e => onChange(e.target.value)}
        style={{
          width, background: theme.surfaceUp, color,
          border: `1px solid ${theme.border}`, borderRadius: 6,
          padding: '3px 6px', fontSize: 12, fontFamily: theme.fontMono,
          textAlign: 'right', outline: 'none',
        }}
      />
      <span style={{ fontSize: 11, color: theme.textMuted }}>%</span>
    </div>
  )
}

// Upgrade old {ref_dept, alloc_pct} format to new split-field format
function upgradeMapping(m) {
  const out = {}
  for (const [div, entries] of Object.entries(m || {})) {
    out[div] = {}
    for (const [dept, cfg] of Object.entries(entries || {})) {
      if ('alloc_pct' in cfg && !('new_dept_pct' in cfg)) {
        out[div][dept] = {
          ref_dept: cfg.ref_dept,
          new_dept_pct: cfg.alloc_pct,
          ref_reduction_pct: cfg.alloc_pct,
        }
      } else {
        out[div][dept] = cfg
      }
    }
  }
  return out
}

export default function NewDeptPlan() {
  const [activeDiv, setActiveDiv]    = useState('KIDS')
  const [mapping, setMapping]        = useState({})
  const [existingDepts, setExisting] = useState({})
  const [preview, setPreview]        = useState(null)
  const [tyMonths, setTyMonths]      = useState([])
  const [loading, setLoading]        = useState(true)
  const [saving, setSaving]          = useState(false)
  const [saveMsg, setSaveMsg]        = useState('')
  const [adding, setAdding]          = useState(false)
  const [draft, setDraft]            = useState({ new_dept: '', ref_dept: '', new_dept_pct: '', ref_reduction_pct: '' })
  const [draftErr, setDraftErr]      = useState('')
  const [refFilter, setRefFilter]    = useState(new Set())
  const [planFinalized, setPlanFinalized] = useState(false)
  const [showStorePlan, setShowStorePlan] = useState(false)
  const [syncStatus, setSyncStatus]       = useState(null)
  const [syncing, setSyncing]             = useState(false)
  const [syncMsg, setSyncMsg]             = useState('')
  const navigate = useNavigate()
  const inPipeline = currentEngineKey() === 'new-depts'

  const fetchSyncStatus = useCallback(async () => {
    try {
      const r = await fetch('/api/planning/dept-sales/new-depts/sync-status')
      setSyncStatus(await r.json())
    } catch {}
  }, [])

  const handleSync = async () => {
    setSyncing(true); setSyncMsg('')
    try {
      const r = await fetch('/api/planning/dept-sales/new-depts/sync', { method: 'POST' })
      const d = await r.json()
      if (d.ok) {
        setSyncMsg(`Synced — ${d.total_entries} entries across ${d.divisions.join(', ')}`)
        await fetchMapping()
        await fetchPreview()
        setPlanFinalized(d.plan_regenerated !== false)
      } else {
        setSyncMsg(d.detail || 'Sync failed')
      }
    } catch (e) {
      setSyncMsg('Sync error: ' + e.message)
    } finally {
      setSyncing(false)
      setTimeout(() => setSyncMsg(''), 6000)
    }
  }

  const fetchDepts = useCallback(async () => {
    try {
      const r = await fetch('/api/planning/dept-sales/actuals/status')
      setTyMonths((await r.json()).available_ty_months || [])
    } catch {}
    try {
      const r = await fetch('/api/planning/department-plan/config')
      const data = await r.json()
      const out = {}
      for (const [div, rows] of Object.entries(data.divisions || {}))
        out[div] = rows.map(r => r.name).sort()
      setExisting(out)
    } catch {}
  }, [])

  const fetchMapping = useCallback(async () => {
    try {
      const r = await fetch('/api/planning/dept-sales/new-depts')
      setMapping(upgradeMapping(await r.json()))
    } finally { setLoading(false) }
  }, [])

  const fetchPreview = useCallback(async () => {
    try {
      const r = await fetch('/api/planning/dept-sales/run')
      setPreview(await r.json())
    } catch {}
  }, [])

  useEffect(() => {
    fetchSyncStatus()
    Promise.all([fetchDepts(), fetchMapping()]).then(() => fetchPreview())
  }, [fetchDepts, fetchMapping, fetchPreview, fetchSyncStatus])

  const aggTY = useCallback((deptName) => {
    const out = {}
    for (const ty of tyMonths) out[ty] = 0
    for (const sdata of Object.values(preview?.stores || {})) {
      const months = sdata.divisions?.[activeDiv]?.months || {}
      for (const ty of tyMonths) {
        const dv = months[ty]?.departments?.[deptName]
        if (dv) out[ty] = (out[ty] || 0) + (dv.ty || 0)
      }
    }
    return out
  }, [preview, activeDiv, tyMonths])

  const divMonthTotal = useCallback((ty) => {
    let t = 0
    for (const sdata of Object.values(preview?.stores || {}))
      t += sdata.divisions?.[activeDiv]?.months?.[ty]?.div_total_ty || 0
    return t
  }, [preview, activeDiv])

  const avgContPct = useCallback((deptName) => {
    let sumTY = 0, sumDiv = 0
    for (const ty of tyMonths) {
      sumTY  += aggTY(deptName)[ty] || 0
      sumDiv += divMonthTotal(ty)
    }
    return sumDiv > 0 ? (sumTY / sumDiv * 100) : 0
  }, [aggTY, divMonthTotal, tyMonths])

  const handleClear = async () => {
    if (!window.confirm('Clear all new department entries and remove the generated plan? This cannot be undone.')) return
    try {
      const r = await fetch('/api/planning/dept-sales/new-depts', { method: 'DELETE' })
      const d = await r.json()
      if (d.ok) {
        setMapping({})
        setPlanFinalized(false)
        setPreview(null)
        setSaveMsg(`Cleared — ${d.cleared.length} file(s) removed`)
        setTimeout(() => setSaveMsg(''), 4000)
      }
    } catch {
      setSaveMsg('Error clearing')
    }
  }

  const handleSave = async () => {
    setSaving(true); setSaveMsg('')
    try {
      const r = await fetch('/api/planning/dept-sales/new-depts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(mapping),
      })
      const d = await r.json()
      if (d.ok) {
        setPlanFinalized(d.plan_finalized !== false)
        if (inPipeline) {
          navigate(advancePipeline())
          return
        }
        setSaveMsg(`Saved & finalized — ${d.saved} entr${d.saved === 1 ? 'y' : 'ies'}`)
        await fetchPreview()
      } else {
        setSaveMsg(d.detail || 'Error')
      }
    } finally {
      setSaving(false)
      setTimeout(() => setSaveMsg(''), 4000)
    }
  }

  const handleAddRow = () => {
    setDraftErr('')
    const nd  = draft.new_dept.trim().toUpperCase()
    const rd  = draft.ref_dept.trim().toUpperCase()
    const ndp = parseFloat(draft.new_dept_pct)
    const rrd = parseFloat(draft.ref_reduction_pct)
    if (!nd)  return setDraftErr('New dept name is required')
    if (!rd)  return setDraftErr('Reference dept is required')
    if (isNaN(ndp)) return setDraftErr('New Dept % must be a number')
    if (isNaN(rrd)) return setDraftErr('Ref Dept % must be a number')
    if (nd === rd) return setDraftErr('New dept and reference dept cannot be the same')
    if ((existingDepts[activeDiv] || []).includes(nd))
      return setDraftErr(`${nd} already has LY actuals — only truly new depts belong here`)
    setMapping(prev => ({
      ...prev,
      [activeDiv]: { ...(prev[activeDiv] || {}), [nd]: { ref_dept: rd, new_dept_pct: ndp, ref_reduction_pct: rrd } },
    }))
    setDraft({ new_dept: '', ref_dept: '', new_dept_pct: '', ref_reduction_pct: '' })
    setAdding(false)
  }

  const handleDelete = (dept) => {
    setMapping(prev => {
      const next = { ...prev, [activeDiv]: { ...(prev[activeDiv] || {}) } }
      delete next[activeDiv][dept]
      return next
    })
  }

  const setEntryField = (dept, field, val) =>
    setMapping(prev => ({
      ...prev,
      [activeDiv]: {
        ...(prev[activeDiv] || {}),
        [dept]: { ...(prev[activeDiv]?.[dept] || {}), [field]: isNaN(parseFloat(val)) ? 0 : parseFloat(val) },
      },
    }))

  const allEntries      = Object.entries(mapping[activeDiv] || {})
  const uniqueRefDepts  = [...new Set(allEntries.map(([, cfg]) => cfg.ref_dept).filter(Boolean))].sort()
  const entries         = refFilter.size === 0
    ? allEntries
    : allEntries.filter(([, cfg]) => refFilter.has(cfg.ref_dept))

  if (loading) return <div style={{ padding: 40, color: theme.textSecondary }}>Loading…</div>

  return (
    <div style={{ padding: '32px 36px', maxWidth: 1700 }}>
      {inPipeline && <PipelineBanner currentKey="new-depts" />}
      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <div style={{ fontSize: 22, fontWeight: 700, color: theme.textPrimary, letterSpacing: -0.3 }}>
          New Department Plan
        </div>
        <div style={{ fontSize: 13, color: theme.textSecondary, marginTop: 4 }}>
          Define new depts (MCs) introduced in TY, link each to a reference dept, and set the reallocation percentages independently. Results flow into Post New MCs AOP.
        </div>
      </div>

      {/* Sync from folder panel */}
      <div style={{
        background: theme.surface, border: `1px solid ${theme.border}`,
        borderRadius: 10, padding: '16px 20px', marginBottom: 20,
        display: 'flex', alignItems: 'center', gap: 20, flexWrap: 'wrap',
      }}>
        <div style={{ flex: 1, minWidth: 240 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: theme.textPrimary, marginBottom: 4 }}>
            Sync from Folder
          </div>
          <div style={{ fontSize: 11, color: theme.textMuted, fontFamily: theme.fontMono }}>
            {syncStatus?.path || '…'}
          </div>
          {syncStatus && (
            <div style={{ fontSize: 11, color: theme.textSecondary, marginTop: 3 }}>
              {syncStatus.file_found
                ? `File found · ${syncStatus.file_date} · ${syncStatus.size_kb} KB`
                : 'File not found — drop NEW Departments.xlsx in the folder above'}
            </div>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button
            onClick={fetchSyncStatus}
            style={{
              padding: '6px 14px', borderRadius: 7, fontSize: 12, fontWeight: 500,
              background: 'none', color: theme.textSecondary,
              border: `1px solid ${theme.border}`, cursor: 'pointer',
            }}
          >Refresh</button>
          <button
            onClick={handleSync}
            disabled={syncing || !syncStatus?.file_found}
            style={{
              padding: '6px 18px', borderRadius: 7, fontSize: 12, fontWeight: 600,
              background: syncStatus?.file_found ? '#A8CBB7' : theme.border,
              color: syncStatus?.file_found ? '#1F4D3A' : theme.textMuted,
              border: 'none', cursor: (syncing || !syncStatus?.file_found) ? 'default' : 'pointer',
              opacity: syncing ? 0.7 : 1,
            }}
          >{syncing ? 'Syncing…' : 'Sync from Folder'}</button>
        </div>
        {syncMsg && (
          <div style={{ width: '100%', fontSize: 12, color: theme.accent, fontWeight: 600, marginTop: 4 }}>
            {syncMsg}
          </div>
        )}
      </div>

      {/* Division tabs + Save */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 16, flexWrap: 'wrap' }}>
        {DIVISIONS.map(div => {
          const active = div === activeDiv
          const c      = DIV_COLOR[div]
          const count  = Object.keys(mapping[div] || {}).length
          return (
            <button
              key={div}
              onClick={() => { setActiveDiv(div); setAdding(false); setDraftErr(''); setRefFilter(new Set()) }}
              style={{
                padding: '7px 18px', borderRadius: 8,
                border: `1.5px solid ${active ? c : theme.border}`,
                background: active ? `${c}22` : theme.surface,
                color: active ? c : theme.textSecondary,
                fontWeight: active ? 700 : 500, fontSize: 13, cursor: 'pointer',
                display: 'flex', alignItems: 'center', gap: 8,
              }}
            >
              {div}
              {count > 0 && (
                <span style={{
                  fontSize: 10, fontWeight: 700,
                  background: active ? c : theme.border,
                  color: active ? '#fff' : theme.textSecondary,
                  borderRadius: 10, padding: '1px 6px',
                }}>{count}</span>
              )}
            </button>
          )
        })}
        <div style={{ flex: 1 }} />
        <button
          onClick={handleClear}
          style={{
            padding: '7px 16px', borderRadius: 8,
            background: 'none', color: theme.textMuted,
            border: `1px solid ${theme.border}`, fontWeight: 500, fontSize: 13, cursor: 'pointer',
          }}
        >Clear</button>
        <button
          onClick={handleSave} disabled={saving}
          style={{
            padding: '7px 20px', borderRadius: 8,
            background: '#A8CBB7', color: '#1F4D3A',
            border: 'none', fontWeight: 600, fontSize: 13,
            cursor: saving ? 'default' : 'pointer', opacity: saving ? 0.7 : 1,
          }}
        >{saving ? 'Saving…' : 'Save & Apply'}</button>
        {saveMsg && (
          <span style={{ alignSelf: 'center', fontSize: 12, color: theme.accent, fontWeight: 600 }}>
            {saveMsg}
          </span>
        )}
      </div>

      {/* Filter bar — above table, pivot-style multi-select by ref dept */}
      {uniqueRefDepts.length > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
          <span style={{ fontSize: 11, color: theme.textMuted, fontWeight: 600, letterSpacing: 0.5 }}>
            FILTER:
          </span>
          <PivotFilter
            label="Reference Dept"
            options={uniqueRefDepts}
            selected={refFilter}
            onChange={setRefFilter}
          />
          {refFilter.size > 0 && refFilter.size < uniqueRefDepts.length && (
            <button
              onClick={() => setRefFilter(new Set())}
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                fontSize: 11, color: theme.textMuted, textDecoration: 'underline', padding: 0,
              }}
            >
              Clear filter
            </button>
          )}
        </div>
      )}

      {/* Info note */}
      <div style={{
        background: theme.surface, border: `1px solid ${theme.border}`,
        borderRadius: 10, padding: '12px 18px', marginBottom: 20,
        display: 'flex', gap: 12, alignItems: 'flex-start',
      }}>
        <span style={{ fontSize: 16, marginTop: 1 }}>ℹ️</span>
        <div style={{ fontSize: 12.5, color: theme.textSecondary, lineHeight: 1.6 }}>
          <strong style={{ color: theme.textPrimary }}>How it works:</strong>{' '}
          <strong style={{ color: theme.accent }}>New Dept %</strong> — share of the reference dept's TY that goes to the new dept (e.g. 20% of ref TY).{' '}
          <strong style={{ color: theme.danger }}>Ref Dept %</strong> — how much the reference dept's AOP independently reduces (e.g. ref loses 7% of its own value). These two are <em>independent</em> — values above 100% are allowed. Final output is the <strong style={{ color: theme.accent }}>Post New MCs AOP</strong>.
        </div>
      </div>

      {/* Table */}
      <div style={{
        background: theme.surface, border: `1px solid ${theme.border}`,
        borderRadius: 12, overflow: 'visible',
      }}>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 1050 }}>
            <thead>
              <tr style={{ background: theme.surfaceUp, borderBottom: `1px solid ${theme.border}` }}>
                {[
                  ['NEW DEPARTMENT', 'left', 160],
                  ['REFERENCE DEPT', 'left', 230],
                  ['NEW DEPT %', 'right', 105],
                  ['REF DEPT %', 'right', 105],
                  ['CONT %', 'right', 90],
                  ...tyMonths.map(m => [m, 'right', 85]),
                  ['POST NEW MCs AOP', 'right', 130],
                  ['', 'center', 40],
                ].map(([label, align, w]) => (
                  <th key={label} style={{
                    ...CELL, textAlign: align, padding: '10px 12px',
                    color: theme.textSecondary, fontWeight: 600, fontSize: 11,
                    letterSpacing: 0.5, minWidth: w,
                    borderRight: label === 'CONT %' ? `1px solid ${theme.borderStrong}` : 'none',
                  }}>{label}</th>
                ))}
              </tr>
            </thead>

            <tbody>
              {entries.length === 0 && !adding && (
                <tr>
                  <td colSpan={8 + tyMonths.length} style={{
                    padding: '32px 20px', textAlign: 'center',
                    color: theme.textMuted, fontSize: 13,
                  }}>
                    {refFilter.size > 0 && refFilter.size < uniqueRefDepts.length
                      ? 'No entries match the current filter.'
                      : `No new departments defined for ${activeDiv}. Click "+ Add Dept" to start.`
                    }
                  </td>
                </tr>
              )}

              {entries.map(([newDept, cfg], idx) => {
                const refDept         = cfg.ref_dept
                const newDeptPct      = parseFloat(cfg.new_dept_pct) || 0
                const refReductionPct = parseFloat(cfg.ref_reduction_pct) || 0
                const newTY           = aggTY(newDept)
                const refTY           = aggTY(refDept)
                const newTotal        = tyMonths.reduce((s, m) => s + (newTY[m] || 0), 0)
                const refTotal        = tyMonths.reduce((s, m) => s + (refTY[m] || 0), 0)
                const refContPct      = avgContPct(refDept)
                const isEven          = idx % 2 === 0
                const stripeBg        = isEven ? 'transparent' : 'rgba(0,0,0,0.06)'

                return [
                  <tr key={`new-${newDept}`} style={{ background: stripeBg, borderBottom: `1px solid ${theme.border}18` }}>
                    <td style={{ padding: '9px 12px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{
                          fontSize: 9, fontWeight: 700, letterSpacing: 0.5,
                          background: '#ECFDF3', color: theme.accent,
                          borderRadius: 4, padding: '2px 6px', flexShrink: 0,
                        }}>NEW</span>
                        <span style={{ fontFamily: theme.fontMono, fontSize: 12.5, color: theme.textPrimary, fontWeight: 600 }}>
                          {newDept}
                        </span>
                      </div>
                    </td>

                    <td style={{ padding: '9px 12px' }}>
                      <PivotSelect
                        options={existingDepts[activeDiv] || []}
                        value={refDept}
                        onChange={v => setEntryField(newDept, 'ref_dept', v)}
                      />
                    </td>

                    {/* New Dept % — editable, accent colour */}
                    <td style={{ ...CELL }}>
                      <PctInput
                        value={newDeptPct || ''}
                        onChange={v => setEntryField(newDept, 'new_dept_pct', v)}
                        color={theme.accent}
                      />
                    </td>

                    {/* Ref Dept % — editable, danger colour */}
                    <td style={{ ...CELL }}>
                      <PctInput
                        value={refReductionPct || ''}
                        onChange={v => setEntryField(newDept, 'ref_reduction_pct', v)}
                        color={theme.danger}
                      />
                    </td>

                    {/* Cont % — blank for new dept */}
                    <td style={{ ...CELL, borderRight: `1px solid ${theme.borderStrong}`, color: theme.textMuted }}>—</td>

                    {tyMonths.map(m => (
                      <td key={m} style={{ ...CELL, color: theme.accent }}>
                        {(newTY[m] || 0).toFixed(2)}
                      </td>
                    ))}

                    <td style={{ ...CELL, color: theme.accent, fontWeight: 700 }}>
                      {newTotal.toFixed(2)}
                    </td>
                    <td style={{ padding: '9px 8px', textAlign: 'center' }}>
                      <button
                        onClick={() => handleDelete(newDept)}
                        title="Remove"
                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: theme.danger, fontSize: 15, lineHeight: 1, padding: '2px 6px', borderRadius: 4 }}
                      >×</button>
                    </td>
                  </tr>,

                  <tr key={`ref-${newDept}`} style={{ background: isEven ? 'rgba(0,0,0,0.04)' : 'rgba(0,0,0,0.1)', borderBottom: `1px solid ${theme.border}` }}>
                    <td style={{ padding: '6px 12px 6px 22px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                        <span style={{ fontSize: 10, color: theme.textMuted, flexShrink: 0 }}>↑ REF</span>
                        <span style={{ fontFamily: theme.fontMono, fontSize: 12, color: theme.textSecondary }}>
                          {refDept}
                        </span>
                      </div>
                    </td>
                    <td style={{ padding: '6px 12px', fontSize: 11, color: theme.textMuted, fontStyle: 'italic' }}>adjusted</td>

                    {/* New Dept % — blank for ref row */}
                    <td style={{ ...CELL, color: theme.textMuted }}>—</td>

                    {/* Ref Dept % — read-only with minus badge */}
                    <td style={{ ...CELL, fontSize: 11 }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 5 }}>
                        <span style={{ fontFamily: theme.fontMono, fontSize: 12, color: theme.danger, fontWeight: 600 }}>
                          {refReductionPct}%
                        </span>
                        <span style={{
                          fontSize: 9, fontWeight: 700, letterSpacing: 0.3,
                          background: 'rgba(248,113,113,0.12)', color: theme.danger,
                          borderRadius: 4, padding: '1px 5px',
                        }}>−</span>
                      </div>
                    </td>

                    {/* Cont % — ref dept's adjusted share */}
                    <td style={{ ...CELL, borderRight: `1px solid ${theme.borderStrong}`, color: theme.textSecondary, fontWeight: 600, fontSize: 11 }}>
                      {refContPct.toFixed(2)}%
                    </td>

                    {tyMonths.map(m => (
                      <td key={m} style={{ ...CELL, color: theme.textSecondary, fontSize: 11 }}>
                        {(refTY[m] || 0).toFixed(2)}
                      </td>
                    ))}

                    <td style={{ ...CELL, color: theme.textSecondary, fontWeight: 600, fontSize: 11 }}>
                      {refTotal.toFixed(2)}
                    </td>
                    <td />
                  </tr>,
                ]
              })}

              {/* Draft add-row form */}
              {adding && (
                <tr style={{ background: `__TPL<'#A8CBB7'>__0D`, borderBottom: `1px solid ${theme.border}` }}>
                  <td style={{ padding: '10px 12px' }}>
                    <input
                      autoFocus
                      placeholder="NEW_DEPT_CODE"
                      value={draft.new_dept}
                      onChange={e => setDraft(d => ({ ...d, new_dept: e.target.value.toUpperCase() }))}
                      style={{
                        background: theme.surfaceUp, color: theme.textPrimary,
                        border: `1px solid ${theme.border}`, borderRadius: 6,
                        padding: '5px 10px', fontSize: 12, fontFamily: theme.fontMono, width: 160,
                        outline: 'none',
                      }}
                    />
                  </td>
                  <td style={{ padding: '10px 12px' }}>
                    <PivotSelect
                      options={existingDepts[activeDiv] || []}
                      value={draft.ref_dept}
                      onChange={v => setDraft(d => ({ ...d, ref_dept: v }))}
                    />
                  </td>
                  <td style={{ ...CELL }}>
                    <PctInput
                      value={draft.new_dept_pct}
                      onChange={v => setDraft(d => ({ ...d, new_dept_pct: v }))}
                      placeholder="20"
                      color={theme.accent}
                    />
                  </td>
                  <td style={{ ...CELL }}>
                    <PctInput
                      value={draft.ref_reduction_pct}
                      onChange={v => setDraft(d => ({ ...d, ref_reduction_pct: v }))}
                      placeholder="7"
                      color={theme.danger}
                    />
                  </td>
                  <td style={{ borderRight: `1px solid ${theme.borderStrong}` }} />
                  <td colSpan={tyMonths.length + 1} style={{ padding: '10px 12px' }}>
                    {draftErr && <span style={{ fontSize: 11, color: theme.danger }}>{draftErr}</span>}
                  </td>
                  <td style={{ padding: '10px 8px', whiteSpace: 'nowrap' }}>
                    <button
                      onClick={handleAddRow}
                      style={{ background: theme.accent, color: '#fff', border: 'none', borderRadius: 6, padding: '4px 12px', fontSize: 12, fontWeight: 600, cursor: 'pointer', marginRight: 6 }}
                    >Add</button>
                    <button
                      onClick={() => { setAdding(false); setDraftErr('') }}
                      style={{ background: 'none', color: theme.textMuted, border: 'none', borderRadius: 6, padding: '4px 8px', fontSize: 12, cursor: 'pointer' }}
                    >Cancel</button>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Footer */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 16,
          padding: '12px 14px', borderTop: `1px solid ${theme.border}`,
          background: theme.surfaceUp,
        }}>
          <button
            onClick={() => { setAdding(true); setDraftErr('') }}
            disabled={adding}
            style={{
              padding: '6px 14px', borderRadius: 7,
              background: 'none', border: `1.5px dashed ${theme.border}`,
              color: theme.textSecondary, fontSize: 12.5,
              cursor: adding ? 'default' : 'pointer', fontWeight: 500,
            }}
          >+ Add Dept</button>

          {allEntries.length > 0 && (() => {
            const totalNewAOP = allEntries.reduce((sum, [nd]) => {
              return sum + tyMonths.reduce((s, m) => s + (aggTY(nd)[m] || 0), 0)
            }, 0)
            return (
              <span style={{ fontSize: 11.5, color: theme.textMuted }}>
                {allEntries.length} new dept{allEntries.length > 1 ? 's' : ''} in {activeDiv}
                {tyMonths.length > 0 && (
                  <> · Post New MCs AOP: <strong style={{ color: theme.accent }}>₹{totalNewAOP.toFixed(2)}L</strong></>
                )}
                {refFilter.size > 0 && refFilter.size < uniqueRefDepts.length && (
                  <span style={{ color: theme.primary }}> · {entries.length} shown (filtered)</span>
                )}
              </span>
            )
          })()}
        </div>
      </div>

      {/* Final plan status + store-level breakdown */}
      {planFinalized && preview && allEntries.length > 0 && (() => {
        const activeDepts = [...new Set(allEntries.flatMap(([nd, cfg]) => [nd, cfg.ref_dept]).filter(Boolean))]

        // Build store rows: store → dept → {ly, ty} per month
        const storeRows = []
        for (const [store, sdata] of Object.entries(preview.stores || {})) {
          const divData = sdata.divisions?.[activeDiv]
          if (!divData) continue
          const row = { store, isSSG: sdata.is_ssg, depts: {} }
          let hasAny = false
          for (const dept of activeDepts) {
            const deptTotals = { ly: 0, ty: 0 }
            for (const ty of tyMonths) {
              const d = divData.months?.[ty]?.departments?.[dept]
              if (d) { deptTotals.ly += d.ly || 0; deptTotals.ty += d.ty || 0 }
            }
            row.depts[dept] = deptTotals
            if (deptTotals.ty > 0 || deptTotals.ly > 0) hasAny = true
          }
          if (hasAny) storeRows.push(row)
        }
        storeRows.sort((a, b) => (b.isSSG ? 1 : 0) - (a.isSSG ? 1 : 0))

        return (
          <div style={{ marginTop: 20 }}>
            {/* Finalized banner */}
            <div style={{
              background: 'rgba(16,185,129,0.08)', border: '1px solid rgba(16,185,129,0.25)',
              borderRadius: 10, padding: '12px 18px', marginBottom: 16,
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            }}>
              <div>
                <span style={{ fontSize: 13, fontWeight: 700, color: theme.accent }}>
                  ✓ Department Plan Finalized — Post New MCs AOP
                </span>
                <span style={{ fontSize: 12, color: theme.textSecondary, marginLeft: 12 }}>
                  {activeDiv} · {allEntries.length} new dept{allEntries.length > 1 ? 's' : ''} · {storeRows.length} stores
                </span>
              </div>
              <button
                onClick={() => setShowStorePlan(p => !p)}
                style={{
                  padding: '5px 14px', borderRadius: 6, fontSize: 12, fontWeight: 600,
                  background: showStorePlan ? theme.surfaceUp : theme.accent,
                  color: showStorePlan ? theme.textSecondary : '#fff',
                  border: `1px solid ${showStorePlan ? theme.border : 'transparent'}`,
                  cursor: 'pointer',
                }}
              >
                {showStorePlan ? 'Hide' : 'View Store-Level Plan'}
              </button>
            </div>

            {/* Store × Dept breakdown */}
            {showStorePlan && (
              <div style={{
                background: theme.surface, border: `1px solid ${theme.border}`,
                borderRadius: 12, overflow: 'hidden',
              }}>
                <div style={{
                  padding: '12px 16px', background: theme.surfaceUp,
                  borderBottom: `1px solid ${theme.border}`,
                  display: 'flex', alignItems: 'center', gap: 12,
                }}>
                  <span style={{ fontSize: 13, fontWeight: 700, color: theme.textPrimary }}>
                    Final Plan — {activeDiv} — Store × Department
                  </span>
                  <span style={{ fontSize: 11, color: theme.textMuted }}>
                    Post New MCs AOP · TY values in ₹L · {storeRows.length} stores
                  </span>
                </div>
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 600 }}>
                    <thead>
                      <tr style={{ background: theme.surfaceUp, borderBottom: `1px solid ${theme.border}` }}>
                        <th style={{ ...CELL, textAlign: 'left', padding: '8px 12px', fontSize: 11, color: theme.textSecondary, fontWeight: 600, letterSpacing: 0.5, minWidth: 140 }}>STORE</th>
                        <th style={{ ...CELL, textAlign: 'left', padding: '8px 12px', fontSize: 11, color: theme.textSecondary, fontWeight: 600, letterSpacing: 0.5, minWidth: 60 }}>TYPE</th>
                        {activeDepts.map(dept => {
                          const isNew = allEntries.some(([nd]) => nd === dept)
                          return (
                            <th key={dept} style={{ ...CELL, padding: '8px 10px', fontSize: 10, fontWeight: 600, letterSpacing: 0.4, minWidth: 110, color: isNew ? theme.accent : theme.danger }}>
                              {isNew ? '▲' : '▼'} {dept}
                            </th>
                          )
                        })}
                      </tr>
                    </thead>
                    <tbody>
                      {storeRows.map((row, i) => (
                        <tr key={row.store} style={{ borderBottom: `1px solid ${theme.border}18`, background: i % 2 === 0 ? 'transparent' : 'rgba(0,0,0,0.04)' }}>
                          <td style={{ padding: '6px 12px', fontFamily: theme.fontMono, fontSize: 12, color: theme.textPrimary, fontWeight: 600 }}>
                            {row.store}
                          </td>
                          <td style={{ padding: '6px 12px' }}>
                            <span style={{
                              fontSize: 9, fontWeight: 700, letterSpacing: 0.4, borderRadius: 4, padding: '2px 5px',
                              background: row.isSSG ? 'rgba(16,185,129,0.12)' : 'rgba(99,102,241,0.12)',
                              color: row.isSSG ? theme.accent : '#4338CA',
                            }}>{row.isSSG ? (row.store === 'ANG' ? 'SSG - ANG' : 'SSG') : 'NSO'}</span>
                          </td>
                          {activeDepts.map(dept => {
                            const d = row.depts[dept] || { ty: 0 }
                            const isNew = allEntries.some(([nd]) => nd === dept)
                            return (
                              <td key={dept} style={{ ...CELL, fontSize: 11, color: isNew ? theme.accent : theme.textSecondary }}>
                                {d.ty.toFixed(2)}
                              </td>
                            )
                          })}
                        </tr>
                      ))}
                    </tbody>
                    <tfoot>
                      <tr style={{ borderTop: `1px solid ${theme.borderStrong}`, background: theme.surfaceUp }}>
                        <td style={{ padding: '7px 12px', fontSize: 12, fontWeight: 700, color: theme.textPrimary }} colSpan={2}>ALL STORES</td>
                        {activeDepts.map(dept => {
                          const total = storeRows.reduce((s, r) => s + (r.depts[dept]?.ty || 0), 0)
                          const isNew = allEntries.some(([nd]) => nd === dept)
                          return (
                            <td key={dept} style={{ ...CELL, fontWeight: 700, fontSize: 12, color: isNew ? theme.accent : theme.danger }}>
                              {total.toFixed(2)}
                            </td>
                          )
                        })}
                      </tr>
                    </tfoot>
                  </table>
                </div>
              </div>
            )}
          </div>
        )
      })()}
    </div>
  )
}
