import { useState, useEffect } from 'react'
import { listCalendarLibrary, getCalendar, saveCalendar, deleteCalendar } from '../../lib/api'

export default function CalendarLibrary({ onLoad, isPlanner, buildSavePayload }) {
  const [items, setItems] = useState([])
  const [status, setStatus] = useState(null)
  const [busy, setBusy] = useState(false)

  function refresh() {
    listCalendarLibrary().then(setItems).catch(e => setStatus({ ok: false, msg: e.message }))
  }

  useEffect(refresh, [])

  async function handleSave() {
    if (!isPlanner) return
    setBusy(true)
    try {
      await saveCalendar(buildSavePayload())
      setStatus({ ok: true, msg: 'Calendar saved' })
      refresh()
    } catch (e) {
      setStatus({ ok: false, msg: e.message })
    } finally {
      setBusy(false)
    }
  }

  async function handleLoad(id) {
    try {
      const full = await getCalendar(id)
      onLoad(full)
    } catch (e) {
      setStatus({ ok: false, msg: e.message })
    }
  }

  async function handleDelete(id) {
    if (!isPlanner) return
    try {
      await deleteCalendar(id)
      refresh()
    } catch (e) {
      setStatus({ ok: false, msg: e.message })
    }
  }

  return (
    <div className="card" id="calLibrary">
      <h3>Calendar Library</h3>
      {isPlanner && <button className="btn" onClick={handleSave} disabled={busy}>Lock &amp; Save Calendar</button>}
      <ul>
        {items.length === 0 && <li style={{ color: 'var(--muted)' }}>No saved calendars yet.</li>}
        {items.map(c => (
          <li key={c.id}>
            {c.name} ({c.refYear}→{c.futYear})
            <button onClick={() => handleLoad(c.id)}>Load</button>
            {isPlanner && <button onClick={() => handleDelete(c.id)}>Delete</button>}
          </li>
        ))}
      </ul>
      {status && <p style={{ color: status.ok ? 'var(--green)' : 'var(--red)' }}>{status.msg}</p>}
    </div>
  )
}
