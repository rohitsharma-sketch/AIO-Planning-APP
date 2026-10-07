import { useState, useEffect } from 'react'
import { Menu } from '../ui'

// The old app's cluster Region dropdown, ported verbatim (all 11 options, same
// values and labels) from calendar_engine.html lines 775-787. The value is
// persisted to cluster_profiles.region through the normal putClusterProfiles
// path - the same column the seeded data already uses (north/east/bengal).
//
// NOTE: the old app's setClusterRegion() also called autoApplyRegionalFestivals()
// (calendar_engine.html lines 2156-2195), which appended every region-tagged
// festival from FESTIVAL_DB that the cluster didn't already have. That is
// deliberately NOT ported here - it silently mutates a real cluster's festival
// list (and therefore the generated calendar) as a side effect of picking a
// region, which is a much bigger behaviour change than restoring the control
// itself. The dropdown here only sets cp.region.
const REGIONS = [
  ['all', 'All India'],
  ['north', 'North India'],
  ['south', 'South India'],
  ['east', 'East India'],
  ['west', 'West India'],
  ['punjab', 'Punjab / Haryana'],
  ['maharashtra', 'Maharashtra'],
  ['kerala', 'Kerala'],
  ['tamil', 'Tamil Nadu'],
  ['bengal', 'Bengal / Assam'],
  ['gujarat', 'Gujarat / Rajasthan'],
]

export default function ClusterTabs({ profiles, activeIdx, onSwitch, onReorder, onAdd, onRename, onRegionChange, onCopyFrom, isPlanner }) {
  const [dragIdx, setDragIdx] = useState(null)
  const [dragOverIdx, setDragOverIdx] = useState(null)

  const active = profiles[activeIdx]

  // The rename box is a local draft committed on blur / Enter, NOT on every
  // keystroke. The old app could afford oninput="renameCluster(...)" because
  // saveState() wrote to localStorage; here every commit is a PUT
  // /cluster-profiles that deletes and re-inserts every cluster and every
  // festival row server-side, so per-keystroke writes would be both slow and a
  // pointless amount of churn on real data.
  const [nameDraft, setNameDraft] = useState(active?.name ?? '')
  useEffect(() => { setNameDraft(profiles[activeIdx]?.name ?? '') }, [activeIdx, profiles])

  function handleDrop(e, idx) {
    e.preventDefault()
    setDragOverIdx(null)
    if (dragIdx === null || dragIdx === idx) { setDragIdx(null); return }
    onReorder(dragIdx, idx)
    setDragIdx(null)
  }

  // Mirrors renameCluster() (calendar_engine.html lines 2197-2206): trim, and
  // fall back to "Cluster N" rather than allowing an empty name.
  //
  // The duplicate-name check has no old-app equivalent and is required here:
  // calendar.cluster_profiles has a UNIQUE constraint on `name`
  // (uq_cluster_profiles_name), so committing a duplicate would 500 and leave
  // the on-screen state diverged from the DB. Cluster name is also the join key
  // used by store_calendar_clusters and the saved calendars' day maps, so a
  // duplicate would be ambiguous there too.
  function commitName() {
    const trimmed = nameDraft.trim() || `Cluster ${activeIdx + 1}`
    if (trimmed === active?.name) { setNameDraft(trimmed); return }
    if (profiles.some((cp, i) => i !== activeIdx && cp.name === trimmed)) {
      window.alert(`Another cluster is already named "${trimmed}". Cluster names must be unique.`)
      setNameDraft(active?.name ?? '')
      return
    }
    setNameDraft(trimmed)
    onRename(trimmed)
  }

  return (
    <>
      <div id="clusterTabsRow" className="cluster-tabs-row">
        {profiles.map((cp, i) => (
          <button
            key={i}
            type="button"
            className={`cluster-tab${i === activeIdx ? ' active' : ''}${dragOverIdx === i ? ' cluster-drag-over' : ''}`}
            draggable={isPlanner}
            style={dragIdx === i ? { opacity: 0.4 } : undefined}
            onClick={() => onSwitch(i)}
            onDragStart={() => setDragIdx(i)}
            onDragOver={(e) => { if (dragIdx !== null && dragIdx !== i) { e.preventDefault(); setDragOverIdx(i) } }}
            onDrop={(e) => handleDrop(e, i)}
            onDragEnd={() => { setDragIdx(null); setDragOverIdx(null) }}
          >
            {cp.name}
          </button>
        ))}
        {isPlanner && (
          <button type="button" className="cluster-add-btn" onClick={onAdd} title="Add new cluster">+</button>
        )}
        {/* Rename / Region / Copy-from - ported from calendar_engine.html
            lines 770-795, collapsed into one menu (2026-10-07 declutter).
            Planner-only: these all write through persist(). */}
        {isPlanner && (
          <Menu label="Cluster settings" keepOpen title={`Rename, region and copy-from for "${active?.name ?? ''}"`}>
            <div className="ce-menu-section">
              <label htmlFor="clusterNameInput">Rename:</label>
              <input
                id="clusterNameInput"
                type="text"
                placeholder="Cluster name"
                title="Rename the active cluster (saved when you leave the box or press Enter)"
                value={nameDraft}
                onChange={e => setNameDraft(e.target.value)}
                onBlur={commitName}
                onKeyDown={e => { if (e.key === 'Enter') e.currentTarget.blur(); if (e.key === 'Escape') setNameDraft(active?.name ?? '') }}
              />
            </div>

            <div className="ce-menu-section">
              <label htmlFor="clusterRegionSelect">Region:</label>
              <select
                id="clusterRegionSelect"
                value={active?.region || 'all'}
                onChange={e => onRegionChange(e.target.value)}
              >
                {REGIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </div>

            {profiles.length > 1 && (
              <div className="ce-menu-section">
                <label htmlFor="copyFromSelect">Copy from:</label>
                {/* Always rendered with value="" - picking an option fires the copy
                    and the select snaps straight back to the placeholder, exactly
                    as renderCopyFromDropdown()/copyFromCluster() did by assigning
                    sel.value = '' (calendar_engine.html lines 2098-2121). */}
                <select
                  id="copyFromSelect"
                  value=""
                  title="Replace this cluster's festival list with another cluster's"
                  onChange={e => { if (e.target.value !== '') onCopyFrom(Number(e.target.value)) }}
                >
                  <option value="">- copy festivals from... -</option>
                  {profiles.map((cp, i) => i === activeIdx ? null : (
                    <option key={i} value={i}>{cp.name}</option>
                  ))}
                </select>
              </div>
            )}
          </Menu>
        )}
      </div>
    </>
  )
}
