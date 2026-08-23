import './ExcelPalettePicker.css'

const GROUPS = [
  {
    label: 'Blues',
    options: [
      { id: 'classic',  label: 'Classic Navy',  header: '#1F3864', mid: '#2F5597', light: '#EEF3FB', total: '#D8E4F4' },
      { id: 'royal',    label: 'Royal Blue',    header: '#1A56DB', mid: '#2970FF', light: '#EBF5FF', total: '#BFDBFE' },
      { id: 'steel',    label: 'Steel',         header: '#2E4057', mid: '#3B5068', light: '#EDF2F7', total: '#CBD5E1' },
      { id: 'teal',     label: 'Teal',          header: '#0F4C5C', mid: '#0D6E83', light: '#E6F7FA', total: '#99DDE8' },
    ],
  },
  {
    label: 'Greens',
    options: [
      { id: 'emerald',  label: 'Emerald',       header: '#1E293B', mid: '#10B981', light: '#ECFDF5', total: '#A7F3D0' },
      { id: 'forest',   label: 'Forest',        header: '#14532D', mid: '#166534', light: '#F0FDF4', total: '#BBF7D0' },
      { id: 'sage',     label: 'Sage',          header: '#3D6B4F', mid: '#4D8763', light: '#F0FAF4', total: '#BBF4CF' },
      { id: 'olive',    label: 'Olive',         header: '#3B3A1F', mid: '#5A5728', light: '#FAFAF0', total: '#EBEBBB' },
    ],
  },
  {
    label: 'Warm',
    options: [
      { id: 'amber',    label: 'Amber',         header: '#0F172A', mid: '#F59E0B', light: '#FFFBEB', total: '#FDE68A' },
      { id: 'burnt',    label: 'Burnt Orange',  header: '#7C2D12', mid: '#9A3412', light: '#FFF7ED', total: '#FED7AA' },
      { id: 'burgundy', label: 'Burgundy',      header: '#6B1A2A', mid: '#8B2038', light: '#FFF1F4', total: '#FECDD3' },
      { id: 'coral',    label: 'Violet',        header: '#3B1F6A', mid: '#5B2D9E', light: '#FAF5FF', total: '#E9D5FF' },
    ],
  },
  {
    label: 'Neutrals',
    options: [
      { id: 'charcoal', label: 'Charcoal',      header: '#1C1C1E', mid: '#3A3A3C', light: '#F5F5F7', total: '#D8D8DC' },
      { id: 'slate',    label: 'Slate',         header: '#334155', mid: '#475569', light: '#F8FAFC', total: '#E2E8F0' },
      { id: 'warm_gray',label: 'Warm Gray',     header: '#44403C', mid: '#57534E', light: '#FAFAF9', total: '#E7E5E4' },
    ],
  },
]

function MiniPreview({ header, mid, light, total, selected }) {
  return (
    <div className={`epp-preview ${selected ? 'epp-preview--selected' : ''}`}>
      <div className="epp-row" style={{ background: header }} />
      <div className="epp-row" style={{ background: header, opacity: 0.85 }} />
      <div className="epp-row" style={{ background: light }} />
      <div className="epp-row" style={{ background: '#fff' }} />
      <div className="epp-row" style={{ background: light }} />
      <div className="epp-row epp-row--total" style={{ background: total, borderTop: `2px solid ${mid}` }} />
    </div>
  )
}

export default function ExcelPalettePicker({ value, onChange }) {
  const selected = GROUPS.flatMap(g => g.options).find(o => o.id === value) || GROUPS[0].options[0]

  return (
    <div className="epp-wrap">
      <div className="epp-heading">
        <span className="epp-label">Output sheet colour theme</span>
        <span className="epp-current">
          <span className="epp-dot" style={{ background: selected.header }} />
          <span className="epp-dot" style={{ background: selected.mid }} />
          <span className="epp-dot" style={{ background: selected.light, border: '1px solid #ccc' }} />
          <span style={{ fontSize: 12, color: 'var(--muted)' }}>{selected.label}</span>
        </span>
      </div>

      {GROUPS.map(group => (
        <div key={group.label} className="epp-group">
          <div className="epp-group-label">{group.label}</div>
          <div className="epp-row-cards">
            {group.options.map(opt => (
              <button
                key={opt.id}
                className={`epp-card ${value === opt.id ? 'selected' : ''}`}
                onClick={() => onChange(opt.id)}
                title={opt.label}
              >
                <MiniPreview {...opt} selected={value === opt.id} />
                <div className="epp-card-label">{opt.label}</div>
                {value === opt.id && <div className="epp-card-check">✓</div>}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
