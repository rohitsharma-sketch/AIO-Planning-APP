import { useState, useEffect } from 'react'
import { theme } from '../theme'
import HierarchyView from '../components/HierarchyView'

// user, 2026-10-13: "remove multiple views just keep the hierarchial view so that any view can be drilled down to" - the
// Store / Department / Cluster / Dashboard views are gone; the Hierarchy view reaches every one of them (pick the levels
// and their order). This page now reads only the pipeline status; the tree loads branch by branch.
export default function FinalResults() {
  const [ps, setPs] = useState(null)
  const [err, setErr] = useState('')

  useEffect(() => {
    fetch('/api/planning/final-results/pipeline')
      .then(r => (r.ok ? r.json() : r.json().then(e => { throw new Error(e.detail || `HTTP ${r.status}`) })))
      .then(setPs)
      .catch(e => setErr(e.message))
  }, [])

  const pipeline = ps?.pipeline || {}
  return (
    <div style={{ padding: '28px 32px', minHeight: '100vh', background: theme.surfaceAlt }}>
      <div className="sp-sub">Live view of the most advanced dept plan available. Reflects all engines that have run.</div>

      {err && <div style={{ fontSize: 12.5, color: theme.danger, marginBottom: 10 }}>Pipeline status: {err}</div>}
      {ps && (
        <div className="sp-slim" style={{ background: theme.surface, borderRadius: 10, border: `1px solid ${theme.border}`, padding: '9px 16px', marginBottom: 14, gap: '4px 10px' }}>
          <span style={{ color: theme.textMuted, fontWeight: 600, fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.6 }}>Pipeline</span>
          <span style={{ color: pipeline.buyer_synced ? theme.success : theme.textMuted, fontWeight: 600 }}>
            ✓ Master Setup <span style={{ fontWeight: 400, fontSize: 11 }}>({pipeline.buyer_synced ? "Buyer's Input ↑" : 'No MRP sync'})</span>
          </span>
          {[
            ['Base plan + new depts (BIS)', pipeline.new_depts, 'final_dept_plan.json'],
            ['Attr Correction', pipeline.attr_correction, 'attr_corrected_plan.json'],
            ['Base Correction', pipeline.base_correction, 'base_corrected_plan.json'],
          ].map(([label, done, src]) => (
            <span key={label}>
              <span style={{ color: done ? theme.success : theme.textMuted }}>→ </span>
              <span style={{ fontWeight: ps.active_source === src ? 700 : 600, color: done ? (ps.active_source === src ? theme.accent : theme.success) : theme.textMuted }}>
                {done ? '✓ ' : ''}{label}
              </span>
              {!done && <span style={{ fontSize: 11 }}> (not run)</span>}
            </span>
          ))}
          <span style={{ marginLeft: 'auto' }}>Active source: <b style={{ fontFamily: theme.fontMono, fontSize: 11 }}>{ps.active_source || '-'}</b>
            {ps.base_plan_at && <span style={{ fontSize: 11, color: theme.textMuted }} title="The base plan remakes itself within a minute of a BIS save or an AOP publish (not after a correction step has run)"> · made {ps.base_plan_at}{ps.bis_saved_at ? ` · BIS saved ${ps.bis_saved_at}` : ''}</span>}</span>
          <span style={{ flexBasis: '100%', fontSize: 12 }}><span style={{ color: theme.accent, fontWeight: 600 }}>Engines run: </span>{ps.remark}</span>
        </div>
      )}

      <HierarchyView />
    </div>
  )
}
