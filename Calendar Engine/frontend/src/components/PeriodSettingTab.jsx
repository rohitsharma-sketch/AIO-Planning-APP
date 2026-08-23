export default function PeriodSettingTab() {
  return (
    <div className="module-panel">
      <div className="card" style={{ textAlign: 'center', padding: '48px 24px' }}>
        <div style={{ fontSize: '13px', fontWeight: 700, color: 'var(--navy3)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          Phase 2
        </div>
        <h2 style={{ color: 'var(--navy)' }}>Period Setting</h2>
        <p style={{ color: 'var(--muted)' }}>
          Define fiscal periods, week numbering, and planning horizons. Configure period
          start and end dates aligned to your financial year calendar.
        </p>
      </div>
    </div>
  )
}
