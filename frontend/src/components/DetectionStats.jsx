import Icon from './Icon'

/**
 * DetectionStats
 * Sidebar summary of what detection found: counts, scale source, and the
 * per-room size table.
 */
export default function DetectionStats({ detection, loading }) {
  if (loading) {
    return (
      <div className="sidebar-section">
        <div className="section-label">Detected layout</div>
        <div className="status-card loading">
          <div className="spinner" />
          <div className="status-body">
            <span className="status-title">Detecting…</span>
            <span className="status-detail">Finding walls, rooms, doors and windows</span>
          </div>
        </div>
      </div>
    )
  }

  if (!detection) return null

  const { walls = [], rooms = [], openings = [], stats = {}, measurements } = detection
  const doors   = openings.filter(o => o.type === 'door')
  const windows = openings.filter(o => o.type === 'window')
  const isCad = stats.engine === 'cad_vector'
  const fmtDim = (d) => (Array.isArray(d) ? `${d[0]} × ${d[1]} ft` : '—')
  const roomName = (r) => (r.type && r.type !== 'undefined' ? r.type.replace(/_/g, ' ') : 'Unnamed')

  const counts = [
    { icon: 'wall',   value: walls.length,   label: 'Walls' },
    { icon: 'room',   value: rooms.length,   label: 'Rooms' },
    { icon: 'door',   value: doors.length,   label: 'Doors' },
    { icon: 'window', value: windows.length, label: 'Windows' },
  ]

  return (
    <div className="sidebar-section">
      <div className="section-head">
        <div className="section-label">Detected layout</div>
        {isCad
          ? <span className="chip chip-success">From CAD geometry</span>
          : <span className="chip chip-neutral">From image</span>}
      </div>

      <div className="detection-grid">
        {counts.map(c => (
          <div className="det-card" key={c.label}>
            <span className="det-icon"><Icon name={c.icon} size={18} /></span>
            <span className="det-val">{c.value}</span>
            <span className="det-lbl">{c.label}</span>
          </div>
        ))}
      </div>

      {(measurements || isCad) && (
        <div className="meta-list">
          {measurements?.building_ft && (
            <div className="meta-row">
              <span>Building size</span>
              <span>
                {measurements.building_ft[0]} × {measurements.building_ft[1]} ft{' '}
                {stats.scale_source === 'door_width' && (
                  <span className="chip chip-warning" title="No dimension labels could be read, so the scale is estimated from standard door widths (±10%).">Estimated</span>
                )}
                {stats.scale_source === 'dimension_labels' && (
                  <span className="chip chip-success" title="Scale read from the plan's own printed dimension labels.">Measured</span>
                )}
              </span>
            </div>
          )}
          {isCad && stats.units?.name && (
            <div className="meta-row"><span>Drawing units</span><span>{stats.units.name}</span></div>
          )}
          {isCad && stats.label_dim_check?.rooms_checked > 0 && (
            <div className="meta-row">
              <span>Size check vs labels</span>
              <span>{stats.label_dim_check.median_error_pct}% off ({stats.label_dim_check.rooms_checked} rooms)</span>
            </div>
          )}
        </div>
      )}

      {measurements && rooms.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div className="section-label" style={{ marginBottom: 4 }}>Rooms</div>
          <table className="data-table">
            <thead>
              <tr><th>Room</th><th>Size</th><th className="num">Area</th></tr>
            </thead>
            <tbody>
              {rooms.map((r) => (
                <tr key={r.id} title={r.label_dim ? `Printed on plan: ${r.label_dim}` : undefined}>
                  <td>{roomName(r)}</td>
                  <td>{fmtDim(r.computed_dim_ft)}</td>
                  <td className="num">{r.area_sqft ? `${Math.round(r.area_sqft)} ft²` : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="status-card success" style={{ marginTop: 14 }}>
        <span className="status-icon"><Icon name="checkCircle" size={16} /></span>
        <div className="status-body">
          <span className="status-title">Detection complete</span>
          <span className="status-detail">Check the layout in Edit, then confirm it to build the 3D model.</span>
        </div>
      </div>
    </div>
  )
}
