import { theme, alpha } from '../theme'
import { useEngines } from '../engines'

// an optional engine switched off in the sidebar (2026-10-14): its page says so instead of running it
export function EngineGate({ k, name, children }) {
  const [on, set, loaded] = useEngines()
  if (!loaded) return null   // the switches not read yet
  if (on(k)) return children
  return (
    <div style={{ padding: '40px 36px', maxWidth: 760 }}>
      <div style={{ background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: 12, padding: '22px 24px' }}>
        <div style={{ fontSize: 16, fontWeight: 700, color: theme.navy, marginBottom: 8 }}>{name} is switched off</div>
        <div style={{ fontSize: 13, color: theme.textSecondary, lineHeight: 1.6, marginBottom: 16 }}>
          It is skipped in the flow and its output is not used by the plan. Switch it on (here or with its switch in the
          sidebar) to use it - anything it made before comes back as it was.
        </div>
        <button type="button" onClick={() => set(k, true).catch(() => {})}
          style={{ padding: '8px 16px', borderRadius: 8, fontSize: 13, fontWeight: 700, cursor: 'pointer',
                   background: 'var(--st-btn,#A8CBB7)', color: 'var(--st-btn-text,#1F4D3A)', border: `1px solid ${alpha(theme.primary, '40')}` }}>
          Switch {name} on
        </button>
      </div>
    </div>
  )
}
