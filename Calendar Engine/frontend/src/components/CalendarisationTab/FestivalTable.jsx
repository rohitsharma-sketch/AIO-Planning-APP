import { useState } from 'react'

export default function FestivalTable({ festivals, onChange, isPlanner }) {
  const [dragIdx, setDragIdx] = useState(null)
  const [dragOverIdx, setDragOverIdx] = useState(null)

  function reorder(from, to) {
    const next = [...festivals]
    const [moved] = next.splice(from, 1)
    next.splice(to, 0, moved)
    onChange(next)
  }

  function updateField(idx, field, value) {
    const next = festivals.map((f, i) => i === idx ? { ...f, [field]: value } : f)
    onChange(next)
  }

  function removeRow(idx) {
    onChange(festivals.filter((_, i) => i !== idx))
  }

  return (
    <table id="festTable">
      <thead>
        <tr>
          <th></th><th>#</th><th>Festival Name</th><th>Reference Date</th><th>Future Date</th>
          <th>Pre(days)</th><th>Core(days)</th><th>Post(days)</th><th></th>
        </tr>
      </thead>
      <tbody id="festTbody">
        {festivals.map((f, idx) => (
          <tr key={f.id}
            className={dragOverIdx === idx ? 'fest-row-drag-over' : undefined}
            onDragOver={(e) => { if (dragIdx !== null) { e.preventDefault(); setDragOverIdx(idx) } }}
            onDrop={(e) => { e.preventDefault(); setDragOverIdx(null); if (dragIdx !== null && dragIdx !== idx) reorder(dragIdx, idx); setDragIdx(null) }}
          >
            <td className="drag-handle" draggable={isPlanner}
              onDragStart={() => setDragIdx(idx)}
              onDragEnd={() => { setDragIdx(null); setDragOverIdx(null) }}
              title="Drag to reorder">::</td>
            <td>{idx + 1}</td>
            <td><input value={f.name} disabled={!isPlanner} onChange={e => updateField(idx, 'name', e.target.value)} /></td>
            <td><input type="date" value={f.refDate} disabled={!isPlanner} onChange={e => updateField(idx, 'refDate', e.target.value)} /></td>
            <td><input type="date" value={f.futDate} disabled={!isPlanner} onChange={e => updateField(idx, 'futDate', e.target.value)} /></td>
            <td><input type="number" value={f.pre} disabled={!isPlanner} onChange={e => updateField(idx, 'pre', +e.target.value)} /></td>
            <td><input type="number" value={f.core} disabled={!isPlanner} onChange={e => updateField(idx, 'core', +e.target.value)} /></td>
            <td><input type="number" value={f.post} disabled={!isPlanner} onChange={e => updateField(idx, 'post', +e.target.value)} /></td>
            <td>{isPlanner && <button onClick={() => removeRow(idx)} title="Remove">×</button>}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
