import { useState, useEffect } from 'react'
import { getAppState, putAppState } from '../lib/api'

const MAPPING_TYPES = [
  'Exact Match', 'Nearest Weekday', 'Cross-Month Shift', 'Regional Override',
  'Fallback Assignment', 'Manual Override', 'Repaired (Excessive Shift)',
]

export default function VersionSettingTab({ isPlanner }) {
  const [refYear, setRefYear] = useState('')
  const [futYear, setFutYear] = useState('')
  const [maxShift, setMaxShift] = useState('45')
  const [moPri, setMoPri] = useState('prev')
  const [status, setStatus] = useState(null)

  useEffect(() => {
    getAppState().then(s => {
      if (s.refYear) setRefYear(s.refYear)
      if (s.futYear) setFutYear(s.futYear)
      if (s.maxShift) setMaxShift(s.maxShift)
      if (s.moPri) setMoPri(s.moPri)
    }).catch(() => {})
  }, [])

  async function save(partial) {
    if (!isPlanner) return
    try {
      await putAppState(partial)
      setStatus({ ok: true, msg: 'Saved' })
    } catch (e) {
      setStatus({ ok: false, msg: e.message })
    }
  }

  return (
    <div className="module-panel">
      <div className="card">
        <h3>Calendar Years</h3>
        <label>Reference Year</label>
        <input type="number" value={refYear} disabled={!isPlanner}
          onChange={e => setRefYear(e.target.value)}
          onBlur={() => save({ refYear })} />
        <label>Future Year</label>
        <input type="number" value={futYear} disabled={!isPlanner}
          onChange={e => setFutYear(e.target.value)}
          onBlur={() => save({ futYear })} />
        <label>Max Date Shift</label>
        <input type="number" value={maxShift} disabled={!isPlanner}
          onChange={e => setMaxShift(e.target.value)}
          onBlur={() => save({ maxShift })} />
      </div>

      <div className="card">
        <h3>Month Priority (non-festive days)</h3>
        <label>
          <input type="radio" name="moPri" value="prev" checked={moPri === 'prev'} disabled={!isPlanner}
            onChange={() => { setMoPri('prev'); save({ moPri: 'prev' }) }} />
          Same → Previous → Next
        </label>
        <label>
          <input type="radio" name="moPri" value="next" checked={moPri === 'next'} disabled={!isPlanner}
            onChange={() => { setMoPri('next'); save({ moPri: 'next' }) }} />
          Same → Next → Previous
        </label>
      </div>

      <div className="card">
        <h3>Festive Category Legend</h3>
        <ul>
          <li><span style={{ color: 'var(--navy3)' }}>■</span> Pre-Festive</li>
          <li><span style={{ color: 'var(--navy)' }}>■</span> Core Festive</li>
          <li><span style={{ color: 'var(--muted)' }}>■</span> Post-Festive</li>
          <li><span style={{ color: 'var(--border)' }}>■</span> Non-Festive</li>
        </ul>
      </div>

      <div className="card">
        <h3>Mapping Type Reference</h3>
        <ul>{MAPPING_TYPES.map(t => <li key={t}>{t}</li>)}</ul>
      </div>

      {status && <p style={{ color: status.ok ? 'var(--green)' : 'var(--red)' }}>{status.msg}</p>}
    </div>
  )
}
