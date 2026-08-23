import { useState, useEffect } from 'react'
import { theme } from '../theme'
import SearchSlicer from '../components/SearchSlicer'

const CELL = { fontFamily: theme.fontMono, fontSize: 12, textAlign: 'right', padding: '5px 10px', whiteSpace: 'nowrap' }
const HDR  = { ...CELL, fontSize: 11, color: theme.textMuted, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.4 }

const TY_MONTHS = [
  "Mar'27","Apr'27","May'27","Jun'27","Jul'27","Aug'27",
  "Sep'27","Oct'27","Nov'27","Dec'27","Jan'28","Feb'28","Mar'28"
]

const DIV_COLOR = {
  KIDS: '#C85A12', LADIES: '#7420B8', MENS: '#077A4A', GM: '#1E54C0', RETAIL: '#B22620',
}

// ── Pipeline node ──────────────────────────────────────────────────────────────
function PipelineNode({ label, done, active, optional }) {
  const bg    = done   ? (active ? theme.accent : `${theme.success}22`) : theme.surfaceAlt
  const border = done  ? (active ? theme.accent : theme.success)         : theme.border
  const color  = done  ? (active ? '#fff'       : theme.success)         : theme.textMuted
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, minWidth: 130,
    }}>
      <div style={{
        padding: '8px 16px', borderRadius: 8, border: `1px solid ${border}`,
        background: bg, color, fontSize: 12, fontWeight: 600, textAlign: 'center',
        position: 'relative',
      }}>
        {done ? '✓ ' : ''}{label}
        {optional && (
          <span style={{
            position: 'absolute', top: -8, right: -6,
            fontSize: 9, background: theme.surfaceUp, color: theme.textMuted,
            border: `1px solid ${theme.border}`, borderRadius: 4, padding: '1px 4px',
          }}>opt</span>
        )}
      </div>
      {!done && <div style={{ fontSize: 10, color: theme.textMuted }}>not run</div>}
    </div>
  )
}

function Arrow({ active }) {
  return (
    <div style={{
      fontSize: 18, color: active ? theme.success : theme.border,
      alignSelf: 'center', marginBottom: 16,
    }}>→</div>
  )
}

export default function FinalResults() {
  const [data, setData]     = useState(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr]       = useState('')
  const [expandedDiv, setExpandedDiv] = useState(null)
  const [storeFilters, setStoreFilters]   = useState(new Set())
  const [storeTypeFilters, setStoreTypeFilters] = useState(new Set())
  const [viewMode, setViewMode]     = useState('store')  // 'store' | 'dept' | 'dashboard' | 'cluster'
  const [deptDiv, setDeptDiv]         = useState('KIDS')
  const [deptFilters, setDeptFilters] = useState(new Set())
  const [deptStoreFilters, setDeptStoreFilters] = useState(new Set())
  const [deptStoreType, setDeptStoreType] = useState('ALL')
  const [showDegrowthOnly, setShowDegrowthOnly] = useState(false)
  const [dashboard, setDashboard]   = useState(null)
  const [dashDiv, setDashDiv]       = useState(null)
  // Cluster view state
  const [clusterPlan, setClusterPlan] = useState(null)
  const [clusterLoading, setClusterLoading] = useState(false)
  const [activeCluster, setActiveCluster] = useState(null)
  const [clusterDiv, setClusterDiv]   = useState('KIDS')
  const [clusterMonth, setClusterMonth] = useState(null)

  const NODEPT = ['GM', 'RETAIL']

  useEffect(() => {
    fetch('/api/final-results/data')
      .then(r => r.ok ? r.json() : r.json().then(e => { throw new Error(e.detail) }))
      .then(d => { setData(d); setLoading(false) })
      .catch(e => { setErr(e.message); setLoading(false) })
    fetch('/api/final-results/dashboard')
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) { setDashboard(d); setDashDiv(Object.keys(d.divisions || {})[0] || null) } })
      .catch(() => {})
  }, [])

  // Lazy-load cluster plan only when Cluster View is first opened
  useEffect(() => {
    if (viewMode !== 'cluster' || clusterPlan) return
    setClusterLoading(true)
    fetch('/api/dept-sales/cluster-plan')
      .then(r => r.json())
      .then(d => {
        setClusterPlan(d)
        if (d.clusters?.length) setActiveCluster(d.clusters[0])
        if (d.months?.length)   setClusterMonth(d.months[0])
        setClusterLoading(false)
      })
      .catch(() => setClusterLoading(false))
  }, [viewMode, clusterPlan])


  if (loading) return (
    <div style={{ padding: '28px 32px', color: theme.textMuted, fontSize: 13 }}>Loading final plan…</div>
  )

  if (err) return (
    <div style={{ padding: '28px 32px' }}>
      <div style={{ padding: 32, background: theme.surface, borderRadius: 12, border: `1px solid ${theme.border}`, textAlign: 'center' }}>
        <div style={{ fontSize: 28, marginBottom: 10 }}>📂</div>
        <div style={{ fontSize: 14, color: theme.danger, fontWeight: 600, marginBottom: 6 }}>{err}</div>
        <div style={{ fontSize: 12, color: theme.textMuted }}>Run the Department Plan → New Depts engine first to generate a plan.</div>
      </div>
    </div>
  )

  const { pipeline, remark, active_source, total_stores, ssg_stores, nso_stores, total_ty, stores } = data
  const buyerSynced = pipeline.buyer_synced

  const allStoreNames = stores.map(s => s.store)

  const filteredStores = stores.filter(s => {
    if (storeTypeFilters.size > 0) {
      const tag = s.is_ssg ? (s.store === 'ANG' ? 'SSG - ANG' : 'SSG') : 'NSO'
      if (!storeTypeFilters.has(tag)) return false
    }
    if (storeFilters.size > 0 && !storeFilters.has(s.store)) return false
    return true
  })

  const allDivs = [...new Set(stores.flatMap(s => Object.keys(s.divisions)))].sort()

  // ── Dept view data ────────────────────────────────────────────────────────
  const deptRows = (() => {
    if (viewMode !== 'dept') return []
    const rows = []
    for (const s of stores) {
      if (deptStoreType === 'SSG' && !s.is_ssg) continue
      if (deptStoreType === 'NSO' && s.is_ssg)  continue
      if (deptStoreFilters.size > 0 && !deptStoreFilters.has(s.store)) continue
      const divData = s.divisions[deptDiv]
      if (!divData) continue
      for (const [dept, vals] of Object.entries(divData.departments || {})) {
        if (deptFilters.size > 0 && !deptFilters.has(dept)) continue
        if (showDegrowthOnly && (vals.growth === null || vals.growth >= 0)) continue
        rows.push({ store: s.store, is_ssg: s.is_ssg, cluster: s.cluster, tag: s.tag, dept, ...vals })
      }
    }
    rows.sort((a, b) => {
      if (a.dept !== b.dept) return a.dept.localeCompare(b.dept)
      return (a.growth ?? 999) - (b.growth ?? 999)
    })
    return rows
  })()

  const allDeptsInDiv = deptDiv
    ? [...new Set(stores.flatMap(s => Object.keys(s.divisions[deptDiv]?.departments || {})))].sort()
    : []

  const degrowthCount = deptDiv
    ? stores.reduce((n, s) => {
        for (const vals of Object.values(s.divisions[deptDiv]?.departments || {}))
          if (vals.growth !== null && vals.growth < 0) n++
        return n
      }, 0)
    : 0

  return (
    <div style={{ padding: '28px 32px', minHeight: '100vh', background: theme.surfaceAlt }}>

      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: theme.textPrimary }}>Final Results</h1>
        <p style={{ margin: '6px 0 0', fontSize: 13, color: theme.textMuted }}>
          Live view of the most advanced dept plan available. Reflects all engines that have run.
        </p>
      </div>

      {/* Pipeline pathway */}
      <div style={{
        background: theme.surface, borderRadius: 12, border: `1px solid ${theme.border}`,
        padding: '20px 24px', marginBottom: 20,
      }}>
        <div style={{ fontSize: 11, color: theme.textMuted, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.6, marginBottom: 16 }}>
          Pipeline Pathway
        </div>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
          {/* Master Setup — always the starting node, synced from Integrated Buyer's Input */}
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, minWidth: 140 }}>
            <div style={{
              padding: '8px 14px', borderRadius: 8,
              border: `1px solid ${buyerSynced ? theme.success : theme.border}`,
              background: buyerSynced ? `${theme.success}18` : theme.surfaceAlt,
              color: buyerSynced ? theme.success : theme.textMuted,
              fontSize: 12, fontWeight: 600, textAlign: 'center',
            }}>
              ✓ Master Setup
            </div>
            <div style={{ fontSize: 10, color: buyerSynced ? theme.success : theme.textMuted, textAlign: 'center' }}>
              {buyerSynced ? 'Buyer\'s Input ↑' : 'No MRP sync'}
            </div>
          </div>
          <Arrow active />
          <PipelineNode label="New Depts"        done={pipeline.new_depts}      active={active_source === 'final_dept_plan.json'} optional />
          <Arrow active={pipeline.new_depts} />
          <PipelineNode label="Attr Correction"  done={pipeline.attr_correction} active={active_source === 'attr_corrected_plan.json'} optional />
          <Arrow active={pipeline.attr_correction} />
          <PipelineNode label="Base Correction"  done={pipeline.base_correction} active={active_source === 'base_corrected_plan.json'} optional />
          <div style={{ marginLeft: 16, alignSelf: 'center', marginBottom: 16 }}>
            <div style={{
              padding: '8px 14px', borderRadius: 8, background: `${theme.accent}18`,
              border: `1px solid ${theme.accent}`, fontSize: 11, color: theme.accent, fontWeight: 600,
            }}>
              Active source:<br />
              <span style={{ fontFamily: theme.fontMono, fontSize: 10, color: theme.textPrimary }}>{active_source}</span>
            </div>
          </div>
        </div>
        <div style={{
          marginTop: 4, fontSize: 12, color: theme.textMuted,
          borderTop: `1px solid ${theme.border}`, paddingTop: 12,
        }}>
          <span style={{ color: theme.accent, fontWeight: 600 }}>Engines run: </span>{remark}
        </div>
      </div>

      {/* Summary cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 12, marginBottom: 20 }}>
        {[
          { label: 'Total Stores',   value: total_stores, color: theme.textPrimary },
          { label: 'SSG Stores',     value: ssg_stores,   color: theme.success },
          { label: 'NSO Stores',     value: nso_stores,   color: theme.accent },
          { label: 'Total TY (₹L)',  value: total_ty?.toFixed(2), color: theme.primary },
        ].map(c => (
          <div key={c.label} style={{ background: theme.surface, borderRadius: 10, padding: '14px 16px', border: `1px solid ${theme.border}` }}>
            <div style={{ fontSize: 11, color: theme.textMuted, marginBottom: 4 }}>{c.label}</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: c.color, fontFamily: theme.fontMono }}>{c.value}</div>
          </div>
        ))}
      </div>

      {/* View mode toggle */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16, alignItems: 'center' }}>
        {[['store', 'Store View'], ['dept', 'Department View'], ['cluster', 'Cluster View'], ['dashboard', 'Dashboard']].map(([mode, label]) => (
          <button key={mode} onClick={() => setViewMode(mode)} style={{
            padding: '6px 18px', borderRadius: 7, fontSize: 12, fontWeight: 600, cursor: 'pointer',
            background: viewMode === mode ? theme.primary : theme.surface,
            color: viewMode === mode ? '#fff' : theme.textMuted,
            border: `1px solid ${viewMode === mode ? theme.primary : theme.border}`,
          }}>{label}</button>
        ))}
      </div>

      {/* ── STORE VIEW ─────────────────────────────────────────────────────── */}
      {viewMode === 'store' && (
        <>
          <div style={{ display: 'flex', gap: 10, marginBottom: 14, alignItems: 'center', flexWrap: 'wrap' }}>
            <SearchSlicer
              items={allStoreNames}
              selected={storeFilters}
              onChange={setStoreFilters}
              label="All Stores"
              placeholder="Search store…"
              width={170}
            />
            <SearchSlicer
              items={['SSG', 'SSG - ANG', 'NSO']}
              selected={storeTypeFilters}
              onChange={setStoreTypeFilters}
              label="All Store Types"
              placeholder="Search type…"
              width={150}
            />
            <div style={{ display: 'flex', gap: 6 }}>
              {allDivs.map(d => (
                <button key={d} onClick={() => setExpandedDiv(expandedDiv === d ? null : d)} style={{
                  padding: '4px 12px', borderRadius: 6, fontSize: 11, fontWeight: 600, cursor: 'pointer',
                  background: expandedDiv === d ? `${DIV_COLOR[d] || theme.primary}33` : 'transparent',
                  color: DIV_COLOR[d] || theme.textMuted,
                  border: `1px solid ${expandedDiv === d ? (DIV_COLOR[d] || theme.primary) : theme.border}`,
                }}>{d}</button>
              ))}
              {expandedDiv && (
                <button onClick={() => setExpandedDiv(null)} style={{ padding: '4px 10px', borderRadius: 6, fontSize: 11, cursor: 'pointer', background: 'transparent', border: `1px solid ${theme.border}`, color: theme.textMuted }}>✕</button>
              )}
            </div>
            <span style={{ fontSize: 11, color: theme.textMuted }}>{filteredStores.length} of {stores.length} stores</span>
          </div>

          <div style={{ background: theme.surface, borderRadius: 12, border: `1px solid ${theme.border}`, overflow: 'hidden' }}>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 12 }}>
                <thead>
                  <tr style={{ background: theme.surfaceAlt, borderBottom: `2px solid ${theme.border}` }}>
                    <th style={{ ...HDR, textAlign: 'left' }}>Store</th>
                    <th style={{ ...HDR, textAlign: 'center' }}>Type</th>
                    <th style={{ ...HDR, textAlign: 'left' }}>Zone</th>
                    <th style={{ ...HDR, textAlign: 'left' }}>Tag</th>
                    {expandedDiv
                      ? TY_MONTHS.map(m => <th key={m} style={{ ...HDR, fontSize: 10 }}>{m}</th>)
                      : allDivs.map(d => <th key={d} style={{ ...HDR, color: DIV_COLOR[d] || theme.textMuted }}>{d}</th>)
                    }
                    <th style={{ ...HDR }}>Total TY (₹L)</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredStores.map((s, i) => (
                    <tr key={s.store} style={{ borderBottom: `1px solid ${theme.border}`, background: i % 2 === 0 ? 'transparent' : theme.surfaceAlt }}>
                      <td style={{ ...CELL, textAlign: 'left', fontWeight: 600 }}>{s.store}</td>
                      <td style={{ ...CELL, textAlign: 'center' }}>
                        <span style={{ fontSize: 10, padding: '2px 6px', borderRadius: 4, fontWeight: 600, background: s.is_ssg ? `${theme.success}22` : `${theme.accent}22`, color: s.is_ssg ? theme.success : theme.accent }}>
                          {s.is_ssg ? (s.store === 'ANG' ? 'SSG - ANG' : 'SSG') : 'NSO'}
                        </span>
                      </td>
                      <td style={{ ...CELL, textAlign: 'left', color: theme.textMuted, fontSize: 11 }}>{s.cluster || '—'}</td>
                      <td style={{ ...CELL, textAlign: 'left', color: theme.textMuted, fontSize: 11 }}>{s.tag || '—'}</td>
                      {expandedDiv
                        ? TY_MONTHS.map(m => {
                            const mObj = s.divisions[expandedDiv]?.monthly[m]
                            const mVal = typeof mObj === 'object' ? (mObj?.total ?? 0) : (mObj ?? 0)
                            return (
                              <td key={m} style={{ ...CELL, color: mVal > 0 ? theme.textPrimary : theme.textMuted }}>
                                {mVal.toFixed(2)}
                              </td>
                            )
                          })
                        : allDivs.map(d => (
                            <td key={d} style={{ ...CELL, color: (s.divisions[d]?.div_total || 0) > 0 ? theme.textPrimary : theme.textMuted }}>
                              {(s.divisions[d]?.div_total ?? 0).toFixed(2)}
                            </td>
                          ))
                      }
                      <td style={{ ...CELL, fontWeight: 700, color: theme.primary }}>{s.store_total.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {/* ── DEPARTMENT VIEW ─────────────────────────────────────────────────── */}
      {viewMode === 'dept' && (
        <>
          {/* Dept view filters */}
          <div style={{ display: 'flex', gap: 10, marginBottom: 14, alignItems: 'center', flexWrap: 'wrap' }}>
            {/* Division pills */}
            <div style={{ display: 'flex', gap: 6 }}>
              {allDivs.map(d => (
                <button key={d} onClick={() => { setDeptDiv(d); setDeptFilters(new Set()); setDeptStoreFilters(new Set()) }} style={{
                  padding: '5px 14px', borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: 'pointer',
                  background: deptDiv === d ? `${DIV_COLOR[d]}33` : 'transparent',
                  color: DIV_COLOR[d] || theme.textMuted,
                  border: `1.5px solid ${deptDiv === d ? DIV_COLOR[d] : theme.border}`,
                }}>{d}</button>
              ))}
            </div>

            <div style={{ width: 1, height: 22, background: theme.border }} />

            {/* Dept slicer */}
            {!NODEPT.includes(deptDiv) && (
              <SearchSlicer
                items={allDeptsInDiv}
                selected={deptFilters}
                onChange={setDeptFilters}
                label="All Departments"
                placeholder="Search department…"
                width={170}
              />
            )}

            <select value={deptStoreType} onChange={e => setDeptStoreType(e.target.value)}
              style={{ background: theme.surfaceUp, border: `1px solid ${theme.border}`, color: theme.textPrimary, borderRadius: 7, padding: '6px 10px', fontSize: 12, outline: 'none' }}>
              <option value="ALL">All Store Types</option>
              <option value="SSG">SSG Only</option>
              <option value="NSO">NSO Only</option>
            </select>

            <SearchSlicer
              items={allStoreNames}
              selected={deptStoreFilters}
              onChange={setDeptStoreFilters}
              label="All Stores"
              placeholder="Search store…"
              width={150}
            />

            {/* Degrowth toggle */}
            <button onClick={() => setShowDegrowthOnly(v => !v)} style={{
              padding: '5px 14px', borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: 'pointer',
              background: showDegrowthOnly ? `${theme.danger}22` : 'transparent',
              color: showDegrowthOnly ? theme.danger : theme.textMuted,
              border: `1.5px solid ${showDegrowthOnly ? theme.danger : theme.border}`,
              display: 'flex', alignItems: 'center', gap: 6,
            }}>
              ↓ Degrowth Only
              {degrowthCount > 0 && (
                <span style={{ fontSize: 10, background: theme.danger, color: '#fff', borderRadius: 10, padding: '1px 6px', fontWeight: 700 }}>{degrowthCount}</span>
              )}
            </button>

            <span style={{ fontSize: 11, color: theme.textMuted, marginLeft: 4 }}>
              {deptRows.length} rows
            </span>
          </div>

          {/* GM / RETAIL guard */}
          {NODEPT.includes(deptDiv) && (
            <div style={{ padding: '20px 24px', background: theme.surface, borderRadius: 12, border: `1px solid ${theme.border}`, marginBottom: 12, display: 'flex', gap: 12, alignItems: 'flex-start' }}>
              <span style={{ fontSize: 18 }}>ℹ️</span>
              <div>
                <div style={{ fontWeight: 600, fontSize: 13, color: theme.textPrimary, marginBottom: 4 }}>{deptDiv} — Item Master Level Only</div>
                <div style={{ fontSize: 12, color: theme.textMuted }}>
                  {deptDiv} and RETAIL are sourced from the item master and do not have attribute-based dept corrections.
                  Their plans are applied at division level. Dept-level breakdown is not available here to avoid inflating the list.
                </div>
              </div>
            </div>
          )}

          {/* Dept table */}
          {!NODEPT.includes(deptDiv) && <div style={{ background: theme.surface, borderRadius: 12, border: `1px solid ${theme.border}`, overflow: 'hidden' }}>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 12 }}>
                <thead>
                  <tr style={{ background: theme.surfaceAlt, borderBottom: `2px solid ${theme.border}` }}>
                    <th style={{ ...HDR, textAlign: 'left' }}>Department</th>
                    <th style={{ ...HDR, textAlign: 'left' }}>Store</th>
                    <th style={{ ...HDR, textAlign: 'center' }}>Type</th>
                    <th style={{ ...HDR, textAlign: 'left' }}>Zone</th>
                    <th style={{ ...HDR, textAlign: 'left' }}>Tag</th>
                    <th style={{ ...HDR }}>LY (₹L)</th>
                    <th style={{ ...HDR }}>TY (₹L)</th>
                    <th style={{ ...HDR }}>Growth %</th>
                  </tr>
                </thead>
                <tbody>
                  {deptRows.slice(0, 1000).map((r, i) => {
                    const isDegrowth = r.growth !== null && r.growth < 0
                    const isNew      = r.growth === null && r.ty > 0
                    const growthColor = isDegrowth ? theme.danger : (r.growth > 0 ? theme.success : theme.textMuted)
                    return (
                      <tr key={`${r.store}-${r.dept}-${i}`}
                        style={{
                          borderBottom: `1px solid ${theme.border}`,
                          background: isDegrowth
                            ? `${theme.danger}0d`
                            : i % 2 === 0 ? 'transparent' : theme.surfaceAlt,
                        }}>
                        <td style={{ ...CELL, textAlign: 'left', fontWeight: 600, color: DIV_COLOR[deptDiv] || theme.textPrimary }}>{r.dept}</td>
                        <td style={{ ...CELL, textAlign: 'left', fontWeight: 600 }}>{r.store}</td>
                        <td style={{ ...CELL, textAlign: 'center' }}>
                          <span style={{ fontSize: 10, padding: '2px 6px', borderRadius: 4, fontWeight: 600, background: r.is_ssg ? `${theme.success}22` : `${theme.accent}22`, color: r.is_ssg ? theme.success : theme.accent }}>
                            {r.is_ssg ? (r.store === 'ANG' ? 'SSG - ANG' : 'SSG') : 'NSO'}
                          </span>
                        </td>
                        <td style={{ ...CELL, textAlign: 'left', color: theme.textMuted, fontSize: 11 }}>{r.cluster || '—'}</td>
                        <td style={{ ...CELL, textAlign: 'left', color: theme.textMuted, fontSize: 11 }}>{r.tag || '—'}</td>
                        <td style={{ ...CELL, color: theme.textMuted }}>{r.ly.toFixed(2)}</td>
                        <td style={{ ...CELL, color: theme.textPrimary, fontWeight: 600 }}>{r.ty.toFixed(2)}</td>
                        <td style={{ ...CELL, fontWeight: 700, color: growthColor }}>
                          {isNew ? <span style={{ fontSize: 10, color: theme.accent }}>New</span>
                            : r.growth !== null ? `${r.growth > 0 ? '+' : ''}${r.growth}%`
                            : '—'}
                        </td>
                      </tr>
                    )
                  })}
                  {deptRows.length > 1000 && (
                    <tr><td colSpan={8} style={{ padding: '10px 16px', textAlign: 'center', color: theme.textMuted, fontSize: 12 }}>
                      Showing first 1000 rows — use filters to narrow down.
                    </td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>}
        </>
      )}

      {/* ── CLUSTER VIEW ───────────────────────────────────────────────────── */}
      {viewMode === 'cluster' && (
        <>
          {clusterLoading && (
            <div style={{ padding: 32, textAlign: 'center', color: theme.textMuted, fontSize: 13 }}>Loading cluster plan…</div>
          )}

          {!clusterLoading && clusterPlan && (() => {
            const divs    = clusterPlan.divisions || []
            const months  = clusterPlan.months    || []
            const clusters = clusterPlan.clusters || []
            const clData  = clusterPlan.result?.[activeCluster]?.[clusterDiv] || {}
            const monthData = clData[clusterMonth] || {}
            const depts   = Object.entries(monthData).sort(([a],[b]) => b[1].ty - a[1].ty)

            // Summary: total TY and LY for selected cluster/div/month
            const totalTY = depts.reduce((s,[,d]) => s + d.ty, 0)
            const totalLY = depts.reduce((s,[,d]) => s + d.ly, 0)
            const growthPct = totalLY > 0 ? ((totalTY - totalLY) / totalLY * 100).toFixed(1) : null

            // All months summary for selected cluster/div
            const monthSummary = months.map(m => {
              const mData = clData[m] || {}
              const mTY = Object.values(mData).reduce((s,d) => s + d.ty, 0)
              return { month: m, ty: mTY }
            })

            return (
              <>
                {/* Cluster pills */}
                <div style={{ display: 'flex', gap: 6, marginBottom: 14, flexWrap: 'wrap', alignItems: 'center' }}>
                  <span style={{ fontSize: 11, color: theme.textMuted, fontWeight: 600, marginRight: 4 }}>CLUSTER</span>
                  {clusters.map(cl => {
                    const active = cl === activeCluster
                    return (
                      <button key={cl} onClick={() => setActiveCluster(cl)} style={{
                        padding: '5px 14px', borderRadius: 7, cursor: 'pointer', fontSize: 11, fontWeight: active ? 700 : 400,
                        border: `1.5px solid ${active ? theme.accent : theme.border}`,
                        background: active ? `${theme.accent}22` : theme.surface,
                        color: active ? theme.accent : theme.textSecondary,
                      }}>{cl}</button>
                    )
                  })}
                </div>

                {/* Division tabs */}
                <div style={{ display: 'flex', gap: 6, marginBottom: 14, flexWrap: 'wrap', alignItems: 'center' }}>
                  <span style={{ fontSize: 11, color: theme.textMuted, fontWeight: 600, marginRight: 4 }}>DIVISION</span>
                  {divs.map(div => {
                    const active = div === clusterDiv
                    const c = DIV_COLOR[div] || theme.primary
                    return (
                      <button key={div} onClick={() => setClusterDiv(div)} style={{
                        padding: '5px 14px', borderRadius: 7, cursor: 'pointer', fontSize: 12, fontWeight: active ? 700 : 500,
                        border: `1.5px solid ${active ? c : theme.border}`,
                        background: active ? `${c}22` : theme.surface,
                        color: active ? c : theme.textSecondary,
                      }}>{div}</button>
                    )
                  })}
                </div>

                {/* Month tabs + mini bar */}
                <div style={{ display: 'flex', gap: 6, marginBottom: 16, flexWrap: 'wrap', alignItems: 'center' }}>
                  <span style={{ fontSize: 11, color: theme.textMuted, fontWeight: 600, marginRight: 4 }}>MONTH</span>
                  {months.map(m => {
                    const active = m === clusterMonth
                    const ms = monthSummary.find(x => x.month === m)
                    return (
                      <button key={m} onClick={() => setClusterMonth(m)} style={{
                        padding: '5px 14px', borderRadius: 7, cursor: 'pointer', fontSize: 11,
                        fontWeight: active ? 700 : 400,
                        border: `1.5px solid ${active ? theme.primary : theme.border}`,
                        background: active ? `${theme.primary}22` : theme.surface,
                        color: active ? theme.primaryLight : theme.textSecondary,
                        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1,
                      }}>
                        <span>{m}</span>
                        {ms && <span style={{ fontSize: 9, color: active ? theme.primaryLight : theme.textMuted, fontFamily: theme.fontMono }}>₹{ms.ty.toFixed(0)}L</span>}
                      </button>
                    )
                  })}
                </div>

                {/* KPI row */}
                <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
                  {[
                    { label: 'Cluster', value: activeCluster },
                    { label: 'Division', value: clusterDiv, color: DIV_COLOR[clusterDiv] },
                    { label: 'Month', value: clusterMonth },
                    { label: 'TY Total (₹L)', value: totalTY.toFixed(2), color: theme.primary },
                    { label: 'LY Total (₹L)', value: totalLY.toFixed(2), color: theme.textMuted },
                    { label: 'Growth', value: growthPct != null ? `${growthPct > 0 ? '+' : ''}${growthPct}%` : '—', color: growthPct < 0 ? theme.danger : theme.success },
                    { label: 'Departments', value: depts.length },
                  ].map(k => (
                    <div key={k.label} style={{
                      background: theme.surface, borderRadius: 8, padding: '10px 16px',
                      border: `1px solid ${theme.border}`, flex: k.label === 'Cluster' ? 2 : 1,
                    }}>
                      <div style={{ fontSize: 10, color: theme.textMuted, fontWeight: 600, letterSpacing: 0.5, textTransform: 'uppercase', marginBottom: 3 }}>{k.label}</div>
                      <div style={{ fontSize: 15, fontWeight: 700, color: k.color || theme.textPrimary, fontFamily: theme.fontMono }}>{k.value ?? '—'}</div>
                    </div>
                  ))}
                </div>

                {/* Dept table */}
                <div style={{ background: theme.surface, borderRadius: 12, border: `1px solid ${theme.border}`, overflow: 'hidden' }}>
                  <div style={{ overflowX: 'auto' }}>
                    <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 12 }}>
                      <thead>
                        <tr style={{ background: theme.surfaceAlt, borderBottom: `2px solid ${theme.border}` }}>
                          <th style={{ ...HDR, textAlign: 'left', paddingLeft: 16 }}>Department</th>
                          <th style={{ ...HDR }}>LY (₹L)</th>
                          <th style={{ ...HDR }}>TY (₹L)</th>
                          <th style={{ ...HDR }}>Growth %</th>
                          <th style={{ ...HDR }}>Cont %</th>
                          <th style={{ ...HDR, textAlign: 'left', width: 180, paddingLeft: 12 }}>Cont Bar</th>
                        </tr>
                      </thead>
                      <tbody>
                        {depts.length === 0 && (
                          <tr><td colSpan={6} style={{ padding: '24px 16px', textAlign: 'center', color: theme.textMuted, fontSize: 12 }}>
                            No data for this selection.
                          </td></tr>
                        )}
                        {depts.map(([dept, d], i) => {
                          const growth = d.ly > 0 ? ((d.ty - d.ly) / d.ly * 100) : null
                          const growColor = growth === null ? theme.textMuted : growth < 0 ? theme.danger : theme.success
                          const c = DIV_COLOR[clusterDiv] || theme.primary
                          return (
                            <tr key={dept} style={{
                              borderBottom: `1px solid ${theme.border}`,
                              background: growth !== null && growth < 0
                                ? `${theme.danger}0a`
                                : i % 2 === 0 ? 'transparent' : theme.surfaceAlt,
                            }}>
                              <td style={{ ...CELL, textAlign: 'left', paddingLeft: 16, fontWeight: 600, color: c }}>{dept}</td>
                              <td style={{ ...CELL, color: theme.textMuted }}>{d.ly.toFixed(2)}</td>
                              <td style={{ ...CELL, fontWeight: 600, color: theme.textPrimary }}>{d.ty.toFixed(2)}</td>
                              <td style={{ ...CELL, fontWeight: 700, color: growColor }}>
                                {growth !== null ? `${growth > 0 ? '+' : ''}${growth.toFixed(1)}%` : <span style={{ fontSize: 10, color: theme.accent }}>New</span>}
                              </td>
                              <td style={{ ...CELL, color: theme.textSecondary }}>{d.cont_pct.toFixed(2)}%</td>
                              <td style={{ ...CELL, textAlign: 'left', paddingLeft: 12 }}>
                                <div style={{ height: 7, background: theme.border, borderRadius: 4, overflow: 'hidden', width: 160 }}>
                                  <div style={{ height: '100%', width: `${Math.min(d.cont_pct, 100)}%`, background: c, borderRadius: 4 }} />
                                </div>
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              </>
            )
          })()}
        </>
      )}

      {/* ── DASHBOARD VIEW ─────────────────────────────────────────────────── */}
      {viewMode === 'dashboard' && (
        <>
          {!dashboard ? (
            <div style={{ padding: 32, textAlign: 'center', color: theme.textMuted, fontSize: 13 }}>Loading dashboard…</div>
          ) : (
            <>
              {/* Division cards */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 12, marginBottom: 24 }}>
                {Object.entries(dashboard.divisions).sort(([a],[b]) => a.localeCompare(b)).map(([div, d]) => {
                  const isDegrow = d.growth !== null && d.growth < 0
                  const growColor = isDegrow ? theme.danger : d.growth > 0 ? theme.success : theme.textMuted
                  const isActive = dashDiv === div
                  return (
                    <div key={div} onClick={() => setDashDiv(div)} style={{
                      background: isActive ? `${DIV_COLOR[div] || theme.primary}18` : theme.surface,
                      borderRadius: 12, padding: '16px 18px', cursor: 'pointer',
                      border: `1.5px solid ${isActive ? (DIV_COLOR[div] || theme.primary) : theme.border}`,
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                        <div style={{ width: 8, height: 8, borderRadius: '50%', background: DIV_COLOR[div] || theme.textMuted }} />
                        <span style={{ fontSize: 13, fontWeight: 700, color: DIV_COLOR[div] || theme.textPrimary }}>{div}</span>
                        {!d.has_attr && <span style={{ fontSize: 9, color: theme.textMuted, background: theme.surfaceAlt, border: `1px solid ${theme.border}`, borderRadius: 4, padding: '1px 5px' }}>item master</span>}
                      </div>
                      <div style={{ fontSize: 20, fontWeight: 700, color: theme.textPrimary, fontFamily: theme.fontMono }}>₹{d.ty.toFixed(1)}L</div>
                      <div style={{ fontSize: 11, color: theme.textMuted, marginTop: 2 }}>LY ₹{d.ly.toFixed(1)}L</div>
                      <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ fontSize: 14, fontWeight: 700, color: growColor }}>
                          {d.growth !== null ? `${d.growth > 0 ? '+' : ''}${d.growth}%` : '—'}
                        </span>
                        {d.degrowth_stores > 0 && (
                          <span style={{ fontSize: 10, color: theme.danger, background: `${theme.danger}18`, border: `1px solid ${theme.danger}33`, borderRadius: 4, padding: '1px 6px' }}>
                            {d.degrowth_stores} ↓
                          </span>
                        )}
                      </div>
                      <div style={{ marginTop: 10, display: 'flex', gap: 6 }}>
                        <div style={{ flex: 1 }}>
                          <div style={{ fontSize: 9, color: theme.textMuted, marginBottom: 2 }}>SSG</div>
                          <div style={{ fontSize: 11, fontFamily: theme.fontMono, color: theme.success }}>{d.ssg_ty.toFixed(1)}</div>
                        </div>
                        <div style={{ flex: 1 }}>
                          <div style={{ fontSize: 9, color: theme.textMuted, marginBottom: 2 }}>NSO</div>
                          <div style={{ fontSize: 11, fontFamily: theme.fontMono, color: theme.accent }}>{d.nso_ty.toFixed(1)}</div>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>

              {/* Attribute breakdown for selected division */}
              {dashDiv && (() => {
                const divData = dashboard.divisions[dashDiv]
                const isNoDept = NODEPT.includes(dashDiv)
                const ATTR_COLOR = {
                  REGULAR: '#818CF8', SUMMER: '#FB923C', PREWINTER: '#4ADE80',
                  'LT WINTER': '#60A5FA', 'HVY WINTER': '#93C5FD', OCCASIONAL: '#C084FC',
                }
                return (
                  <div style={{ background: theme.surface, borderRadius: 12, border: `1px solid ${theme.border}`, overflow: 'hidden' }}>
                    <div style={{ padding: '14px 20px', borderBottom: `1px solid ${theme.border}`, display: 'flex', alignItems: 'center', gap: 10 }}>
                      <div style={{ width: 10, height: 10, borderRadius: '50%', background: DIV_COLOR[dashDiv] || theme.textMuted }} />
                      <span style={{ fontWeight: 700, fontSize: 14, color: DIV_COLOR[dashDiv] || theme.textPrimary }}>{dashDiv}</span>
                      <span style={{ fontSize: 12, color: theme.textMuted }}>— Attribute Breakdown</span>
                      {isNoDept && <span style={{ fontSize: 11, color: theme.textMuted, background: theme.surfaceAlt, border: `1px solid ${theme.border}`, borderRadius: 6, padding: '2px 10px' }}>Item master — no attribute structure</span>}
                    </div>
                    {isNoDept ? (
                      <div style={{ padding: '24px 20px', color: theme.textMuted, fontSize: 13 }}>
                        {dashDiv} uses item master sourcing. Attribute-level breakdown is not applicable — corrections are applied at division total only.
                      </div>
                    ) : (
                      <div style={{ overflowX: 'auto' }}>
                        <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 12 }}>
                          <thead>
                            <tr style={{ background: theme.surfaceAlt, borderBottom: `2px solid ${theme.border}` }}>
                              {['Attribute', 'LY (₹L)', 'TY (₹L)', 'Growth %', 'TY Share %', 'Bar'].map(h => (
                                <th key={h} style={{ ...HDR, textAlign: h === 'Attribute' || h === 'Bar' ? 'left' : 'right', padding: '10px 16px' }}>{h}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {Object.entries(divData.attributes || {})
                              .sort(([,a],[,b]) => b.ty - a.ty)
                              .map(([attr, av], i) => {
                                const isDegrow = av.growth !== null && av.growth < 0
                                const growColor = isDegrow ? theme.danger : av.growth > 0 ? theme.success : theme.textMuted
                                const share = divData.ty > 0 ? (av.ty / divData.ty * 100) : 0
                                const aColor = ATTR_COLOR[attr] || theme.textMuted
                                return (
                                  <tr key={attr} style={{ borderBottom: `1px solid ${theme.border}`, background: isDegrow ? `${theme.danger}08` : i % 2 === 0 ? 'transparent' : theme.surfaceAlt }}>
                                    <td style={{ ...CELL, textAlign: 'left', fontWeight: 600 }}>
                                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
                                        <span style={{ width: 8, height: 8, borderRadius: '50%', background: aColor, display: 'inline-block', flexShrink: 0 }} />
                                        {attr}
                                      </span>
                                    </td>
                                    <td style={{ ...CELL, color: theme.textMuted }}>{av.ly.toFixed(2)}</td>
                                    <td style={{ ...CELL, fontWeight: 600 }}>{av.ty.toFixed(2)}</td>
                                    <td style={{ ...CELL, fontWeight: 700, color: growColor }}>
                                      {av.growth !== null ? `${av.growth > 0 ? '+' : ''}${av.growth}%` : '—'}
                                    </td>
                                    <td style={{ ...CELL }}>{share.toFixed(1)}%</td>
                                    <td style={{ ...CELL, textAlign: 'left', width: 200, padding: '5px 16px' }}>
                                      <div style={{ height: 8, borderRadius: 4, background: theme.border, overflow: 'hidden' }}>
                                        <div style={{ height: '100%', width: `${Math.min(share, 100)}%`, background: aColor, borderRadius: 4 }} />
                                      </div>
                                    </td>
                                  </tr>
                                )
                              })}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                )
              })()}
            </>
          )}
        </>
      )}
    </div>
  )
}
