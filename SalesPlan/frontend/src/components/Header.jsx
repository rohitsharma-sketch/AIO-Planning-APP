import { theme } from '../theme'

export default function Header({ title }) {
  const today = new Date().toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })

  return (
    <div style={{
      height: 56,
      background: theme.surface,
      borderBottom: `1px solid ${theme.border}`,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '0 28px',
      flexShrink: 0,
    }}>
      <span style={{ fontSize: 16, fontWeight: 600, color: theme.textPrimary }}>{title}</span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <span style={{ fontSize: 13, color: theme.textSecondary }}>{today}</span>
        <span style={{
          fontSize: 12,
          fontWeight: 600,
          background: theme.primary,
          color: '#fff',
          borderRadius: 6,
          padding: '4px 10px',
          letterSpacing: 0.4,
        }}>FY 2025-26</span>
      </div>
    </div>
  )
}
