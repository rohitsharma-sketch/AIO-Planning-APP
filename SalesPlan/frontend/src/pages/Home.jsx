import { useNavigate } from 'react-router-dom'
import Header from '../components/Header'
import EngineCard from '../components/EngineCard'
import { theme } from '../theme'

const engines = [
  {
    title: 'Division Based Plan',
    description: 'Build annual sales targets by division with growth rates, seasonality index, and monthly distribution.',
    status: 'active',
    route: '/division-plan',
  },
  {
    title: 'Department Based Plan',
    description: 'Drill down to department level within each division for granular sales planning.',
    status: 'active',
    route: '/department-plan',
  },
  {
    title: 'MRP / Article Plan',
    description: 'Buyer-supplied MRP price points with P1/P2 contribution % splits feeding the department plan.',
    status: 'active',
    route: '/mrp-plan/import',
  },
  {
    title: 'Display Type Plan',
    description: 'Allocate sales targets across display types — gondola, endcap, wall fixture — by store format.',
    status: 'coming-soon',
  },
]

export default function Home() {
  const navigate = useNavigate()

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Header title="Dashboard" />
      <div style={{ flex: 1, padding: '28px 32px', overflowY: 'auto', background: theme.surfaceAlt }}>
        <div style={{
          background: `linear-gradient(135deg, ${theme.primary} 0%, ${theme.primaryLight} 100%)`,
          borderRadius: 12,
          padding: '28px 32px',
          marginBottom: 32,
          color: '#fff',
        }}>
          <div style={{ fontSize: 22, fontWeight: 700, marginBottom: 6 }}>Sales Plan Engine — FY 2027-28</div>
          <div style={{ fontSize: 14, opacity: 0.82, maxWidth: 520 }}>
            Build, review, and export structured sales plans across divisions, departments, and articles. Select an engine below to get started.
          </div>
        </div>

        <div style={{ fontSize: 13, fontWeight: 600, color: theme.textMuted, letterSpacing: 0.8, textTransform: 'uppercase', marginBottom: 16 }}>
          Planning Engines
        </div>

        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(2, 1fr)',
          gap: 20,
        }}>
          {engines.map(eng => (
            <EngineCard
              key={eng.title}
              title={eng.title}
              description={eng.description}
              status={eng.status}
              onClick={eng.route ? () => navigate(eng.route) : undefined}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
