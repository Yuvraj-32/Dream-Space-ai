import { useMemo, useState } from 'react'
import { ROLE_OPTIONS, UNIT_OPTIONS, cadUrl } from './cadApi'

const KIND_LABEL = {
  floor_plan: 'Floor plan',
  plan_without_walls: 'Rooms, no walls',
  possible_plan: 'Possible plan',
  other_drawing: 'Other drawing',
}
const KIND_COLOR = {
  floor_plan: '#3dd9c6',
  plan_without_walls: '#f5a623',
  possible_plan: '#6378ff',
  other_drawing: '#8890ab',
}

const box = {
  background: 'rgba(15, 18, 33, 0.96)',
  border: '1px solid rgba(255,255,255,0.08)',
  borderRadius: 10,
  padding: 16,
}
const label = { fontSize: 10, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#8890ab' }

export default function CadReviewPanel({ inspect, generating, error, onGenerate, onCancel }) {
  const suggested = inspect.clusters.find((c) => c.suggested)
  const [clusterId, setClusterId] = useState((suggested || inspect.clusters[0])?.id)
  const [roles, setRoles] = useState(() =>
    Object.fromEntries(inspect.layers.map((l) => [l.name, l.suggested_role])))
  const [units, setUnits] = useState(inspect.units.name)
  const [showIgnored, setShowIgnored] = useState(false)

  const cluster = inspect.clusters.find((c) => c.id === clusterId)
  const detectedMpu = inspect.units.metres_per_unit
  const mpu = UNIT_OPTIONS.find((u) => u.id === units)?.mpu ?? detectedMpu
  const size = cluster ? cluster.size_m.map((v) => (v * mpu / detectedMpu).toFixed(1)) : null
  const walls = useMemo(() => Object.values(roles).filter((r) => r === 'wall').length, [roles])
  const layers = inspect.layers.filter((l) => showIgnored || roles[l.name] !== 'ignore' || l.suggested_role !== 'ignore')
  const hiddenCount = inspect.layers.length - layers.length

  const changedRoles = Object.fromEntries(
    inspect.layers.filter((l) => roles[l.name] !== l.suggested_role).map((l) => [l.name, roles[l.name]]))

  if (!inspect.clusters.length) {
    return (
      <div style={{ ...box, margin: 'auto', maxWidth: 520 }}>
        <div style={{ fontWeight: 700, marginBottom: 8 }}>No drawings found</div>
        {inspect.warnings.map((w) => <div key={w} style={{ fontSize: 13, color: '#c7cce0' }}>{w}</div>)}
        <button className="view-btn" style={{ marginTop: 12 }} onClick={onCancel}>Back</button>
      </div>
    )
  }

  return (
    <div style={{ padding: 20, overflowY: 'auto', height: '100%', display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div>
        <div style={{ fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 700 }}>Review CAD drawing</div>
        <div style={{ fontSize: 12, color: '#8890ab', marginTop: 2 }}>
          {inspect.source.format.toUpperCase()}{inspect.source.version ? ` ${inspect.source.version}` : ''} ·
          {' '}{inspect.clusters.length} drawing{inspect.clusters.length === 1 ? '' : 's'} found ·
          {' '}{inspect.layers.length} layers
        </div>
      </div>

      {inspect.warnings.length > 0 && (
        <div style={{ ...box, borderColor: 'rgba(245,166,35,0.4)', background: 'rgba(245,166,35,0.07)' }}>
          {inspect.warnings.map((w) => (
            <div key={w} style={{ fontSize: 12, color: '#f0d9a8', lineHeight: 1.5 }}>⚠ {w}</div>
          ))}
        </div>
      )}

      <div style={box}>
        <div style={label}>1 · Pick the floor plan</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(190px, 1fr))', gap: 10, marginTop: 10 }}>
          {inspect.clusters.map((c) => (
            <button
              key={c.id}
              onClick={() => setClusterId(c.id)}
              aria-pressed={c.id === clusterId}
              style={{
                textAlign: 'left', cursor: 'pointer', padding: 8, borderRadius: 8, color: '#fff',
                background: c.id === clusterId ? 'rgba(99,120,255,0.18)' : 'rgba(255,255,255,0.03)',
                border: `1px solid ${c.id === clusterId ? '#6378ff' : 'rgba(255,255,255,0.08)'}`,
              }}
            >
              <img src={cadUrl(c.thumbnail_url)} alt={`Drawing ${c.id}`}
                   style={{ width: '100%', height: 110, objectFit: 'contain', background: '#141824', borderRadius: 4 }} />
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 6 }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: KIND_COLOR[c.kind_guess] }}>
                  {KIND_LABEL[c.kind_guess]}{c.suggested ? ' ★' : ''}
                </span>
                <span style={{ fontSize: 10, color: '#8890ab' }}>{c.size_m[0]} × {c.size_m[1]} m</span>
              </div>
              {c.room_labels.length > 0 && (
                <div style={{ fontSize: 10, color: '#8890ab', marginTop: 2, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {c.room_labels.slice(0, 4).join(', ')}
                </div>
              )}
            </button>
          ))}
        </div>
      </div>

      <div style={box}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={label}>2 · Confirm layers</div>
          {hiddenCount > 0 && (
            <label style={{ fontSize: 11, color: '#8890ab', cursor: 'pointer' }}>
              <input type="checkbox" checked={showIgnored} onChange={(e) => setShowIgnored(e.target.checked)} /> show {hiddenCount} ignored
            </label>
          )}
        </div>
        <div style={{ maxHeight: 260, overflowY: 'auto', marginTop: 8 }}>
          {layers.map((l) => (
            <div key={l.name} title={l.reason} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 0', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
              <span style={{ width: 10, height: 10, borderRadius: 2, background: l.color, flex: '0 0 auto', border: '1px solid rgba(255,255,255,0.3)' }} />
              <span style={{ flex: 1, fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{l.name}</span>
              <span style={{ fontSize: 10, color: '#8890ab', width: 56, textAlign: 'right' }}>{l.entities}</span>
              <select
                value={roles[l.name]}
                onChange={(e) => setRoles((r) => ({ ...r, [l.name]: e.target.value }))}
                aria-label={`Role of layer ${l.name}`}
                style={{ background: '#1c2235', color: '#fff', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 4, fontSize: 11, padding: '3px 4px' }}
              >
                {ROLE_OPTIONS.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
              </select>
            </div>
          ))}
        </div>
        {walls === 0 && (
          <div style={{ fontSize: 11, color: '#f5a623', marginTop: 8 }}>Mark at least one layer as Walls.</div>
        )}
      </div>

      <div style={{ ...box, display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <div style={label}>3 · Units</div>
        <select value={units} onChange={(e) => setUnits(e.target.value)} aria-label="Drawing units"
                style={{ background: '#1c2235', color: '#fff', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 4, fontSize: 12, padding: '4px 6px' }}>
          {UNIT_OPTIONS.map((u) => <option key={u.id} value={u.id}>{u.label}</option>)}
        </select>
        {size && <span style={{ fontSize: 12, color: '#c7cce0' }}>→ plan is about <b>{size[0]} × {size[1]} m</b></span>}
        {inspect.units.confidence !== 'header' && (
          <span style={{ fontSize: 11, color: '#f5a623' }}>
            {inspect.units.confidence === 'corrected' ? `file says ${inspect.units.header}, geometry says ${inspect.units.name}` : 'guessed from geometry'}
          </span>
        )}
      </div>

      {error && <div style={{ ...box, borderColor: 'rgba(255,90,90,0.5)', color: '#ffb4b4', fontSize: 13 }}>{error}</div>}

      <div style={{ display: 'flex', gap: 10 }}>
        <button
          className="view-btn active"
          disabled={generating || walls === 0 || !cluster}
          onClick={() => onGenerate({ clusterId, layerRoles: changedRoles, units: units !== inspect.units.name ? units : undefined })}
        >
          {generating ? 'Generating walls…' : 'Generate walls →'}
        </button>
        <button className="view-btn" disabled={generating} onClick={onCancel}>Cancel</button>
      </div>
    </div>
  )
}
