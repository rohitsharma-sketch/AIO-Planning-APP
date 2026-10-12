import { theme, alpha } from '../theme'
import { setGrain } from '../grain'

// user, 2026-10-12: "disable attr correction and base correction in cluster view" - both correct the plan store by
// store, so in Cluster view their page shows this instead (the header switch or the button brings them back).
export default function ClusterOff({ name }) {
  return (
    <div style={{ padding: '40px 36px', maxWidth: 760 }}>
      <div style={{ background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: 12, padding: '22px 24px' }}>
        <div style={{ fontSize: 16, fontWeight: 700, color: theme.navy, marginBottom: 8 }}>{name} is off in Cluster view</div>
        <div style={{ fontSize: 13, color: theme.textSecondary, lineHeight: 1.6, marginBottom: 16 }}>
          {name} corrects the plan store by store, so it only runs in Store view. Switch to Store to use it - the plan
          itself is the same in both views; Cluster view only shows it rolled up to clusters.
        </div>
        <button type="button" onClick={() => setGrain('store')}
          style={{ padding: '8px 16px', borderRadius: 8, fontSize: 13, fontWeight: 700, cursor: 'pointer',
                   background: 'var(--st-btn,#A8CBB7)', color: 'var(--st-btn-text,#1F4D3A)', border: `1px solid ${alpha(theme.primary, '40')}` }}>
          Switch to Store
        </button>
      </div>
    </div>
  )
}
