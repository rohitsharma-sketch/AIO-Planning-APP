import { theme } from '../theme'

export default function EngineCard({ title, description, status, onClick }) {
  const isActive = status === 'active'

  return (
    <div
      onClick={isActive ? onClick : undefined}
      style={{
        background: theme.surface,
        border: `1px solid ${theme.border}`,
        borderLeft: isActive ? `4px solid ${theme.primary}` : `4px solid ${theme.border}`,
        borderRadius: 10,
        padding: '22px 24px',
        cursor: isActive ? 'pointer' : 'default',
        boxShadow: '0 1px 4px rgba(27,79,138,0.07)',
        transition: 'box-shadow 0.15s, transform 0.15s',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
      }}
      onMouseEnter={e => {
        if (isActive) {
          e.currentTarget.style.boxShadow = '0 4px 16px rgba(27,79,138,0.14)'
          e.currentTarget.style.transform = 'translateY(-2px)'
        }
      }}
      onMouseLeave={e => {
        e.currentTarget.style.boxShadow = '0 1px 4px rgba(27,79,138,0.07)'
        e.currentTarget.style.transform = 'translateY(0)'
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: 15, fontWeight: 700, color: theme.textPrimary }}>{title}</span>
        <span style={{
          fontSize: 11,
          fontWeight: 600,
          padding: '3px 10px',
          borderRadius: 20,
          background: isActive ? theme.accentLight : theme.surfaceAlt,
          color: isActive ? theme.accent : theme.textMuted,
          letterSpacing: 0.4,
        }}>
          {isActive ? 'Active' : 'Coming Soon'}
        </span>
      </div>
      <p style={{ fontSize: 13, color: theme.textSecondary, margin: 0, lineHeight: 1.55 }}>{description}</p>
    </div>
  )
}
