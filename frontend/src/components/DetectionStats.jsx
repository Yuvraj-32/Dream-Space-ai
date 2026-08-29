/**
 * DetectionStats
 * Shows the Phase 1 detection results summary in the sidebar:
 * wall count, room count, opening count, pipeline info.
 */
export default function DetectionStats({ detection, loading }) {
  if (loading) {
    return (
      <div className="sidebar-section">
        <div className="section-label">Detection Results</div>
        <div className="status-card loading">
          <div className="spinner" />
          <div className="status-body">
            <span className="status-title">Running CV pipeline…</span>
            <span className="status-detail">Hough lines · contours · gap detection</span>
          </div>
        </div>
      </div>
    )
  }

  if (!detection) return null

  const { walls = [], rooms = [], openings = [], stats = {}, image_size, measurements } = detection
  const doors   = openings.filter(o => o.type === 'door')
  const windows = openings.filter(o => o.type === 'window')
  const fmtDim = (d) => (Array.isArray(d) ? `${d[0]} × ${d[1]} ft` : '—')

  return (
    <div className="sidebar-section">
      <div className="section-label">Detection Results</div>

      {/* Summary grid */}
      <div className="detection-grid">
        <div className="det-card">
          <span className="det-icon">🧱</span>
          <span className="det-val">{walls.length}</span>
          <span className="det-lbl">Walls</span>
        </div>
        <div className="det-card">
          <span className="det-icon">🏠</span>
          <span className="det-val">{rooms.length}</span>
          <span className="det-lbl">Rooms</span>
        </div>
        <div className="det-card">
          <span className="det-icon">🚪</span>
          <span className="det-val">{doors.length}</span>
          <span className="det-lbl">Doors</span>
        </div>
        <div className="det-card">
          <span className="det-icon">🪟</span>
          <span className="det-val">{windows.length}</span>
          <span className="det-lbl">Windows</span>
        </div>
      </div>

      {/* Image info */}
      <div style={{ marginTop: 10, fontSize: 11, color: 'var(--text-muted)' }}>
        Image: {image_size?.width} × {image_size?.height}px
        {stats.raw_hough_segments !== undefined && (
          <> · {stats.raw_hough_segments} raw segments → {stats.merged_walls} merged</>
        )}
      </div>

      {/* Real-world measurements. Two sources, and the difference matters:
          "dimension_labels" was read off the plan; "door_width" is inferred
          from standard door sizes and is only approximate. */}
      {measurements && (
        <div style={{ marginTop: 12 }}>
          <div className="section-label">Dimensions</div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 6 }}>
            Building: <b>{measurements.building_ft?.[0]} × {measurements.building_ft?.[1]} ft</b>
            {stats.scale_source === 'door_width' && (
              <span
                title="No dimension labels could be read, so the scale is estimated from standard door widths (±10%)."
                style={{
                  marginLeft: 6, padding: '1px 6px', borderRadius: 4, fontSize: 10,
                  fontWeight: 700, letterSpacing: 0.3,
                  background: 'rgba(255,193,107,0.15)', color: '#ffc16b',
                }}
              >
                ~EST
              </span>
            )}
            {stats.scale_source === 'dimension_labels' && (
              <span
                title="Scale read from the plan's own printed dimension labels."
                style={{
                  marginLeft: 6, padding: '1px 6px', borderRadius: 4, fontSize: 10,
                  fontWeight: 700, letterSpacing: 0.3,
                  background: 'rgba(61,217,198,0.15)', color: '#3dd9c6',
                }}
              >
                MEASURED
              </span>
            )}
          </div>
          <table style={{ width: '100%', fontSize: 11, borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ textAlign: 'left', color: 'var(--text-muted)' }}>
                <th>Room</th><th>Labeled</th><th>Measured</th><th>Area</th>
              </tr>
            </thead>
            <tbody>
              {rooms.map((r) => (
                <tr key={r.id} style={{ borderTop: '1px solid var(--border, #333)' }}>
                  <td>{r.type ?? 'room'}</td>
                  <td>{r.label_dim ?? '—'}</td>
                  <td>{fmtDim(r.computed_dim_ft)}</td>
                  <td>{r.area_sqft ? `${r.area_sqft} ft²` : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pipeline badge */}
      <div className="status-card success" style={{ marginTop: 10 }}>
        <span className="status-icon">✅</span>
        <div className="status-body">
          <span className="status-title">Phase 1 complete</span>
          <span className="status-detail">Ready for 2D editor correction</span>
        </div>
      </div>
    </div>
  )
}
