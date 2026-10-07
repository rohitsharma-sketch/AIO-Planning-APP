import React, { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { theme, alpha } from '../theme'
import PipelineBanner from '../components/PipelineBanner'
import { currentEngineKey, advancePipeline } from '../pipelineState'

const DIVISIONS = ['KIDS', 'LADIES', 'MENS', 'GM', 'RETAIL']

const DIV_COLOR = {
  KIDS: '#C85A12', LADIES: '#7420B8', MENS: '#077A4A', GM: '#1E54C0', RETAIL: '#B22620',
}

const ATTR_COLOR = {
  SUMMER:    '#B45309',
  REGULAR:   '#38BDF8',
  PREWINTER: '#15803D',
  OCCASIONAL:'#7E22CE',
  'LT WINTER':'#67E8F9',
  'HVY WINTER':'#2563EB',
  GM:        '#94A3B8',
  RETAIL:    '#FB7185',
}

const CELL = { fontFamily: theme.fontMono, fontSize: 12, textAlign: 'right', padding: '5px 10px', whiteSpace: 'nowrap' }
const HDR  = { ...CELL, fontSize: 11, color: theme.textMuted, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.4 }

// The month's division AOP (the cap) shared out over the attributes after one of them is set to `newVal`: locked
// attributes keep their value, the other unlocked ones move pro-rata, and the result always adds back to the cap
// exactly (the remainder lands on the largest part). (user, 2026-10-01: "a column for every attribute and re-apportion
// according to the changes made against it. It should always be capped to the division AOP.")
export function reapportionToCap(values, cap, changed, newVal, locked) {
  const out = { ...values }
  const others = Object.keys(out).filter(a => a !== changed)
  const lockedSum = others.filter(a => locked.has(a)).reduce((s, a) => s + out[a], 0)
  const free = others.filter(a => !locked.has(a))
  const room = Math.max(cap - lockedSum, 0)
  out[changed] = free.length ? Math.min(Math.max(newVal, 0), room) : room   // nothing to absorb: it is what's left
  const rest = room - out[changed]
  const cur = free.reduce((s, a) => s + out[a], 0)
  free.forEach(a => { out[a] = cur > 0 ? out[a] / cur * rest : rest / free.length })
  const big = Object.keys(out).reduce((b, a) => (Math.abs(out[a]) > Math.abs(out[b] ?? 0) ? a : b), changed)
  out[big] += cap - Object.values(out).reduce((s, v) => s + v, 0)
  return out
}

function AttributeAopWindow({ div, attrs, months, data, getContPct, isLocked, onSetMonth, color, isWorking, onToggleWork }) {
  const shown = attrs.filter(a => isWorking(div, a))
  const held = attrs.filter(a => !isWorking(div, a))
  const capOf = m => attrs.reduce((s, a) => s + (data?.[div]?.[a]?.[m]?.ty ?? 0), 0)
  const valOf = (a, m) => getContPct(div, a, m) / 100 * capOf(m)
  const [draft, setDraft] = useState({})   // the cell being typed in, so typing isn't fought by re-renders
  const commit = (a, m, raw) => {
    setDraft({})
    const v = parseFloat(raw)
    if (isNaN(v)) return
    const cap = capOf(m)
    if (cap <= 0) return
    const cur = Object.fromEntries(attrs.map(x => [x, valOf(x, m)]))
    const vals = reapportionToCap(cur, cap, a, v, new Set(attrs.filter(x => isLocked(div, x))))
    const pct = Object.fromEntries(attrs.map(x => [x, vals[x] / cap * 100]))
    const big = attrs.reduce((b, x) => (pct[x] > pct[b] ? x : b), attrs[0])
    pct[big] += 100 - Object.values(pct).reduce((t, x) => t + x, 0)   // the % add to exactly 100
    onSetMonth(m, pct)
  }
  const f2 = v => v.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  const season = a => months.reduce((t, m) => t + valOf(a, m), 0)
  const seasonCap = months.reduce((t, m) => t + capOf(m), 0)
  const TH = { ...HDR, padding: '8px 10px', borderBottom: `1px solid ${theme.border}`, background: theme.surfaceAlt }
  return (
    <div style={{ background: theme.surface, borderRadius: 12, border: `1px solid ${theme.border}`, overflow: 'hidden', marginBottom: 20 }}>
      <div style={{ padding: '12px 16px', borderBottom: `1px solid ${theme.border}`, display: 'flex', gap: 10, alignItems: 'baseline', flexWrap: 'wrap' }}>
        <span style={{ fontSize: 14, fontWeight: 700, color: theme.textPrimary }}>AOP by attribute — {div}</span>
        <span style={{ fontSize: 11.5, color: theme.textMuted }}>
          ₹ L · SSG stores, departments with an ATTRIBUTE1. Type an attribute's new AOP for a month: the other unlocked
          attributes re-apportion pro-rata and the month stays exactly on the division AOP (the cap). Locked (🔒) attributes don't move.
        </span>
      </div>
      <div style={{ padding: '10px 16px', borderBottom: `1px solid ${theme.border}`, display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
        <span style={{ fontSize: 11.5, color: theme.textSecondary, fontWeight: 600, marginRight: 4 }}>Work on:</span>
        {attrs.map(a => {
          const on = isWorking(div, a), ac = ATTR_COLOR[a] || theme.textMuted
          return (
            <button key={a} onClick={() => onToggleWork(div, a)} title={on ? 'Click to hold it out - it and its departments keep their AOP' : 'Click to work on it'}
              style={{ fontSize: 11.5, fontWeight: 600, padding: '3px 10px', borderRadius: 14, cursor: 'pointer',
                       border: `1px solid ${on ? ac : theme.border}`, background: on ? `${alpha(ac, '22')}` : 'none',
                       color: on ? ac : theme.textMuted, textDecoration: on ? 'none' : 'line-through' }}>
              {on ? '✓ ' : ''}{a}
            </button>
          )
        })}
        {held.length > 0 && <span style={{ fontSize: 11, color: theme.textMuted, marginLeft: 6 }}>
          Held out: {held.join(', ')} - they and their departments keep their AOP (even with LY sales); the rest share what's left of the cap.</span>}
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 12 }}>
          <thead>
            <tr>
              <th style={{ ...TH, textAlign: 'left', position: 'sticky', left: 0, zIndex: 2 }}>Month</th>
              <th style={{ ...TH, color }}>Division AOP (cap)</th>
              {held.length > 0 && <th style={{ ...TH, borderLeft: `1px solid ${theme.border}` }}>Held (not selected)</th>}
              {shown.map(a => (
                <th key={a} style={{ ...TH, color: ATTR_COLOR[a] || theme.textMuted, borderLeft: `1px solid ${theme.border}` }}>
                  {a}{isLocked(div, a) ? ' 🔒' : ''}
                </th>
              ))}
              <th style={{ ...TH, borderLeft: `2px solid ${theme.border}` }}>Σ attributes</th>
              <th style={{ ...TH }}>Σ − cap</th>
            </tr>
          </thead>
          <tbody>
            {months.map((m, mi) => {
              const cap = capOf(m)
              const sum = attrs.reduce((t, a) => t + valOf(a, m), 0)
              return (
                <tr key={m} style={{ borderBottom: `1px solid ${theme.border}`, background: mi % 2 ? theme.surfaceAlt : 'transparent' }}>
                  <td style={{ ...CELL, textAlign: 'left', fontWeight: 600, color: theme.textPrimary, position: 'sticky', left: 0, background: mi % 2 ? theme.surfaceAlt : theme.surface }}>{m}</td>
                  <td style={{ ...CELL, fontWeight: 700, color }}>{f2(cap)}</td>
                  {held.length > 0 && <td style={{ ...CELL, borderLeft: `1px solid ${theme.border}`, color: theme.textMuted }}>{f2(held.reduce((t, a) => t + valOf(a, m), 0))}</td>}
                  {shown.map(a => {
                    const orig = data?.[div]?.[a]?.[m]?.ty ?? 0
                    const v = valOf(a, m)
                    const k = `${a}|${m}`
                    const changed = Math.abs(v - orig) > 0.005
                    const ac = ATTR_COLOR[a] || theme.textMuted
                    return (
                      <td key={a} style={{ ...CELL, borderLeft: `1px solid ${theme.border}`, padding: '4px 8px' }}>
                        <input type="number" step="0.01" disabled={isLocked(div, a) || cap <= 0}
                          value={draft[k] ?? v.toFixed(2)}
                          onChange={e => setDraft({ [k]: e.target.value })}
                          onBlur={e => commit(a, m, e.target.value)}
                          onKeyDown={e => { if (e.key === 'Enter') e.currentTarget.blur() }}
                          title={`Current AOP ₹ ${f2(orig)} L (${(data?.[div]?.[a]?.[m]?.cont_pct ?? 0).toFixed(2)}%) · new ${(getContPct(div, a, m)).toFixed(4)}%`}
                          style={{ width: 92, fontFamily: theme.fontMono, fontSize: 12, textAlign: 'right', padding: '3px 6px', borderRadius: 5,
                                   border: `1px solid ${changed ? ac : theme.border}`, background: changed ? `${alpha(ac, '18')}` : theme.surface,
                                   color: theme.textPrimary, outline: 'none' }} />
                        <div style={{ fontSize: 10, color: theme.textMuted, marginTop: 2 }}>
                          {changed ? <>was {f2(orig)} · </> : null}{getContPct(div, a, m).toFixed(2)}%
                        </div>
                      </td>
                    )
                  })}
                  <td style={{ ...CELL, borderLeft: `2px solid ${theme.border}`, fontWeight: 600 }}>{f2(sum)}</td>
                  <td style={{ ...CELL, color: Math.abs(sum - cap) < 5e-9 ? theme.success : theme.danger }}>{(sum - cap).toFixed(8)}</td>
                </tr>
              )
            })}
            <tr style={{ borderTop: `2px solid ${theme.border}`, background: theme.surfaceAlt, fontWeight: 700 }}>
              <td style={{ ...CELL, textAlign: 'left', position: 'sticky', left: 0, background: theme.surfaceAlt }}>Season</td>
              <td style={{ ...CELL, color }}>{f2(seasonCap)}</td>
              {held.length > 0 && <td style={{ ...CELL, borderLeft: `1px solid ${theme.border}`, color: theme.textMuted }}>{f2(held.reduce((t, a) => t + season(a), 0))}</td>}
              {shown.map(a => <td key={a} style={{ ...CELL, borderLeft: `1px solid ${theme.border}` }}>{f2(season(a))}</td>)}
              <td style={{ ...CELL, borderLeft: `2px solid ${theme.border}` }}>{f2(attrs.reduce((t, a) => t + season(a), 0))}</td>
              <td style={{ ...CELL }}>{(attrs.reduce((t, a) => t + season(a), 0) - seasonCap).toFixed(8)}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}

// Comparison drawer — pre vs post side by side
function CompareDrawer({ open, onClose, months, pre, post, activeDiv }) {
  if (!open) return null
  const attrs = Object.keys(pre?.[activeDiv] || {})
  if (!attrs.length) return null

  return (
    <div style={{
      position: 'fixed', top: 0, right: 0, width: 680, height: '100vh',
      background: theme.surface, borderLeft: `1px solid ${theme.border}`,
      zIndex: 200, display: 'flex', flexDirection: 'column', boxShadow: '-8px 0 32px rgba(0,0,0,0.4)',
    }}>
      {/* Header */}
      <div style={{ padding: '18px 20px 14px', borderBottom: `1px solid ${theme.border}`, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <div style={{ fontSize: 14, fontWeight: 700, color: theme.textPrimary }}>AOP Comparison — {activeDiv}</div>
          <div style={{ fontSize: 11, color: theme.textMuted, marginTop: 2 }}>Pre vs Post Attribute Correction · SSG Stores · ₹L</div>
        </div>
        <button onClick={onClose} style={{ background: 'none', border: `1px solid ${theme.border}`, color: theme.textMuted, borderRadius: 6, padding: '4px 12px', cursor: 'pointer', fontSize: 13 }}>Close</button>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', overflowX: 'auto', padding: '0 0 20px 0' }}>
        <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 12 }}>
          <thead>
            <tr style={{ background: theme.surfaceAlt, position: 'sticky', top: 0, zIndex: 1 }}>
              <th style={{ ...HDR, textAlign: 'left', padding: '8px 14px', minWidth: 120 }}>Attribute</th>
              <th style={{ ...HDR, padding: '8px 10px' }}>Month</th>
              <th style={{ ...HDR, padding: '8px 10px', color: '#1D4ED8' }}>Pre TY</th>
              <th style={{ ...HDR, padding: '8px 10px', color: '#1D4ED8' }}>Pre %</th>
              <th style={{ ...HDR, padding: '8px 10px', color: '#15803D' }}>Post TY</th>
              <th style={{ ...HDR, padding: '8px 10px', color: '#15803D' }}>Post %</th>
              <th style={{ ...HDR, padding: '8px 10px' }}>Δ TY</th>
              <th style={{ ...HDR, padding: '8px 10px' }}>Δ %pt</th>
            </tr>
          </thead>
          <tbody>
            {attrs.map(attr => {
              const color = ATTR_COLOR[attr] || theme.textMuted
              return months.map((m, mi) => {
                const preCell  = pre?.[activeDiv]?.[attr]?.[m]  || { ty: 0, cont_pct: 0 }
                const postCell = post?.[activeDiv]?.[attr]?.[m] || { ty: 0, cont_pct: 0 }
                const deltaTy  = postCell.ty - preCell.ty
                const deltaPct = postCell.cont_pct - preCell.cont_pct
                return (
                  <tr key={`${attr}-${m}`} style={{ background: mi % 2 === 0 ? theme.surfaceAlt : 'transparent', borderBottom: `1px solid ${theme.border}` }}>
                    {mi === 0 && (
                      <td rowSpan={months.length} style={{ padding: '0 14px', verticalAlign: 'middle', borderRight: `2px solid ${color}`, minWidth: 120 }}>
                        <span style={{ fontSize: 11, fontWeight: 700, color, letterSpacing: 0.3 }}>{attr}</span>
                      </td>
                    )}
                    <td style={{ ...CELL, textAlign: 'left', color: theme.textMuted, fontSize: 11 }}>{m}</td>
                    <td style={{ ...CELL, color: '#1D4ED8' }}>{preCell.ty.toFixed(2)}</td>
                    <td style={{ ...CELL, color: '#1D4ED8' }}>{preCell.cont_pct.toFixed(2)}%</td>
                    <td style={{ ...CELL, color: '#15803D' }}>{postCell.ty.toFixed(2)}</td>
                    <td style={{ ...CELL, color: '#15803D' }}>{postCell.cont_pct.toFixed(2)}%</td>
                    <td style={{ ...CELL, color: deltaTy > 0 ? theme.success : deltaTy < 0 ? theme.danger : theme.textMuted }}>
                      {deltaTy > 0 ? '+' : ''}{deltaTy.toFixed(2)}
                    </td>
                    <td style={{ ...CELL, color: deltaPct > 0 ? theme.success : deltaPct < 0 ? theme.danger : theme.textMuted }}>
                      {deltaPct > 0 ? '+' : ''}{deltaPct.toFixed(2)}
                    </td>
                  </tr>
                )
              })
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default function AttributeCorrection() {
  const navigate     = useNavigate()
  const inPipeline   = currentEngineKey() === 'attr-correction'
  const [activeDiv, setActiveDiv]       = useState('KIDS')
  const [loading, setLoading]           = useState(true)
  const [saving, setSaving]             = useState(false)
  const [saveMsg, setSaveMsg]           = useState('')
  const [data, setData]                 = useState({})        // {div:{attr:{month:{ty,cont_pct}}}}
  const [corrections, setCorrections]   = useState({})        // {div:{month:{attr:cont_pct}}}
  const [attrDeptMap, setAttrDeptMap]   = useState({})        // {div:{attr:[depts]}}
  const [months, setMonths]             = useState([])
  const [compareOpen, setCompareOpen]   = useState(false)
  const [compareData, setCompareData]   = useState({ pre: {}, post: {} })
  const [showDeptInfo, setShowDeptInfo] = useState(null)      // {attr, depts}
  const [locks, setLocks]               = useState({})        // {div: Set<attr>}
  const [originalCorrections, setOriginalCorrections] = useState({})   // snapshot of defaults on load

  // ── Fetch base data ─────────────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetch('/api/planning/attr-correction/preview')
      .then(r => { if (!r.ok) throw new Error(r.status); return r.json() })
      .then(d => {
        if (cancelled) return
        setData(d.data || {})
        setAttrDeptMap(d.attr_dept_map || {})
        setMonths(d.months || [])
        const defaults = {}
        for (const [div, attrs] of Object.entries(d.data || {})) {
          defaults[div] = {}
          for (const m of (d.months || [])) {
            defaults[div][m] = {}
            for (const [attr, mdata] of Object.entries(attrs)) {
              defaults[div][m][attr] = mdata[m]?.cont_pct ?? 0
            }
          }
        }
        setOriginalCorrections(defaults)
        if (d.corrections && Object.keys(d.corrections).length) {
          setCorrections(d.corrections)
        } else {
          setCorrections(defaults)
        }
        setLoading(false)
      })
      .catch(e => { if (!cancelled) { console.error(e); setLoading(false) } })
    return () => { cancelled = true }
  }, [])

  // ── Lock toggle ────────────────────────────────────────────────────────────
  const toggleLock = (div, attr) => {
    setLocks(prev => {
      const set = new Set(prev[div] || [])
      set.has(attr) ? set.delete(attr) : set.add(attr)
      return { ...prev, [div]: set }
    })
  }
  const isLocked = (div, attr) => locks[div]?.has(attr) ?? false
  // which attributes you work on (default all); the others are held out - they and their departments keep their AOP,
  // like a lock, even with LY sales (user, 2026-10-01)
  const [workOn, setWorkOn] = useState({})   // {div: Set<attr>}; absent = all
  const isWorking = (div, attr) => !workOn[div] || workOn[div].has(attr)
  const toggleWork = (div, attr) => setWorkOn(prev => {
    const set = new Set(prev[div] || Object.keys(data?.[div] || {}))
    set.has(attr) ? set.delete(attr) : set.add(attr)
    return { ...prev, [div]: set }
  })
  const isHeld = (div, attr) => isLocked(div, attr) || !isWorking(div, attr)

  // ── Edit: just update the single cell, no cascade ───────────────────────
  const handleContChange = (div, month, changedAttr, rawVal) => {
    const newPct = parseFloat(rawVal)
    if (isNaN(newPct)) return
    setCorrections(prev => {
      const divCopy   = { ...(prev[div] || {}) }
      const monthCopy = { ...(divCopy[month] || {}) }
      divCopy[month]  = { ...monthCopy, [changedAttr]: newPct }
      return { ...prev, [div]: divCopy }
    })
  }

  // ── Auto Balance: redistribute unlocked attrs proportionally to reach 100% ─
  const handleAutoBalance = useCallback(() => {
    setCorrections(prev => {
      const divCopy = { ...(prev[activeDiv] || {}) }
      const allAttrs = Object.keys(data[activeDiv] || {})

      for (const m of months) {
        const monthCopy = { ...(divCopy[m] || {}) }
        const lockedAttrs   = allAttrs.filter(a => isHeld(activeDiv, a))
        const unlockAttrs   = allAttrs.filter(a => !isHeld(activeDiv, a))

        const lockedSum = lockedAttrs.reduce(
          (s, a) => s + (monthCopy[a] ?? (data[activeDiv]?.[a]?.[m]?.cont_pct ?? 0)), 0
        )
        const remaining     = 100 - lockedSum
        const unlockCurrent = unlockAttrs.reduce(
          (s, a) => s + (monthCopy[a] ?? (data[activeDiv]?.[a]?.[m]?.cont_pct ?? 0)), 0
        )

        const updated = { ...monthCopy }
        if (unlockCurrent > 0) {
          for (const a of unlockAttrs) {
            const cur = monthCopy[a] ?? (data[activeDiv]?.[a]?.[m]?.cont_pct ?? 0)
            updated[a] = parseFloat(((cur / unlockCurrent) * remaining).toFixed(4))
          }
        } else if (unlockAttrs.length > 0) {
          const each = parseFloat((remaining / unlockAttrs.length).toFixed(4))
          for (const a of unlockAttrs) updated[a] = each
        }
        divCopy[m] = updated
      }
      return { ...prev, [activeDiv]: divCopy }
    })
  }, [activeDiv, data, months, locks, workOn])

  // The AOP-by-attribute window sets a whole month's % at once (they add to exactly 100)
  const setMonthPcts = (div, month, pcts) => setCorrections(prev => ({
    ...prev, [div]: { ...(prev[div] || {}), [month]: pcts },
  }))

  // The saved department plan has no months yet: generate it (Department Plan's Generate Base Plan), then reload
  const [generating, setGenerating] = useState(false)
  const generateBase = async () => {
    setGenerating(true)
    try {
      const r = await fetch('/api/planning/dept-sales/generate-base', { method: 'POST' })
      if (r.ok) window.location.reload()
    } finally { setGenerating(false) }
  }

  // Get the effective cont_pct for a cell (correction override or base data)
  const getContPct = (div, attr, month) => {
    const override = corrections?.[div]?.[month]?.[attr]
    if (override !== undefined) return override
    return data?.[div]?.[attr]?.[month]?.cont_pct ?? 0
  }

  // Compute corrected TY from the corrected cont%
  const getCorrectedTy = (div, attr, month) => {
    // Sum all attr TYs for this div × month in original data = total_ty
    const totalTy = Object.values(data?.[div] || {}).reduce((s, mdata) => s + (mdata?.[month]?.ty ?? 0), 0)
    return (getContPct(div, attr, month) / 100) * totalTy
  }

  // Total cont% for validation
  const totalContPct = (div, month) =>
    Object.keys(data?.[div] || {}).reduce((s, a) => s + getContPct(div, a, month), 0)

  // ── Save & Apply ────────────────────────────────────────────────────────────
  const handleSave = async () => {
    setSaving(true); setSaveMsg('')
    try {
      const r = await fetch('/api/planning/attr-correction/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(corrections),
      })
      const d = await r.json()
      if (d.ok) {
        if (inPipeline) { navigate(advancePipeline()); return }
        setSaveMsg('Saved & applied')
        setCompareData({ pre: d.pre, post: d.post })
      } else {
        setSaveMsg(d.detail || 'Error')
      }
    } catch (e) {
      setSaveMsg('Network error')
    } finally {
      setSaving(false)
      setTimeout(() => setSaveMsg(''), 4000)
    }
  }

  // ── Revert active division to original loaded values ────────────────────────
  const handleRevert = useCallback(() => {
    if (!originalCorrections[activeDiv]) return
    // danger action (user, 2026-10-07: "add confirm to both")
    if (!window.confirm(`Revert ${activeDiv} to the original attribute corrections? Unsaved changes in this division will be lost.`)) return
    setCorrections(prev => ({
      ...prev,
      [activeDiv]: originalCorrections[activeDiv],
    }))
  }, [activeDiv, originalCorrections])

  // ── Compare ─────────────────────────────────────────────────────────────────
  const handleCompare = async () => {
    try {
      const r = await fetch('/api/planning/attr-correction/comparison')
      const d = await r.json()
      setCompareData({ pre: d.pre, post: d.post })
      setCompareOpen(true)
    } catch (e) {}
  }

  // ── Derived ─────────────────────────────────────────────────────────────────
  const divAttrs = Object.keys(data?.[activeDiv] || {}).sort()
  const divColor = DIV_COLOR[activeDiv] || theme.primary
  const hasData  = divAttrs.length > 0 && months.length > 0

  // Total AOP per attribute (sum across months)
  const attrAopTotal = (attr) => months.reduce((s, m) => s + getCorrectedTy(activeDiv, attr, m), 0)

  return (
    <div style={{ padding: '28px 32px', minHeight: '100vh', background: theme.surfaceAlt }}>
      {inPipeline && <PipelineBanner currentKey="attr-correction" />}
      <CompareDrawer
        open={compareOpen}
        onClose={() => setCompareOpen(false)}
        months={months}
        pre={compareData.pre}
        post={compareData.post}
        activeDiv={activeDiv}
      />

      {/* Page header */}
      <div style={{ marginBottom: 18 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
          <div className="sp-sub" style={{ margin: 0 }}>
            Adjust ATTRIBUTE1 contribution % per division per month. SSG stores only. Changes reapportion AOP post New Depts.
          </div>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <button
              onClick={handleAutoBalance}
              title="Redistribute unlocked attributes proportionally to sum to 100%"
              style={{ background: 'none', border: `1px solid ${divColor}`, color: divColor, borderRadius: 8, padding: '8px 16px', cursor: 'pointer', fontSize: 13, fontWeight: 600 }}
            >
              ⚖ Auto Balance
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              style={{ background: divColor, border: 'none', color: '#fff', borderRadius: 8, padding: '8px 20px', cursor: saving ? 'default' : 'pointer', fontSize: 13, fontWeight: 600, opacity: saving ? 0.7 : 1 }}
            >
              {saving ? 'Saving…' : 'Save & Apply'}
            </button>
            <details className="sp-menu">
              <summary>More ▾</summary>
              <div className="sp-menu-pop">
                <button onClick={handleCompare}>
                  Compare AOP
                </button>
                <button
                  className="sp-danger"
                  onClick={handleRevert}
                  title="Reset all Cont % for this division back to the original loaded values"
                >
                  ↺ Revert to Original
                </button>
              </div>
            </details>
            {saveMsg && (
              <span style={{ fontSize: 12, color: theme.success, alignSelf: 'center', marginLeft: 4 }}>{saveMsg}</span>
            )}
          </div>
        </div>

        {/* Notice - collapsed by default */}
        <details className="sp-fold" style={{ marginTop: 8 }}>
          <summary>How editing works</summary>
          <div style={{ padding: '4px 0 0 14px', fontSize: 12, color: theme.textMuted }}>
            Edit any Cont% freely — no other values change until you press <strong>Auto Balance</strong>. Locked attributes are always excluded from rebalancing.
            AOP is sourced from Post New MCs working (SSG stores). Correction is <strong>optional</strong> — skip to proceed directly to Base Correction.
          </div>
        </details>
      </div>

      {/* Division tabs */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 20 }}>
        {DIVISIONS.map(div => {
          const isActive = div === activeDiv
          const c = DIV_COLOR[div]
          const attrCount = Object.keys(data?.[div] || {}).length
          return (
            <button
              key={div}
              onClick={() => setActiveDiv(div)}
              style={{
                background: isActive ? c : theme.surface,
                border: `1.5px solid ${isActive ? c : theme.border}`,
                color: isActive ? '#fff' : theme.textMuted,
                borderRadius: 8,
                padding: '7px 18px',
                cursor: 'pointer',
                fontSize: 13,
                fontWeight: isActive ? 700 : 400,
                display: 'flex',
                alignItems: 'center',
                gap: 7,
              }}
            >
              {div}
              {attrCount > 0 && (
                <span style={{ fontSize: 10, background: isActive ? 'rgba(255,255,255,0.25)' : theme.border, borderRadius: 10, padding: '1px 6px' }}>{attrCount}</span>
              )}
            </button>
          )
        })}
      </div>

      {/* Content */}
      {loading ? (
        <div style={{ color: theme.textMuted, fontSize: 13, padding: '40px 0' }}>Loading attribute data…</div>
      ) : !hasData ? (
        <div style={{ padding: 32, background: theme.surface, borderRadius: 12, border: `1px solid ${theme.border}`, textAlign: 'center' }}>
          <div style={{ fontSize: 28, marginBottom: 12 }}>📋</div>
          <div style={{ fontSize: 14, color: theme.textPrimary, marginBottom: 6 }}>No attribute data for {activeDiv}</div>
          <div style={{ fontSize: 12, color: theme.textMuted }}>
            {months.length === 0
              ? <>The saved department plan has no plan months yet (it was generated before the Calendar sales were linked).<br/>
                  Generate it once - it takes a few seconds - and this page fills in.</>
              : <>Either no departments in this division have LY actuals, or the Attribute Master has no entries for {activeDiv}.</>}
          </div>
          {months.length === 0 && (
            <button onClick={generateBase} disabled={generating}
              style={{ marginTop: 14, background: divColor, border: 'none', color: '#fff', borderRadius: 8, padding: '8px 20px',
                       cursor: generating ? 'default' : 'pointer', fontSize: 13, fontWeight: 600, opacity: generating ? 0.7 : 1 }}>
              {generating ? 'Generating the plan…' : '▶ Generate the department plan'}
            </button>
          )}
        </div>
      ) : (
        <>
        <AttributeAopWindow div={activeDiv} attrs={divAttrs} months={months} data={data} getContPct={getContPct}
          isLocked={isHeld} onSetMonth={(m, pcts) => setMonthPcts(activeDiv, m, pcts)} color={divColor}
          isWorking={isWorking} onToggleWork={toggleWork} />
        <div style={{ background: theme.surface, borderRadius: 12, border: `1px solid ${theme.border}`, overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 12 }}>
              <thead>
                <tr style={{ background: theme.surfaceAlt, borderBottom: `2px solid ${theme.border}` }}>
                  <th style={{ ...HDR, textAlign: 'left', padding: '10px 16px', minWidth: 160, position: 'sticky', left: 0, background: theme.surfaceAlt, zIndex: 2 }}>
                    Attribute
                  </th>
                  <th style={{ ...HDR, minWidth: 70, color: theme.accent }}>Depts</th>
                  {months.map(m => (
                    <th key={m} colSpan={2} style={{ ...HDR, minWidth: 130, borderLeft: `1px solid ${theme.border}`, textAlign: 'center', padding: '10px 4px' }}>
                      {m}
                    </th>
                  ))}
                  <th style={{ ...HDR, minWidth: 100, borderLeft: `2px solid ${theme.border}`, color: theme.accent }}>
                    AOP Total
                  </th>
                </tr>
                {/* Sub-header: TY | Cont% */}
                <tr style={{ background: theme.surfaceAlt, borderBottom: `1px solid ${theme.border}` }}>
                  <th style={{ ...HDR, textAlign: 'left', padding: '5px 16px', position: 'sticky', left: 0, background: theme.surfaceAlt, zIndex: 2 }}></th>
                  <th style={{ ...HDR }}></th>
                  {months.map(m => (
                    <th key={`sub-${m}`} colSpan={2} style={{ ...HDR, borderLeft: `1px solid ${theme.border}`, padding: '0' }}>
                      <span style={{ display: 'inline-block', width: '50%', padding: '5px 8px', fontSize: 10, color: theme.textMuted }}>TY ₹L</span>
                      <span style={{ display: 'inline-block', width: '50%', padding: '5px 8px', fontSize: 10, color: theme.accent }}>Cont %</span>
                    </th>
                  ))}
                  <th style={{ ...HDR, borderLeft: `2px solid ${theme.border}` }}></th>
                </tr>
              </thead>
              <tbody>
                {divAttrs.map((attr, ai) => {
                  const color    = ATTR_COLOR[attr] || theme.textMuted
                  const deptList = attrDeptMap?.[activeDiv]?.[attr] || []
                  const aopTotal = attrAopTotal(attr)
                  const locked   = isHeld(activeDiv, attr)
                  const rowBg    = ai % 2 === 0 ? 'transparent' : theme.surfaceAlt
                  return (
                    <tr key={attr} style={{ borderBottom: `1px solid ${theme.border}`, background: rowBg, opacity: !isWorking(activeDiv, attr) ? 0.45 : locked ? 0.88 : 1 }}>
                      {/* Attribute label + lock button */}
                      <td style={{ padding: '6px 10px 6px 16px', position: 'sticky', left: 0, background: ai % 2 === 0 ? theme.surface : theme.surfaceAlt, zIndex: 1, borderRight: `1px solid ${theme.border}` }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <div style={{ width: 4, height: 22, borderRadius: 2, background: color, flexShrink: 0 }} />
                          <span style={{ fontSize: 12, fontWeight: 600, color, flex: 1 }}>{attr}</span>
                          <button
                            onClick={() => toggleLock(activeDiv, attr)}
                            title={locked ? 'Locked — click to unlock' : 'Unlocked — click to lock'}
                            style={{
                              background: locked ? `${alpha(color,'28')}` : 'none',
                              border: `1px solid ${locked ? color : theme.border}`,
                              borderRadius: 5,
                              padding: '2px 6px',
                              cursor: 'pointer',
                              fontSize: 12,
                              lineHeight: 1,
                              color: locked ? color : theme.textMuted,
                              flexShrink: 0,
                            }}
                          >
                            {locked ? '🔒' : '🔓'}
                          </button>
                        </div>
                      </td>
                      {/* Dept count — clickable */}
                      <td style={{ ...CELL, textAlign: 'center' }}>
                        <button
                          onClick={() => setShowDeptInfo(showDeptInfo?.attr === attr ? null : { attr, depts: deptList })}
                          style={{ background: 'none', border: `1px solid ${theme.border}`, color: theme.textMuted, borderRadius: 5, padding: '2px 8px', cursor: 'pointer', fontSize: 11 }}
                        >
                          {deptList.length}
                        </button>
                      </td>
                      {/* Month cells */}
                      {months.map(m => {
                        const contPct = getContPct(activeDiv, attr, m)
                        const corrTy  = getCorrectedTy(activeDiv, attr, m)
                        const changed = Math.abs(contPct - (data?.[activeDiv]?.[attr]?.[m]?.cont_pct ?? 0)) > 0.001
                        return (
                          <React.Fragment key={`${attr}-${m}`}>
                            <td style={{ ...CELL, borderLeft: `1px solid ${theme.border}`, color: changed ? theme.accent : color, opacity: changed ? 1 : 0.75 }}>
                              {corrTy.toFixed(2)}
                            </td>
                            <td style={{ ...CELL, padding: '4px 6px', background: `${alpha(color,'0A')}` }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                                <input
                                  type="number"
                                  step="0.1"
                                  value={parseFloat(contPct.toFixed(4))}
                                  onChange={e => handleContChange(activeDiv, m, attr, e.target.value)}
                                  disabled={locked}
                                  style={{
                                    width: 58,
                                    background: locked ? `${alpha(color,'20')}` : changed ? `${alpha(color,'30')}` : `${alpha(color,'18')}`,
                                    color: changed ? color : `${alpha(color,'CC')}`,
                                    border: `1px solid ${changed ? color : `${alpha(color,'55')}`}`,
                                    borderRadius: 5,
                                    padding: '3px 5px',
                                    fontSize: 11,
                                    fontFamily: theme.fontMono,
                                    textAlign: 'right',
                                    outline: 'none',
                                    cursor: locked ? 'not-allowed' : 'text',
                                    opacity: locked ? 0.85 : 1,
                                  }}
                                />
                                {locked
                                  ? <span style={{ fontSize: 10, color }}>🔒</span>
                                  : <span style={{ fontSize: 10, color: theme.textMuted }}>%</span>
                                }
                              </div>
                            </td>
                          </React.Fragment>
                        )
                      })}
                      {/* AOP Total */}
                      <td style={{ ...CELL, borderLeft: `2px solid ${theme.border}`, color: theme.accent, fontWeight: 600 }}>
                        {aopTotal.toFixed(2)}
                      </td>
                    </tr>
                  )
                })}
                {/* Validation row: totals per month */}
                <tr style={{ borderTop: `2px solid ${theme.border}`, background: theme.surfaceAlt }}>
                  <td colSpan={2} style={{ padding: '8px 16px', fontSize: 11, fontWeight: 700, color: theme.textMuted, position: 'sticky', left: 0, background: theme.surfaceAlt }}>
                    TOTAL
                  </td>
                  {months.map(m => {
                    const total = totalContPct(activeDiv, m)
                    const ok = Math.abs(total - 100) < 0.1
                    return (
                      <React.Fragment key={`tot-${m}`}>
                        <td style={{ ...CELL, borderLeft: `1px solid ${theme.border}`, color: theme.textMuted }}>
                          {Object.values(data?.[activeDiv] || {}).reduce((s, mdata) => s + (mdata?.[m]?.ty ?? 0), 0).toFixed(2)}
                        </td>
                        <td style={{ ...CELL, color: ok ? theme.success : theme.danger, fontWeight: 700 }}>
                          {total.toFixed(2)}%
                        </td>
                      </React.Fragment>
                    )
                  })}
                  <td style={{ ...CELL, borderLeft: `2px solid ${theme.border}`, color: theme.accent, fontWeight: 700 }}>
                    {months.reduce((s, m) => s + Object.values(data?.[activeDiv] || {}).reduce((ss, mdata) => ss + (mdata?.[m]?.ty ?? 0), 0), 0).toFixed(2)}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          {/* Dept info tooltip */}
          {showDeptInfo && (
            <div style={{ padding: '12px 20px', borderTop: `1px solid ${theme.border}`, background: theme.surfaceAlt }}>
              <div style={{ fontSize: 11, color: theme.textMuted, marginBottom: 6 }}>
                Departments under <strong style={{ color: ATTR_COLOR[showDeptInfo.attr] || theme.textPrimary }}>{showDeptInfo.attr}</strong> in {activeDiv}:
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {showDeptInfo.depts.map(d => (
                  <span key={d} style={{ fontSize: 11, padding: '3px 8px', background: theme.surfaceUp, borderRadius: 5, color: theme.textMuted, fontFamily: theme.fontMono }}>
                    {d}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
        </>
      )}
    </div>
  )
}
