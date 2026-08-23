import { useState } from 'react'

// NOTE: `validationIssues` are the actual objects returned by `lib/engine.js`'s
// `validate()` — `{ type: 'error'|'warn'|'info', icon, title, desc }` — not
// plain strings as the task-8 brief's illustrative snippet assumed. Rendered
// accordingly below (title + desc, color keyed off `type`).
export default function OutputSection({ dayMap, validationIssues, monthlySummary }) {
  const [activeSub, setActiveSub] = useState('day')

  if (!dayMap) return null

  const issueColor = { error: 'var(--red)', warn: 'var(--warn, orange)', info: 'var(--muted)' }

  return (
    <div className="card">
      <div className="tabs">
        <button className={activeSub === 'day' ? 'active' : ''} onClick={() => setActiveSub('day')}>Day-by-Day Mapping</button>
        <button className={activeSub === 'monthly' ? 'active' : ''} onClick={() => setActiveSub('monthly')}>Monthly Summary</button>
        <button className={activeSub === 'validation' ? 'active' : ''} onClick={() => setActiveSub('validation')}>Validation</button>
      </div>

      {activeSub === 'day' && (
        <div className="tbl-wrap">
          <table>
            <thead>
              <tr>
                <th>Ref Date</th><th>Ref Day</th><th>Ref Wk</th><th>Festival</th><th>Category</th>
                <th>Position</th><th>→</th><th>Future Date</th><th>Future Day</th><th>Future Wk</th>
                <th>Fut Festival</th><th>Mapping Type</th><th>Score</th><th>Mo</th><th>Wd</th><th>Day Delta</th>
              </tr>
            </thead>
            <tbody>
              {dayMap.map((row, i) => (
                <tr key={i}>
                  <td>{row.refDate}</td><td>{row.refDay}</td><td>{row.refWeek}</td><td>{row.festival}</td>
                  <td>{row.category}</td><td>{row.position}</td><td>→</td><td>{row.futDate}</td>
                  <td>{row.futDay}</td><td>{row.futWeek}</td><td>{row.futFestival}</td><td>{row.mappingType}</td>
                  <td>{row.score}</td><td>{row.monthDelta}</td><td>{row.weekdayDelta}</td><td>{row.dayDelta}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {activeSub === 'monthly' && monthlySummary && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
          <div>
            <h4>By Reference Month</h4>
            <pre>{JSON.stringify(monthlySummary.byRef, null, 2)}</pre>
          </div>
          <div>
            <h4>By Future Month</h4>
            <pre>{JSON.stringify(monthlySummary.byFut, null, 2)}</pre>
          </div>
        </div>
      )}

      {activeSub === 'validation' && (
        <ul>
          {validationIssues.length === 0
            ? <li style={{ color: 'var(--green)' }}>No issues found.</li>
            : validationIssues.map((issue, i) => (
              <li key={i} style={{ color: issueColor[issue.type] || 'var(--red)' }}>
                <strong>{issue.title}</strong>: {issue.desc}
              </li>
            ))}
        </ul>
      )}
    </div>
  )
}
