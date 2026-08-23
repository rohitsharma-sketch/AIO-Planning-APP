import { useState, useCallback, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { theme } from '../theme'
import PipelineBanner from '../components/PipelineBanner'
import SearchSlicer from '../components/SearchSlicer'
import { currentEngineKey, advancePipeline } from '../pipelineState'

const CELL = { fontFamily: theme.fontMono, fontSize: 12, textAlign: 'right', padding: '5px 10px', whiteSpace: 'nowrap' }
const HDR  = { ...CELL, fontSize: 11, color: theme.textMuted, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.4 }

const DIV_COLOR = {
  KIDS: '#C85A12', LADIES: '#7420B8', MENS: '#077A4A', GM: '#1E54C0', RETAIL: '#B22620',
}

export default function BaseCorrection() {
  const navigate    = useNavigate()
  const inPipeline  = currentEngineKey() === 'base-correction'
  const [checking, setChecking]   = useState(false)
  const [applying, setApplying]   = useState(false)
  const [checkData, setCheckData] = useState(null)   // result of /check
  const [applied, setApplied]     = useState(false)
  const [filterDiv, setFilterDiv] = useState(new Set())    // empty = ALL
  const [filterSsg, setFilterSsg] = useState(new Set())    // empty = ALL
  const [searchDept, setSearchDept] = useState('')
  const [msg, setMsg]             = useState('')

  const flash = (text) => { setMsg(text); setTimeout(() => setMsg(''), 5000) }

  // Auto-run when entering via pipeline
  useEffect(() => {
    if (inPipeline) {
      setChecking(true)
      fetch('/api/base-correction/check')
        .then(r => r.ok ? r.json() : null)
        .then(d => { if (d) { setCheckData(d); setChecking(false) } })
    }
  }, [inPipeline])

  // ── Run check ──────────────────────────────────────────────────────────────
  const handleCheck = useCallback(async () => {
    setChecking(true); setCheckData(null); setApplied(false)
    try {
      const r = await fetch('/api/base-correction/check')
      if (!r.ok) { flash((await r.json()).detail || 'Error'); return }
      const d = await r.json()
      setCheckData(d)
    } catch (e) {
      flash('Network error')
    } finally {
      setChecking(false)
    }
  }, [])

  // ── Apply corrections ───────────────────────────────────────────────────────
  const handleApply = async () => {
    setApplying(true)
    try {
      const r = await fetch('/api/base-correction/apply', { method: 'POST' })
      if (!r.ok) { flash((await r.json()).detail || 'Error'); return }
      const d = await r.json()
      setCheckData(d)
      setApplied(true)
      if (inPipeline) {
        navigate(advancePipeline())
        return
      }
      flash(`Applied ${d.gap_count} SSG corrections · ${d.nso_stores_updated ?? 0} NSO stores reapportioned.`)
    } catch (e) {
      flash('Network error')
    } finally {
      setApplying(false)
    }
  }

  // ── Export ──────────────────────────────────────────────────────────────────
  const handleExport = () => {
    window.open('/api/base-correction/export', '_blank')
  }

  // ── Filtered gap list ───────────────────────────────────────────────────────
  const allGaps = checkData?.gaps || []
  const filteredGaps = allGaps.filter(g => {
    if (filterDiv.size > 0 && !filterDiv.has(g.division)) return false
    if (filterSsg.size > 0) {
      const tag = g.is_ssg ? (g.store === 'ANG' ? 'SSG - ANG' : 'SSG') : 'NSO'
      if (!filterSsg.has(tag)) return false
    }
    if (searchDept && !g.department.toLowerCase().includes(searchDept.toLowerCase())) return false
    return true
  })

  const divs = [...new Set(allGaps.map(g => g.division))].sort()

  return (
    <div style={{ padding: '28px 32px', minHeight: '100vh', background: theme.surfaceAlt }}>
      {inPipeline && <PipelineBanner currentKey="base-correction" />}
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
          <div>
            <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: theme.textPrimary }}>Base Correction</h1>
            <p style={{ margin: '6px 0 0', fontSize: 13, color: theme.textMuted }}>
              Finds active departments with TY plan = 0. Fills using zone × grade peer benchmark: Corrected TY = (LY + (MAX+AVG)/2) ÷ 2.
            </p>
          </div>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            {msg && <span style={{ fontSize: 12, color: theme.accent }}>{msg}</span>}
            {applied && (
              <button
                onClick={handleExport}
                style={{ background: 'none', border: `1px solid ${theme.border}`, color: theme.textMuted, borderRadius: 8, padding: '8px 16px', cursor: 'pointer', fontSize: 13 }}
              >
                Export Review ↓
              </button>
            )}
            {inPipeline && checkData && !applied && !applying && (
              <button
                onClick={handleApply}
                style={{ background: theme.primary, border: 'none', color: '#fff', borderRadius: 8, padding: '8px 20px', cursor: 'pointer', fontSize: 13, fontWeight: 600 }}
              >Apply & Continue →</button>
            )}
            {checkData && !applied && !inPipeline && (
              <button
                onClick={handleApply}
                disabled={applying || checkData.gap_count === 0}
                style={{
                  background: checkData.gap_count > 0 ? theme.accent : theme.border,
                  border: 'none', color: '#fff', borderRadius: 8,
                  padding: '8px 20px', cursor: applying || !checkData.gap_count ? 'default' : 'pointer',
                  fontSize: 13, fontWeight: 600, opacity: applying ? 0.7 : 1,
                }}
              >
                {applying ? 'Applying…' : `Apply ${checkData.gap_count} Corrections`}
              </button>
            )}
            <button
              onClick={handleCheck}
              disabled={checking}
              style={{
                background: theme.primary, border: 'none', color: '#fff', borderRadius: 8,
                padding: '8px 20px', cursor: checking ? 'default' : 'pointer',
                fontSize: 13, fontWeight: 600, opacity: checking ? 0.7 : 1,
              }}
            >
              {checking ? 'Scanning…' : 'Run Check'}
            </button>
          </div>
        </div>

        <div style={{ marginTop: 14, padding: '10px 16px', background: theme.surface, borderRadius: 8, border: `1px solid ${theme.border}`, fontSize: 12, color: theme.textMuted, display: 'flex', gap: 8 }}>
          <span style={{ color: theme.accent, fontWeight: 700 }}>ℹ</span>
          <span>
            Source: attr_corrected_plan.json if available, else final_dept_plan.json (post New Depts).
            Only active-plan months are scanned. Fix formula: <strong>col3 = (MAX + AVG of zone×grade SSG peers) ÷ 2 &nbsp;→&nbsp; Corrected TY = (LY + col3) ÷ 2</strong>.
          </span>
        </div>
      </div>

      {/* No data yet */}
      {!checkData && !checking && (
        <div style={{ padding: 48, background: theme.surface, borderRadius: 12, border: `1px solid ${theme.border}`, textAlign: 'center' }}>
          <div style={{ fontSize: 36, marginBottom: 14 }}>🔍</div>
          <div style={{ fontSize: 15, fontWeight: 600, color: theme.textPrimary, marginBottom: 8 }}>Ready to scan</div>
          <div style={{ fontSize: 13, color: theme.textMuted }}>
            Click <strong>Run Check</strong> to scan for zero-TY gaps across all active departments.
          </div>
        </div>
      )}

      {checking && (
        <div style={{ padding: 40, textAlign: 'center', color: theme.textMuted, fontSize: 13 }}>Scanning plan for gaps…</div>
      )}

      {/* Summary cards */}
      {checkData && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 12, marginBottom: 20 }}>
            {[
              { label: 'Total Gaps', value: checkData.gap_count, color: checkData.gap_count > 0 ? theme.danger : theme.success },
              { label: 'SSG Gaps', value: (checkData.gaps || []).filter(g => g.is_ssg).length, color: theme.success },
              { label: 'NSO Gaps', value: (checkData.gaps || []).filter(g => !g.is_ssg).length, color: theme.accent },
              { label: 'LY at Risk (₹L)', value: checkData.total_ly_at_risk?.toFixed(2), color: theme.danger },
              { label: 'Corrected TY (₹L)', value: checkData.total_corrected_ty?.toFixed(2), color: theme.success },
            ].map(c => (
              <div key={c.label} style={{ background: theme.surface, borderRadius: 10, padding: '14px 16px', border: `1px solid ${theme.border}` }}>
                <div style={{ fontSize: 11, color: theme.textMuted, marginBottom: 4 }}>{c.label}</div>
                <div style={{ fontSize: 22, fontWeight: 700, color: c.color, fontFamily: theme.fontMono }}>{c.value}</div>
              </div>
            ))}
          </div>

          {/* Division breakdown pills */}
          {Object.keys(checkData.by_division || {}).length > 0 && (
            <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
              {Object.entries(checkData.by_division).sort((a, b) => b[1] - a[1]).map(([div, cnt]) => (
                <div key={div} style={{
                  padding: '4px 12px', borderRadius: 20, fontSize: 11, fontWeight: 600,
                  background: `${DIV_COLOR[div] || theme.border}22`,
                  color: DIV_COLOR[div] || theme.textMuted,
                  border: `1px solid ${DIV_COLOR[div] || theme.border}`,
                }}>
                  {div}: {cnt}
                </div>
              ))}
            </div>
          )}

          {checkData.gap_count === 0 ? (
            <div style={{ padding: 32, background: theme.surface, borderRadius: 12, border: `1px solid ${theme.border}`, textAlign: 'center' }}>
              <div style={{ fontSize: 28, marginBottom: 10 }}>✅</div>
              <div style={{ fontSize: 14, color: theme.success, fontWeight: 600 }}>No gaps found</div>
              <div style={{ fontSize: 12, color: theme.textMuted, marginTop: 6 }}>
                All active departments have a TY plan wherever LY actuals exist.
              </div>
            </div>
          ) : (
            <>
              {/* Applied banner */}
              {applied && (
                <div style={{ padding: '10px 16px', background: `${theme.success}22`, border: `1px solid ${theme.success}`, borderRadius: 8, fontSize: 12, color: theme.success, marginBottom: 14, fontWeight: 600 }}>
                  ✓ {checkData.gap_count} corrections applied — base_corrected_plan.json written. Export the review sheet for a full audit trail.
                </div>
              )}

              {/* Filters */}
              <div style={{ display: 'flex', gap: 10, marginBottom: 12, alignItems: 'center' }}>
                <input
                  placeholder="Search department…"
                  value={searchDept}
                  onChange={e => setSearchDept(e.target.value)}
                  style={{ background: theme.surfaceUp, border: `1px solid ${theme.border}`, color: theme.textPrimary, borderRadius: 7, padding: '6px 12px', fontSize: 12, outline: 'none', width: 200 }}
                />
                <SearchSlicer
                  items={divs}
                  selected={filterDiv}
                  onChange={setFilterDiv}
                  label="All Divisions"
                  placeholder="Search division…"
                  width={140}
                />
                <SearchSlicer
                  items={['SSG', 'SSG - ANG', 'NSO']}
                  selected={filterSsg}
                  onChange={setFilterSsg}
                  label="All Store Types"
                  placeholder="Search type…"
                  width={150}
                />
                <span style={{ fontSize: 11, color: theme.textMuted }}>Showing {filteredGaps.length} of {allGaps.length}</span>
              </div>

              {/* Review table */}
              <div style={{ background: theme.surface, borderRadius: 12, border: `1px solid ${theme.border}`, overflow: 'hidden' }}>
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 12 }}>
                    <thead>
                      <tr style={{ background: theme.surfaceAlt, borderBottom: `2px solid ${theme.border}` }}>
                        {['Store','Type','Zone','Grade','Division','Department','TY Month','LY Month','LY Actuals','Benchmark','Corrected TY','Method'].map(h => (
                          <th key={h} style={{ ...HDR, padding: '10px 12px', textAlign: ['Store','Zone','Division','Department','Method'].includes(h) ? 'left' : 'right' }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {filteredGaps.slice(0, 500).map((g, i) => {
                        const divColor = DIV_COLOR[g.division] || theme.textMuted
                        return (
                          <tr key={i} style={{ borderBottom: `1px solid ${theme.border}`, background: i % 2 === 0 ? 'transparent' : theme.surfaceAlt }}>
                            <td style={{ ...CELL, textAlign: 'left', fontWeight: 600 }}>{g.store}</td>
                            <td style={{ ...CELL, textAlign: 'center' }}>
                              <span style={{
                                fontSize: 10, padding: '2px 6px', borderRadius: 4, fontWeight: 600,
                                background: g.is_ssg ? `${theme.success}22` : `${theme.accent}22`,
                                color: g.is_ssg ? theme.success : theme.accent,
                              }}>{g.is_ssg ? (g.store === 'ANG' ? 'SSG - ANG' : 'SSG') : 'NSO'}</span>
                            </td>
                            <td style={{ ...CELL, textAlign: 'left', color: theme.textMuted, fontSize: 11 }}>{g.zone || '—'}</td>
                            <td style={{ ...CELL, color: theme.textMuted, fontSize: 11 }}>{g.grade || '—'}</td>
                            <td style={{ ...CELL, textAlign: 'left' }}>
                              <span style={{ color: divColor, fontWeight: 600 }}>{g.division}</span>
                            </td>
                            <td style={{ ...CELL, textAlign: 'left', color: theme.textPrimary }}>{g.department}</td>
                            <td style={{ ...CELL, color: theme.accent }}>{g.ty_month}</td>
                            <td style={{ ...CELL, color: theme.textMuted }}>{g.ly_month}</td>
                            <td style={{ ...CELL, color: theme.danger }}>{g.ly.toFixed(2)}</td>
                            <td style={{ ...CELL, color: theme.textMuted }}>{g.col3_benchmark?.toFixed(2) ?? '—'}</td>
                            <td style={{ ...CELL, color: theme.success, fontWeight: 600 }}>{g.corrected_ty.toFixed(2)}</td>
                            <td style={{ ...CELL, textAlign: 'left', color: theme.textMuted, fontSize: 11 }}>{g.method}</td>
                          </tr>
                        )
                      })}
                      {filteredGaps.length > 500 && (
                        <tr>
                          <td colSpan={12} style={{ padding: '10px 16px', textAlign: 'center', color: theme.textMuted, fontSize: 12 }}>
                            Showing first 500 rows. Export for full data.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}
