import { useNavigate } from 'react-router-dom'
import { theme, alpha } from '../theme'
import { ENGINE_META, getPipeline, clearPipeline } from '../pipelineState'

export default function PipelineBanner({ currentKey }) {
  const navigate = useNavigate()
  const p = getPipeline()
  if (!p) return null

  return (
    <div style={{
      marginBottom: 20, padding: '10px 18px', borderRadius: 9,
      background: `${alpha('var(--st-btn,#A8CBB7)','12')}`, border: `1px solid ${alpha('var(--st-btn-hover,#95BFA7)','55')}`,
      display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
    }}>
      <span style={{ fontSize: 11, color: theme.primary, fontWeight: 700, letterSpacing: 0.4 }}>PIPELINE</span>
      {p.queue.map((key, i) => {
        const meta  = ENGINE_META[key]
        const done  = i < p.current
        const active = i === p.current
        return (
          <span key={key} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            {i > 0 && <span style={{ color: theme.border, fontSize: 13 }}>→</span>}
            <span style={{
              fontSize: 11, padding: '2px 10px', borderRadius: 5, fontWeight: 600,
              background: done ? `${alpha(theme.success,'22')}` : active ? `${alpha(theme.primary,'22')}` : theme.surfaceAlt,
              color: done ? theme.success : active ? theme.primary : theme.textMuted,
              border: `1px solid ${done ? theme.success : active ? theme.primary : theme.border}`,
            }}>
              {done ? '✓ ' : ''}{meta?.label ?? key}
            </span>
          </span>
        )
      })}
      <span style={{ color: theme.border, fontSize: 13 }}>→</span>
      <span style={{ fontSize: 11, color: theme.textMuted, padding: '2px 10px', borderRadius: 5, border: `1px solid ${theme.border}` }}>Final Results</span>
      <div style={{ flex: 1 }} />
      <button onClick={() => { clearPipeline(); navigate('/department-plan/final-results') }}
        style={{ fontSize: 11, color: theme.textMuted, background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline', padding: 0 }}>
        Skip to Final Results
      </button>
    </div>
  )
}
