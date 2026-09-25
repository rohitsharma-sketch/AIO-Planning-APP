import { useNavigate } from 'react-router-dom'
import EngineCard from '../components/EngineCard'
import { theme } from '../theme'

const engines = [
  {
    title: 'Division Based Plan',
    description: 'Build annual sales targets by division with growth rates, seasonality index, and monthly distribution.',
    status: 'active',
    icon: 'division',
    route: '/division-plan',
  },
  {
    title: 'Department Based Plan',
    description: 'Drill down to department level within each division for granular sales planning.',
    status: 'active',
    icon: 'dept',
    route: '/department-plan',
  },
  {
    title: 'MRP / Article Plan',
    description: 'Buyer-supplied MRP price points with P1/P2 contribution % splits feeding the department plan.',
    status: 'active',
    icon: 'mrp',
    route: '/mrp-plan/import',
  },
  {
    title: 'Display Type Plan',
    description: 'Allocate sales targets across display types — gondola, endcap, wall fixture — by store format.',
    status: 'coming-soon',
    icon: 'display',
  },
]

export default function Home() {
  const navigate = useNavigate()

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ flex: 1, padding: '36px 40px 48px', overflowY: 'auto', background: theme.surfaceAlt }}>
        <div style={{ maxWidth: 1080 }}>
          {/* Hero - same landing pattern as the AOP Forecaster */}
          <span style={{
            display: 'inline-block', fontSize: 11, fontWeight: 800, letterSpacing: 1.2, textTransform: 'uppercase',
            color: theme.primary, background: theme.primaryLight, border: '1px solid #E2BFCB',
            borderRadius: 999, padding: '4px 12px',
          }}>Sales Plan · FY 2027–28</span>
          <h1 style={{ fontSize: 30, fontWeight: 800, color: theme.navy, margin: '14px 0 8px', letterSpacing: '-0.02em' }}>
            Sales Plan Engine
          </h1>
          <p style={{ fontSize: 15, color: theme.textSecondary, margin: 0, maxWidth: 620, lineHeight: 1.6 }}>
            Build, review, and export structured sales plans across divisions, departments, and articles.
            Pick an engine to get started.
          </p>

          <div style={{ fontSize: 11, fontWeight: 800, color: theme.textMuted, letterSpacing: 1.2, textTransform: 'uppercase', margin: '36px 0 14px' }}>
            Planning engines
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: 16 }}>
            {engines.map(eng => (
              <EngineCard
                key={eng.title}
                title={eng.title}
                description={eng.description}
                status={eng.status}
                icon={eng.icon}
                onClick={eng.route ? () => navigate(eng.route) : undefined}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
