import { useState } from 'react'
import StoreMappingPanel from './StoreMappingPanel'
import DateShiftPreviewPanel from './DateShiftPreviewPanel'

export default function StoreClusterMappingTab({ isPlanner }) {
  const [sub, setSub] = useState('map')
  return (
    <div className="module-panel">
      <div className="cal-sub-nav">
        <button className={sub === 'map' ? 'active' : ''} onClick={() => setSub('map')}>Store Mapping</button>
        <button className={sub === 'shift' ? 'active' : ''} onClick={() => setSub('shift')}>Date Shift Preview</button>
      </div>
      {sub === 'map' ? <StoreMappingPanel isPlanner={isPlanner} /> : <DateShiftPreviewPanel />}
    </div>
  )
}
