import { useState } from 'react'

export default function ClusterTabs({ profiles, activeIdx, onSwitch, onReorder, onAdd, isPlanner }) {
  const [dragIdx, setDragIdx] = useState(null)
  const [dragOverIdx, setDragOverIdx] = useState(null)

  function handleDrop(e, idx) {
    e.preventDefault()
    setDragOverIdx(null)
    if (dragIdx === null || dragIdx === idx) { setDragIdx(null); return }
    onReorder(dragIdx, idx)
    setDragIdx(null)
  }

  return (
    <div id="clusterTabsRow" style={{ display: 'flex', gap: '4px' }}>
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
    </div>
  )
}
