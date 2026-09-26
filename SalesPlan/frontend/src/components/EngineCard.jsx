import { theme } from '../theme'
import Icon from './Icon'

export default function EngineCard({ title, description, status, icon, onClick }) {
  const isActive = status === 'active'

  return (
    <div
      className={isActive ? 'sp-card' : undefined}
      role={isActive ? 'button' : undefined}
      tabIndex={isActive ? 0 : undefined}
      onClick={isActive ? onClick : undefined}
      onKeyDown={isActive ? e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick?.() } } : undefined}
      style={{
        background: theme.surface,
        border: `1px solid ${theme.border}`,
        borderRadius: 12,
        padding: '20px 22px',
        cursor: isActive ? 'pointer' : 'default',
        boxShadow: '0 1px 2px rgba(var(--st-ink-rgb,30,39,35),0.05)',
        transition: 'box-shadow 0.15s, transform 0.15s, border-color 0.15s',
        display: 'flex',
        gap: 16,
        opacity: isActive ? 1 : 0.72,
      }}
    >
      <div style={{
        width: 40, height: 40, borderRadius: 10, flexShrink: 0,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: isActive ? theme.primaryLight : theme.surfaceUp,
        color: isActive ? theme.primary : theme.textMuted,
      }}>
        <Icon name={icon} size={20} />
      </div>
      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
          <span style={{ fontSize: 15, fontWeight: 700, color: theme.navy }}>{title}</span>
          <span style={{
            fontSize: 10.5, fontWeight: 700, padding: '2px 9px', borderRadius: 999, letterSpacing: 0.4,
            textTransform: 'uppercase', whiteSpace: 'nowrap',
            background: isActive ? theme.accentLight : theme.surfaceUp,
            color: isActive ? theme.accent : theme.textMuted,
            border: `1px solid ${isActive ? '#A6E3BD' : theme.border}`,
          }}>
            {isActive ? 'Active' : 'Coming soon'}
          </span>
        </div>
        <p style={{ fontSize: 13, color: theme.textSecondary, margin: 0, lineHeight: 1.55 }}>{description}</p>
        {isActive && <span className="sp-card-go" style={{ fontSize: 12.5, fontWeight: 700, color: theme.primary, marginTop: 2 }}>Open →</span>}
      </div>
    </div>
  )
}
