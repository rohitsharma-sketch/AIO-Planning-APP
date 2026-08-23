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

// Full month names, matching the old app's own MONTHS const (calendar_engine.html
// line 1336) that renderMonthly() indexes by month number — and the same local
// convention DateShiftPreviewPanel.jsx already uses. The By-Future-Month
// contribution pills slice these to 3 chars exactly as the old app does.
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December']

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

  // Monthly Summary derivations — ported 1:1 from the old app's renderMonthly()
  // (calendar_engine.html lines 1870-1941). Both loops walk months 0-11 and
  // `continue` past any month whose total is 0, so empty months are skipped
  // rather than rendered as blank rows; the TOTAL row therefore sums only the
  // months actually shown (which, since skipped months contribute 0, equals the
  // grand total either way).
  const { refRows, refTotals, futRows } = useMemo(() => {
    if (!monthlySummary) return { refRows: [], refTotals: null, futRows: [] }
    const { byRef, byFut } = monthlySummary
    const totals = { total: 0, same: 0, prev: 0, next: 0, other: 0, pre: 0, core: 0, post: 0, non: 0 }
    const rRows = []
    for (let m = 0; m < 12; m++) {
      const r = byRef[m]
      if (!r || r.total === 0) continue
      totals.total += r.total; totals.same += r.sameMonth; totals.prev += r.prevMonth
      totals.next += r.nextMonth; totals.other += r.other
      totals.pre += r.pre; totals.core += r.core; totals.post += r.post; totals.non += r.non
      // "Shifted out" = every day of this ref month that did NOT land in the
      // same-numbered future month (old app: prevMonth + nextMonth + other).
      rRows.push({ m, r, lost: r.prevMonth + r.nextMonth + r.other })
    }
    const fRows = []
    for (let m = 0; m < 12; m++) {
      const f = byFut[m]
      if (!f || f.total === 0) continue
      const contribs = Object.entries(f.daysFromRef)
        .sort((a, b) => +a[0] - +b[0])
        .map(([rm, cnt]) => ({ rm: +rm, cnt, isSameMonth: +rm === m }))
      const externalDays = contribs.filter(c => !c.isSameMonth).reduce((a, c) => a + c.cnt, 0)
      fRows.push({ m, f, contribs, externalDays })
    }
    return { refRows: rRows, refTotals: totals, futRows: fRows }
  }, [monthlySummary])

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
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(520px, 1fr))', gap: '20px' }}>
          {/* ── By Reference Month ─────────────────────────────────────── */}
          <div>
            <div className="section-heading"><h4>By Reference Month — Where did each month map to?</h4></div>
            <div className="tbl-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Ref Month</th>
                    <th className="num">Total</th>
                    <th className="num" title="Mapped to same future month">Same Mo</th>
                    <th className="num" title="Mapped to previous month">← Prev</th>
                    <th className="num" title="Mapped to next month">→ Next</th>
                    <th className="num">Pre-Fest</th>
                    <th className="num">Core</th>
                    <th className="num">Post-Fest</th>
                    <th className="num">Non-Fest</th>
                    <th>Net Month Shift</th>
                  </tr>
                </thead>
                <tbody>
                  {refRows.map(({ m, r, lost }) => (
                    <tr key={m}>
                      <td className="month-nm">{MONTHS[m]}</td>
                      <td className="num">{r.total}</td>
                      <td className="num">{r.sameMonth}</td>
                      <td className="num" style={{ color: r.prevMonth > 0 ? 'var(--warn)' : 'var(--muted)' }}>{r.prevMonth || '—'}</td>
                      <td className="num" style={{ color: r.nextMonth > 0 ? 'var(--warn)' : 'var(--muted)' }}>{r.nextMonth || '—'}</td>
                      <td className="num" style={{ color: 'var(--pre-text)' }}>{r.pre || '—'}</td>
                      <td className="num" style={{ color: 'var(--core-text)', fontWeight: 700 }}>{r.core || '—'}</td>
                      <td className="num" style={{ color: 'var(--post-text)' }}>{r.post || '—'}</td>
                      <td className="num" style={{ color: 'var(--muted)' }}>{r.non}</td>
                      <td>
                        {lost === 0
                          ? <span className="shift-pill shift-neutral">Neutral</span>
                          : <span className="shift-pill shift-loss">−{lost} day{lost > 1 ? 's' : ''} shifted out</span>}
                      </td>
                    </tr>
                  ))}
                  <tr className="total-row">
                    <td>TOTAL</td>
                    <td className="num">{refTotals.total}</td>
                    <td className="num">{refTotals.same}</td>
                    <td className="num">{refTotals.prev}</td>
                    <td className="num">{refTotals.next}</td>
                    <td className="num">{refTotals.pre}</td>
                    <td className="num">{refTotals.core}</td>
                    <td className="num">{refTotals.post}</td>
                    <td className="num">{refTotals.non}</td>
                    <td></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* ── By Future Month ────────────────────────────────────────── */}
          <div>
            <div className="section-heading"><h4>By Future Month — Which reference months feed each future month?</h4></div>
            <div className="tbl-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Future Month</th>
                    <th className="num">Total Days</th>
                    <th>Contributions from Reference</th>
                  </tr>
                </thead>
                <tbody>
                  {futRows.map(({ m, f, contribs, externalDays }) => (
                    <tr key={m}>
                      <td className="month-nm">{MONTHS[m]}</td>
                      <td className="num">{f.total}</td>
                      <td>
                        {contribs.map(({ rm, cnt, isSameMonth }) => (
                          <span
                            key={rm}
                            style={{
                              fontSize: '11px',
                              background: isSameMonth ? 'var(--light)' : 'var(--pre-bg)',
                              color: isSameMonth ? 'var(--navy)' : 'var(--pre-text)',
                              padding: '1px 7px',
                              borderRadius: '10px',
                              fontWeight: 600,
                              marginRight: '4px',
                              display: 'inline-block',
                            }}
                          >
                            {MONTHS[rm].slice(0, 3)}: {cnt}
                          </span>
                        ))}
                        {externalDays > 0 && (
                          <span className="shift-pill shift-gain" style={{ marginLeft: '4px' }}>+{externalDays} shifted in</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
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
