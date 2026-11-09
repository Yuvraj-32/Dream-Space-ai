import { useMemo, useState } from 'react'
import { ROLE_OPTIONS, UNIT_OPTIONS, cadUrl } from './cadApi'

const KIND_LABEL = {
  floor_plan: 'Floor plan',
  plan_without_walls: 'Rooms, no walls',
  possible_plan: 'Possible plan',
  other_drawing: 'Other drawing',
}
const KIND_CHIP = {
  floor_plan: 'chip-success',
  plan_without_walls: 'chip-warning',
  possible_plan: 'chip-neutral',
  other_drawing: 'chip-neutral',
}

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
      <div className="panel-card" style={{ margin: 'auto', maxWidth: 520 }}>
        <div className="panel-card-title" style={{ marginBottom: 8 }}>No floor plans found in this file</div>
        {inspect.warnings.map((w) => <div key={w} className="inline-note">{w}</div>)}
        <button className="btn" style={{ marginTop: 14 }} onClick={onCancel}>Back</button>
      </div>
    )
  }

  return (
    <div className="cad-review">
      <div>
        <div className="cad-review-title">Review the drawing</div>
        <div className="cad-review-sub">
          {inspect.source.format.toUpperCase()}{inspect.source.version ? ` ${inspect.source.version}` : ''} ·
          {' '}{inspect.clusters.length} drawing{inspect.clusters.length === 1 ? '' : 's'} found ·
          {' '}{inspect.layers.length} layers
        </div>
      </div>

      {inspect.warnings.length > 0 && (
        <div className="panel-card warning">
          {inspect.warnings.map((w) => <div key={w} style={{ lineHeight: 1.5 }}>{w}</div>)}
        </div>
      )}

      <div className="panel-card">
        <div className="panel-card-title"><span className="panel-card-num">1</span> Choose the floor plan</div>
        <div className="cad-grid">
          {inspect.clusters.map((c) => (
            <button
              key={c.id}
              onClick={() => setClusterId(c.id)}
              aria-pressed={c.id === clusterId}
              className={`cad-tile ${c.id === clusterId ? 'selected' : ''}`}
            >
              <img src={cadUrl(c.thumbnail_url)} alt={`Drawing ${c.id}`} />
              <div className="cad-tile-meta">
                <span className={`chip ${KIND_CHIP[c.kind_guess]}`}>
                  {KIND_LABEL[c.kind_guess]}{c.suggested ? ' · suggested' : ''}
                </span>
                <span className="cad-tile-size">{c.size_m[0]} × {c.size_m[1]} m</span>
              </div>
              {c.room_labels.length > 0 && (
                <div className="cad-tile-labels">{c.room_labels.slice(0, 4).join(', ')}</div>
              )}
            </button>
          ))}
        </div>
      </div>

      <div className="panel-card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div className="panel-card-title"><span className="panel-card-num">2</span> Check the layers</div>
          {hiddenCount > 0 && (
            <label className="snap-toggle">
              <input type="checkbox" checked={showIgnored} onChange={(e) => setShowIgnored(e.target.checked)} /> Show {hiddenCount} ignored
            </label>
          )}
        </div>
        <div className="layer-list">
          {layers.map((l) => (
            <div key={l.name} title={l.reason} className="layer-row">
              <span className="layer-swatch" style={{ background: l.color }} />
              <span className="layer-name">{l.name}</span>
              <span className="layer-count">{l.entities}</span>
              <select
                className="field-select"
                style={{ flex: '0 0 140px' }}
                value={roles[l.name]}
                onChange={(e) => setRoles((r) => ({ ...r, [l.name]: e.target.value }))}
                aria-label={`Role of layer ${l.name}`}
              >
                {ROLE_OPTIONS.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
              </select>
            </div>
          ))}
        </div>
        {walls === 0 && (
          <div className="inline-note warn" style={{ marginTop: 8 }}>Mark at least one layer as Walls.</div>
        )}
      </div>

      <div className="panel-card" style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <div className="panel-card-title"><span className="panel-card-num">3</span> Confirm the units</div>
        <select className="field-select" style={{ flex: '0 0 auto' }} value={units} onChange={(e) => setUnits(e.target.value)} aria-label="Drawing units">
          {UNIT_OPTIONS.map((u) => <option key={u.id} value={u.id}>{u.label}</option>)}
        </select>
        {size && <span className="inline-note">The plan is about <b>{size[0]} × {size[1]} m</b></span>}
        {inspect.units.confidence !== 'header' && (
          <span className="inline-note warn">
            {inspect.units.confidence === 'corrected' ? `The file says ${inspect.units.header}, but the geometry suggests ${inspect.units.name}` : 'Guessed from the geometry'}
          </span>
        )}
      </div>

      {error && <div className="panel-card error">{error}</div>}

      <div className="cad-actions">
        <button
          className="btn btn-primary"
          disabled={generating || walls === 0 || !cluster}
          onClick={() => onGenerate({ clusterId, layerRoles: changedRoles, units: units !== inspect.units.name ? units : undefined })}
        >
          {generating ? <><span className="spinner" style={{ borderTopColor: '#fff' }} /> Building walls…</> : 'Build walls →'}
        </button>
        <button className="btn" disabled={generating} onClick={onCancel}>Cancel</button>
      </div>
    </div>
  )
}
