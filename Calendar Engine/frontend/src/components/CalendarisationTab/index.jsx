import { useState, useEffect } from 'react'
import { getClusterProfiles, putClusterProfiles } from '../../lib/api'
import ClusterTabs from './ClusterTabs'
import FestivalTable from './FestivalTable'
import BulkAdjustPanels from './BulkAdjustPanels'
import { DEFAULT_FESTIVALS } from '../../lib/festivalData'

let _nextFestivalId = 1000

export default function CalendarisationTab({ isPlanner }) {
  const [profiles, setProfiles] = useState([])
  const [activeIdx, setActiveIdx] = useState(0)
  const [status, setStatus] = useState(null)

  useEffect(() => {
    getClusterProfiles().then(({ profiles }) => {
      setProfiles(profiles.length ? profiles : [{ name: 'Cluster 1', region: 'all', nextId: 20, festivals: DEFAULT_FESTIVALS.map(f => ({ ...f })) }])
    }).catch(e => setStatus({ ok: false, msg: e.message }))
  }, [])

  async function persist(nextProfiles) {
    setProfiles(nextProfiles)
    if (!isPlanner) return
    try {
      await putClusterProfiles({
        profiles: nextProfiles.map(cp => ({ name: cp.name, region: cp.region, nextId: cp.nextId, festivals: cp.festivals })),
      })
      setStatus({ ok: true, msg: 'Saved' })
    } catch (e) {
      setStatus({ ok: false, msg: e.message })
    }
  }

  function handleReorder(from, to) {
    const next = [...profiles]
    const [moved] = next.splice(from, 1)
    next.splice(to, 0, moved)
    let nextActive = activeIdx
    if (activeIdx === from) nextActive = to
    else if (from < activeIdx && to >= activeIdx) nextActive--
    else if (from > activeIdx && to <= activeIdx) nextActive++
    setActiveIdx(nextActive)
    persist(next)
  }

  function handleAdd() {
    const next = [...profiles, { name: `Cluster ${profiles.length + 1}`, region: 'all', nextId: 20, festivals: DEFAULT_FESTIVALS.map(f => ({ ...f })) }]
    persist(next)
  }

  function handleFestivalsChange(nextFestivals) {
    const next = profiles.map((cp, i) => i === activeIdx ? { ...cp, festivals: nextFestivals } : cp)
    persist(next)
  }

  if (!profiles.length) return <div className="module-panel">Loading…</div>

  return (
    <div className="module-panel" style={{ display: 'flex', gap: '16px' }}>
      <main style={{ flex: 1 }}>
        <div className="card">
          <ClusterTabs profiles={profiles} activeIdx={activeIdx} onSwitch={setActiveIdx}
            onReorder={handleReorder} onAdd={handleAdd} isPlanner={isPlanner} />
          <BulkAdjustPanels festivals={profiles[activeIdx].festivals} onChange={handleFestivalsChange} isPlanner={isPlanner} />
          <FestivalTable festivals={profiles[activeIdx].festivals} onChange={handleFestivalsChange} isPlanner={isPlanner} />
        </div>
        {status && <p style={{ color: status.ok ? 'var(--green)' : 'var(--red)' }}>{status.msg}</p>}
      </main>
    </div>
  )
}

// NOTE (Task 6 known simplifications, to be addressed by later tasks if needed):
// - Festival-name autocomplete (old calendar_engine.html lines 1222-1301, searchFestDB/FESTIVAL_DATES-driven
//   suggestions dropdown) is not ported. Typing a full festival name still works without suggestions.
// - autoFillDate (old calendar_engine.html lines 2036-2054): when a festival's Reference Date is edited and its
//   Future Date is still empty (or vice versa), the old app auto-filled the other date by re-using the day/month
//   against a separately-selected ref/fut year (inputs #refYear/#futYear, part of the bulk-adjust panel added in
//   Task 7). Since those year selectors don't exist yet in this partial file, that auto-fill is deferred to
//   Task 7/8 rather than approximated here.
