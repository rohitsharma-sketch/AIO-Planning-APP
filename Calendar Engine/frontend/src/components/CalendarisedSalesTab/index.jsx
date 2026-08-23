import { useState } from 'react'
import LinkStatusPanel from './LinkStatusPanel'

export default function CalendarisedSalesTab({ isPlanner }) {
  const [selections, setSelections] = useState({})

  function handleSelectionChange(sourceType, payload) {
    setSelections(prev => ({ ...prev, [sourceType]: payload }))
  }

  return (
    <div className="module-panel">
      <LinkStatusPanel sourceType="mw" isPlanner={isPlanner} onSelectionChange={handleSelectionChange} />
      <LinkStatusPanel sourceType="dw" isPlanner={isPlanner} onSelectionChange={handleSelectionChange} />
    </div>
  )
}
