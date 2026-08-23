import { useState, useMemo } from 'react'

// NOTE: `validationIssues` are the actual objects returned by `lib/engine.js`'s
// `validate()` — `{ type: 'error'|'warn'|'info', icon, title, desc }` — not
// plain strings as the task-8 brief's illustrative snippet assumed. Rendered
// accordingly below (title + desc, colour keyed off `type`).
//
// `dayMap` rows are built by index.jsx's toRow(): `category` carries
// engine.js's own `festiveCategory` string verbatim ('Pre-Festive' /
// 'Core Festive' / 'Post-Festive' / 'Non-Festive'), and monthDelta/weekdayDelta
// are the strings 'Yes'/'No'. The two lookup tables below are ported from the
// old app's renderDayTable() (calendar_engine.html lines 1841-1842) and key off
// exactly those values.
const CAT_BADGE = { 'Pre-Festive': 'b-pre', 'Core Festive': 'b-core', 'Post-Festive': 'b-post', 'Non-Festive': 'b-non' }
const CAT_ROW = { 'Pre-Festive': 'r-pre', 'Core Festive': 'r-core', 'Post-Festive': 'r-post', 'Non-Festive': '' }

// Ported from calendar_engine.html's renderValidation() (line ~1958).
const VAL_CLASS = { error: 'val-error', warn: 'val-warn', info: 'val-info' }

export default function OutputSection({ dayMap, validationIssues, monthlySummary }) {
  const [activeSub, setActiveSub] = useState('day')

  // Stats row (old app's renderStats(), calendar_engine.html lines 1762-1775).
  // Every figure is a count over data this component is already handed — no
  // extra fetching. `festival` is '' for non-festive rows (see toRow()).
  const stats = useMemo(() => {
    if (!dayMap) return null
    const total = dayMap.length
    const festive = dayMap.filter(r => r.festival).length
    return {
      total,
      festive,
      nonFestive: total - festive,
      sameMonth: dayMap.filter(r => r.monthDelta === 'Yes').length,
      sameWeekday: dayMap.filter(r => r.weekdayDelta === 'Yes').length,
      errors: (validationIssues || []).filter(i => i.type === 'error').length,
    }
  }, [dayMap, validationIssues])

  if (!dayMap) return null

  return (
    <div className="card">
      <div className="tabs">
        <button className={activeSub === 'day' ? 'active' : ''} onClick={() => setActiveSub('day')}>Day-by-Day Mapping</button>
        <button className={activeSub === 'monthly' ? 'active' : ''} onClick={() => setActiveSub('monthly')}>Monthly Summary</button>
        <button className={activeSub === 'validation' ? 'active' : ''} onClick={() => setActiveSub('validation')}>Validation</button>
      </div>

      {activeSub === 'day' && (
        <>
          {stats && (
            <div className="stats">
              <div className="stat"><div className="stat-val" style={{ color: 'var(--navy)' }}>{stats.total}</div><div className="stat-lbl">Total Days Mapped</div></div>
              <div className="stat"><div className="stat-val" style={{ color: 'var(--warn)' }}>{stats.festive}</div><div className="stat-lbl">Festive Days</div></div>
              <div className="stat"><div className="stat-val" style={{ color: 'var(--char)' }}>{stats.nonFestive}</div><div className="stat-lbl">Non-Festive Days</div></div>
              <div className="stat"><div className="stat-val" style={{ color: 'var(--green)' }}>{stats.sameMonth}</div><div className="stat-lbl">Same Month Mapped</div></div>
              <div className="stat"><div className="stat-val" style={{ color: 'var(--green)' }}>{stats.sameWeekday}</div><div className="stat-lbl">Same Weekday Matched</div></div>
              <div className="stat"><div className="stat-val" style={{ color: stats.errors ? 'var(--red)' : 'var(--green)' }}>{stats.errors}</div><div className="stat-lbl">Validation Errors</div></div>
            </div>
          )}
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
                  <tr key={i} className={CAT_ROW[row.category] || ''}>
                    <td className="date-mono">{row.refDate}</td>
                    <td>{row.refDay}</td>
                    <td style={{ color: 'var(--muted)' }}>{row.refWeek}</td>
                    <td>{row.festival || <span style={{ color: 'var(--muted)' }}>—</span>}</td>
                    <td><span className={`badge ${CAT_BADGE[row.category] || 'b-non'}`}>{row.category}</span></td>
                    <td style={{ color: 'var(--muted)' }}>{row.position}</td>
                    <td className="arrow-sep">→</td>
                    <td className="date-mono">{row.futDate}</td>
                    <td>{row.futDay}</td>
                    <td style={{ color: 'var(--muted)' }}>{row.futWeek}</td>
                    <td style={{ color: 'var(--muted)' }}>{row.futFestival || '—'}</td>
                    <td><span className="b-map">{row.mappingType}</span></td>
                    <td style={{ textAlign: 'right', color: 'var(--muted)' }}>{row.score}</td>
                    <td><span className={row.monthDelta === 'Yes' ? 'check' : 'cross'}>{row.monthDelta}</span></td>
                    <td><span className={row.weekdayDelta === 'Yes' ? 'check' : 'cross'}>{row.weekdayDelta}</span></td>
                    <td style={{ textAlign: 'right', color: Math.abs(row.dayDelta) > 30 ? 'var(--warn)' : 'var(--muted)' }}>
                      {row.dayDelta >= 0 ? '+' : ''}{row.dayDelta}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
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
        validationIssues.length === 0 ? (
          <div className="empty-state">
            <p style={{ fontWeight: 600, marginBottom: '4px' }}>No validation issues found</p>
            <p>All mappings passed the validation checks.</p>
          </div>
        ) : (
          <>
            <div className="section-heading">
              <h4>Validation Results</h4>
              <span className="count">{validationIssues.length} issue{validationIssues.length > 1 ? 's' : ''}</span>
            </div>
            <div className="val-list">
              {validationIssues.map((issue, i) => (
                <div key={i} className={`val-item ${VAL_CLASS[issue.type] || 'val-info'}`}>
                  <div className="val-icon">{issue.icon}</div>
                  <div className="val-txt">
                    <div className="val-title">{issue.title}</div>
                    <div className="val-desc">{issue.desc}</div>
                  </div>
                </div>
              ))}
            </div>
          </>
        )
      )}
    </div>
  )
}
