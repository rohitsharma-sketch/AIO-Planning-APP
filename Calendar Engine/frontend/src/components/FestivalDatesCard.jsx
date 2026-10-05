import { useState, useEffect } from 'react'
import { festivalYearTable, loadFestivalReference } from '../lib/festivalData'

// "Festival Dates" download on the Version Setting tab (user, 2026-10-05: "download the festival list with their bulk
// year dates, dates will be ranging from year to year as per the selection. No clusters nothing just festivals").
// One row per festival (calendar order), one column per year (DD-Mon-YYYY): the Google reference first, then the
// built-in table, blank when neither has that year - never estimated. The range defaults to the Calendar Years above.
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const cell = (v) => `"${String(v == null ? '' : v).replace(/"/g, '""')}"`
const fmt = (iso) => { if (!iso) return ''; const [y, m, d] = iso.split('-'); return `${d}-${MON[+m - 1]}-${y}` }

export default function FestivalDatesCard({ refYear, futYear }) {
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState(null)
  useEffect(() => { if (!from && refYear) setFrom(String(refYear)) }, [refYear])  // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (!to && futYear) setTo(String(futYear)) }, [futYear])        // eslint-disable-line react-hooks/exhaustive-deps

  async function download() {
    const a = Number(from), b = Number(to)
    if (!a || !b || a > b) { setStatus({ ok: false, msg: 'Pick a From year that is not after the To year.' }); return }
    if (b - a > 20) { setStatus({ ok: false, msg: 'Pick at most 21 years.' }); return }
    setBusy(true)
    try {
      await loadFestivalReference()
      const { years, rows } = festivalYearTable(a, b)
      const out = [['Festival', ...years].map(cell).join(',')]
      rows.forEach(r => out.push([r.name, ...r.dates.map(fmt)].map(cell).join(',')))
      const url = URL.createObjectURL(new Blob([out.join('\n')], { type: 'text/csv' }))
      const link = document.createElement('a')
      link.href = url
      link.download = `festival_dates_${a}-${b}.csv`
      link.click()
      URL.revokeObjectURL(url)
      setStatus({ ok: true, msg: `Downloaded ${rows.length} festivals x ${years.length} year${years.length === 1 ? '' : 's'} (${a}-${b}).` })
    } catch (e) {
      setStatus({ ok: false, msg: e.message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card">
      <div className="card-label">Festival Dates</div>
      <div className="field-row">
        <div className="field">
          <label>From Year</label>
          <input type="number" className="year-input" value={from} onChange={e => setFrom(e.target.value)} />
        </div>
        <div style={{ fontSize: '18px', color: 'var(--muted)', alignSelf: 'flex-end', paddingBottom: '4px' }}>-&gt;</div>
        <div className="field">
          <label>To Year</label>
          <input type="number" className="year-input" value={to} onChange={e => setTo(e.target.value)} />
        </div>
      </div>
      <div style={{ marginTop: '12px' }}>
        <button className="btn" onClick={download} disabled={busy}>
          {busy ? 'Preparing...' : 'Download Festival Dates (CSV)'}
        </button>
        <div style={{ fontSize: '11px', color: 'var(--muted)', marginTop: '6px' }}>
          Every festival with its date in each year of the range - no clusters. Dates come from the Google festival
          reference, then the built-in festival table; a year neither has is left blank.
        </div>
        {status && (
          <div style={{ fontSize: '12px', marginTop: '6px', color: status.ok ? 'var(--green)' : 'var(--red)' }}>{status.msg}</div>
        )}
      </div>
    </div>
  )
}
