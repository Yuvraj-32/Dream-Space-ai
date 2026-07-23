import { useEffect, useRef, useState, useCallback } from 'react'
import { Stage, Layer, Image as KonvaImage, Line, Circle, Rect, Group, Text as KonvaText, Label, Tag } from 'react-konva'
import useImage from 'use-image'

/* ─── constants ─────────────────────────────────────────────── */
const GRID_SIZE          = 20
const SNAP_RADIUS        = 14
const HANDLE_RADIUS      = 7
// Main walls — bold, fully opaque structural walls
const MAIN_WALL_STROKE   = 5
const MAIN_WALL_COLOR    = '#6378ff'
// Partition walls — slim, slightly muted interior dividers
const PART_WALL_STROKE   = 2
const PART_WALL_COLOR    = '#8fa0cc'
// Selected state
const SEL_WALL_STROKE    = 6
const WALL_STROKE        = 3   // fallback if wall_type unknown
const WALL_COLOR         = '#6378ff'
const SEL_COLOR          = '#3dd9c6'
const HANDLE_COLOR       = '#ffffff'
const DOOR_COLOR         = '#3dd9c6'
const WIN_COLOR          = '#ffc16b'

/* ─── helpers ────────────────────────────────────────────────── */
function snapToGrid(v) {
  return Math.round(v / GRID_SIZE) * GRID_SIZE
}

function dist(ax, ay, bx, by) {
  return Math.hypot(bx - ax, by - ay)
}

function snapToCorners(x, y, walls, skipWallId, skipEndpoint) {
  let closestPt = null
  let minDist = SNAP_RADIUS
  for (const w of walls) {
    if (w.id === skipWallId) continue
    const pts = [
      { x: w.x1, y: w.y1, which: 'start' },
      { x: w.x2, y: w.y2, which: 'end' },
    ]
    for (const pt of pts) {
      const d = dist(x, y, pt.x, pt.y)
      if (d < minDist) {
        minDist = d
        closestPt = { x: pt.x, y: pt.y, snapped: true }
      }
    }
  }
  return closestPt || { x, y, snapped: false }
}

function getWallMidpoint(wall) {
  return { x: (wall.x1 + wall.x2) / 2, y: (wall.y1 + wall.y2) / 2 }
}

/* ─── BackgroundImage ─────────────────────────────────────────── */
function BackgroundImage({ url, stageW, stageH }) {
  const [img] = useImage(url)
  if (!img) return null
  return (
    <KonvaImage
      image={img}
      x={0} y={0}
      width={stageW} height={stageH}
      opacity={0.55}
      listening={false}
    />
  )
}

/* ─── GridLayer ────────────────────────────────────────────────── */
function GridLayer({ stageW, stageH, visible }) {
  if (!visible) return null
  const lines = []
  for (let x = 0; x <= stageW; x += GRID_SIZE) {
    lines.push(
      <Line key={`gx-${x}`} points={[x, 0, x, stageH]}
        stroke="rgba(99,120,255,0.12)" strokeWidth={0.5} listening={false} />
    )
  }
  for (let y = 0; y <= stageH; y += GRID_SIZE) {
    lines.push(
      <Line key={`gy-${y}`} points={[0, y, stageW, y]}
        stroke="rgba(99,120,255,0.12)" strokeWidth={0.5} listening={false} />
    )
  }
  return <>{lines}</>
}

/* ─── Main Editor ────────────────────────────────────────────── */
export default function FloorPlanEditor({ imageUrl, detection, onConfirm }) {
  const containerRef  = useRef(null)
  const stageRef      = useRef(null)
  const [stageSize,   setStageSz]   = useState({ w: 800, h: 600 })
  const [walls,       setWalls]     = useState([])
  const [openings,    setOpenings]  = useState([])
  const [selectedId,  setSelectedId] = useState(null)
  const [tool,        setTool]      = useState('select')   // 'select' | 'wall'
  const [snapGrid,    setSnapGrid]  = useState(true)
  const [showDims,    setShowDims]  = useState(true)   // wall-length labels
  const [drawState,   setDrawState] = useState(null)       // {x1,y1} while drawing
  const [scaleRatio,  setScaleRatio] = useState({ x: 1, y: 1 })
  const [confirmed,   setConfirmed] = useState(false)
  const nextId = useRef(1000)

  /* ── resize observer ──────────────────────────────────────── */
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const obs = new ResizeObserver(() => {
      // Guard against firing after unmount
      if (!containerRef.current) return
      const { width, height } = containerRef.current.getBoundingClientRect()
      setStageSz({ w: width, h: height })
    })
    obs.observe(el)
    return () => obs.disconnect()
  }, [])

  const lastDetection = useRef(null)
  const prevScaleRatio = useRef({ x: 0, y: 0 })

  /* ── load detection into canvas coords ────────────────────── */
  useEffect(() => {
    if (!detection || !stageSize.w) return
    const { image_size, walls: dWalls, openings: dOpenings } = detection
    const rx = stageSize.w / image_size.width
    const ry = stageSize.h / image_size.height

    if (lastDetection.current !== detection) {
      // First time loading this detection: initialize from original detection data
      setWalls((dWalls || []).map(w => ({
        id:   w.id,
        x1:   Math.round(w.x1 * rx),
        y1:   Math.round(w.y1 * ry),
        x2:   Math.round(w.x2 * rx),
        y2:   Math.round(w.y2 * ry),
        wall_type: w.wall_type,
      })))

      setOpenings((dOpenings || []).map(o => ({
        id:       o.id,
        wallId:   o.wall_id,
        x:        Math.round(o.x * rx),
        y:        Math.round(o.y * ry),
        type:     o.type,
        width_px: o.width_px || (o.type === 'door' ? 90 : 120),
      })))
      
      lastDetection.current = detection
    } else {
      // Stage resized, scale the existing walls and openings instead of wiping edits
      const px = prevScaleRatio.current.x
      const py = prevScaleRatio.current.y
      if (px > 0 && py > 0 && (px !== rx || py !== ry)) {
        const factorX = rx / px
        const factorY = ry / py
        
        setWalls(ws => ws.map(w => ({
          ...w,
          x1: Math.round(w.x1 * factorX),
          y1: Math.round(w.y1 * factorY),
          x2: Math.round(w.x2 * factorX),
          y2: Math.round(w.y2 * factorY),
        })))
        
        setOpenings(ops => ops.map(o => ({
          ...o,
          x: Math.round(o.x * factorX),
          y: Math.round(o.y * factorY),
        })))
      }
    }

    prevScaleRatio.current = { x: rx, y: ry }
    setScaleRatio({ x: rx, y: ry })
  }, [detection, stageSize.w, stageSize.h])

  /* ── keyboard: Delete selected wall ───────────────────────── */
  useEffect(() => {
    function onKey(e) {
      if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA')) return
      if ((e.key === 'Delete' || e.key === 'Backspace') && selectedId) {
        setWalls(ws => ws.filter(w => w.id !== selectedId))
        setSelectedId(null)
      }
      if (e.key === 'Escape') { setTool('select'); setDrawState(null) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [selectedId])

  /* ── stage click (deselect / start drawing) ───────────────── */
  function onStageMouseDown(e) {
    if (confirmed) return
    const pos  = stageRef.current.getPointerPosition()
    let   { x, y } = pos

    if (snapGrid) { x = snapToGrid(x); y = snapToGrid(y) }
    const snapped = snapToCorners(x, y, walls, null, null)
    x = snapped.x; y = snapped.y

    if (tool === 'wall') {
      if (!drawState) {
        setDrawState({ x1: x, y1: y })
      } else {
        if (drawState.x1 === x && drawState.y1 === y) {
          // Reject zero-length wall; cancel drawing
          setDrawState(null)
          setTool('select')
          return
        }
        // Finish wall
        const id = `wall_new_${nextId.current++}`
        setWalls(ws => [...ws, { id, x1: drawState.x1, y1: drawState.y1, x2: x, y2: y, wall_type: 'partition' }])
        setDrawState(null)
        setTool('select')
        setSelectedId(id)
      }
    } else {
      // Deselect if clicking blank stage
      if (e.target === e.target.getStage()) setSelectedId(null)
    }
  }

  /* ── drag an endpoint ──────────────────────────────────────── */
  function onEndpointDrag(wallId, endpoint, e) {
    if (confirmed) return
    let { x, y } = e.target.position()
    if (snapGrid) { x = snapToGrid(x); y = snapToGrid(y) }
    const snapped = snapToCorners(x, y, walls, wallId, endpoint)
    x = snapped.x; y = snapped.y

    setWalls(ws => ws.map(w => {
      if (w.id !== wallId) return w
      return endpoint === 'start'
        ? { ...w, x1: x, y1: y }
        : { ...w, x2: x, y2: y }
    }))
  }

  /* ── delete selected ─────────────────────────────────────── */
  function deleteSelected() {
    if (selectedId) { setWalls(ws => ws.filter(w => w.id !== selectedId)); setSelectedId(null) }
  }

  /* ── confirm layout ──────────────────────────────────────── */
  function handleConfirm() {
    setConfirmed(true)
    setTool('select')
    setSelectedId(null)
    // Convert back to image space for Phase 3
    const rx = scaleRatio.x > 0 ? scaleRatio.x : 1
    const ry = scaleRatio.y > 0 ? scaleRatio.y : 1
    const imageSpaceWalls = walls.map(w => ({
      id: w.id,
      x1: Math.round(w.x1 / rx),
      y1: Math.round(w.y1 / ry),
      x2: Math.round(w.x2 / rx),
      y2: Math.round(w.y2 / ry),
      wall_type: w.wall_type,
    }))
    const imageSpaceOpenings = openings.map(o => ({
      ...o,
      x: Math.round(o.x / rx),
      y: Math.round(o.y / ry),
    }))
    onConfirm?.({ walls: imageSpaceWalls, openings: imageSpaceOpenings })
  }

  /* ── live preview line while drawing ─────────────────────── */
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 })
  function onStageMouseMove(e) {
    if (tool !== 'wall' || !drawState) return
    const pos = stageRef.current.getPointerPosition()
    let { x, y } = pos
    if (snapGrid) { x = snapToGrid(x); y = snapToGrid(y) }
    setMousePos({ x, y })
  }

  /* ── real-world scale for dimension labels ────────────────── */
  const rxR = scaleRatio.x || 1
  const ryR = scaleRatio.y || 1
  // ft-per-pixel in ORIGINAL image space (set when detection ran with ?measure).
  const scaleFtPerPx = detection?.stats?.scale_ft_per_px
                    ?? detection?.measurements?.scale_ft_per_px ?? null
  function wallLabel(w) {
    // Convert canvas coords back to image space (x/rx, y/ry) so the length is
    // correct even when the stage aspect differs, then to feet if calibrated.
    const imgLen = dist(w.x1 / rxR, w.y1 / ryR, w.x2 / rxR, w.y2 / ryR)
    if (scaleFtPerPx) return `${(imgLen * scaleFtPerPx).toFixed(1)} ft`
    return `${Math.round(dist(w.x1, w.y1, w.x2, w.y2))} px`
  }

  /* ── render ──────────────────────────────────────────────── */
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--bg-deep)' }}>

      {/* Toolbar */}
      <div className="editor-toolbar">
        <div className="toolbar-group">
          <button
            id="tool-select"
            className={`tool-btn ${tool === 'select' ? 'active' : ''}`}
            onClick={() => { setTool('select'); setDrawState(null) }}
            title="Select / Move (Esc)"
          >
            ↖ Select
          </button>
          <button
            id="tool-draw"
            className={`tool-btn ${tool === 'wall' ? 'active' : ''}`}
            onClick={() => { setTool('wall'); setSelectedId(null) }}
            disabled={confirmed}
            title="Draw Wall (click two points)"
          >
            📐 Draw Wall
          </button>
          <button
            id="tool-delete"
            className="tool-btn danger"
            onClick={deleteSelected}
            disabled={!selectedId || confirmed}
            title="Delete selected wall (Del)"
          >
            🗑 Delete
          </button>
        </div>

        <div className="toolbar-group">
          <label className="snap-toggle">
            <input type="checkbox" checked={snapGrid} onChange={e => setSnapGrid(e.target.checked)} />
            <span>Snap to Grid</span>
          </label>
          <label className="snap-toggle" title="Show wall length labels">
            <input type="checkbox" checked={showDims} onChange={e => setShowDims(e.target.checked)} />
            <span>Dimensions{scaleFtPerPx ? ' (ft)' : ''}</span>
          </label>
          <div className="wall-count-badge">
            🧱 {walls.length} walls
          </div>
        </div>

        <button
          id="btn-confirm-layout"
          className={`confirm-btn ${confirmed ? 'done' : ''}`}
          onClick={handleConfirm}
          disabled={confirmed || walls.length === 0}
        >
          {confirmed ? '✅ Layout Confirmed' : '✔ Confirm Layout →'}
        </button>
      </div>

      {/* Konva Stage */}
      <div ref={containerRef} style={{ flex: 1, overflow: 'hidden', cursor: tool === 'wall' ? 'crosshair' : 'default' }}>
        <Stage
          ref={stageRef}
          width={stageSize.w}
          height={stageSize.h}
          onMouseDown={onStageMouseDown}
          onMouseMove={onStageMouseMove}
        >
          <Layer>
            {/* Background floor plan image */}
            {imageUrl && <BackgroundImage url={imageUrl} stageW={stageSize.w} stageH={stageSize.h} />}

            {/* Grid */}
            <GridLayer stageW={stageSize.w} stageH={stageSize.h} visible={snapGrid} />

            {/* Openings */}
            {openings.map(op => (
              <Circle
                key={op.id}
                x={op.x} y={op.y}
                radius={14}
                fill={op.type === 'door' ? 'rgba(61,217,198,0.2)' : 'rgba(255,193,107,0.2)'}
                stroke={op.type === 'door' ? DOOR_COLOR : WIN_COLOR}
                strokeWidth={2}
                listening={false}
              />
            ))}

            {/* Walls */}
            {walls.map(wall => {
              const isSel    = wall.id === selectedId
              const isMain   = wall.wall_type === 'main_wall'
              const baseColor  = isSel ? SEL_COLOR
                               : isMain ? MAIN_WALL_COLOR
                               : PART_WALL_COLOR
              const baseWidth  = isSel ? SEL_WALL_STROKE
                               : isMain ? MAIN_WALL_STROKE
                               : PART_WALL_STROKE
              const shadowBlur = isSel ? 12 : isMain ? 5 : 2
              const opacity    = isMain ? 1.0 : 0.72

              return (
                <Group key={wall.id}>
                  {/* Hit area (wider, invisible) */}
                  <Line
                    points={[wall.x1, wall.y1, wall.x2, wall.y2]}
                    stroke="transparent"
                    strokeWidth={18}
                    lineCap="round"
                    onClick={() => !confirmed && setSelectedId(wall.id)}
                    onTap={() => !confirmed && setSelectedId(wall.id)}
                  />
                  {/* Visible wall line */}
                  <Line
                    points={[wall.x1, wall.y1, wall.x2, wall.y2]}
                    stroke={baseColor}
                    strokeWidth={baseWidth}
                    opacity={opacity}
                    lineCap="round"
                    shadowColor={baseColor}
                    shadowBlur={shadowBlur}
                    shadowOpacity={isSel ? 0.8 : 0.45}
                    listening={false}
                  />
                  {/* Length label — shown for all walls when dimensions are
                      on, and always for the selected wall. Real feet when the
                      plan was measured, else pixels. */}
                  {(showDims || isSel) && (() => {
                    const mid = getWallMidpoint(wall)
                    return (
                      <Label x={mid.x} y={mid.y} listening={false}>
                        <Tag
                          fill={isSel ? SEL_COLOR : 'rgba(18,22,38,0.82)'}
                          cornerRadius={3}
                          pointerDirection="down"
                          pointerWidth={0}
                          pointerHeight={0}
                        />
                        <KonvaText
                          text={wallLabel(wall)}
                          fontSize={11}
                          fontStyle={isMain ? 'bold' : 'normal'}
                          fill={isSel ? '#0c1020' : '#e6eaff'}
                          fontFamily="Inter, sans-serif"
                          padding={3}
                        />
                      </Label>
                    )
                  })()}
                  {/* Drag handles (only when selected or hovered) */}
                  {isSel && !confirmed && (
                    <>
                      <Circle
                        x={wall.x1} y={wall.y1}
                        radius={HANDLE_RADIUS}
                        fill={HANDLE_COLOR}
                        stroke={SEL_COLOR}
                        strokeWidth={2}
                        draggable
                        onDragMove={e => onEndpointDrag(wall.id, 'start', e)}
                        dragBoundFunc={pos => pos}
                      />
                      <Circle
                        x={wall.x2} y={wall.y2}
                        radius={HANDLE_RADIUS}
                        fill={HANDLE_COLOR}
                        stroke={SEL_COLOR}
                        strokeWidth={2}
                        draggable
                        onDragMove={e => onEndpointDrag(wall.id, 'end', e)}
                        dragBoundFunc={pos => pos}
                      />
                    </>
                  )}
                  {/* Unselected endpoint dots */}
                  {!isSel && (
                    <>
                      <Circle x={wall.x1} y={wall.y1} radius={3} fill={WALL_COLOR} opacity={0.6} listening={false} />
                      <Circle x={wall.x2} y={wall.y2} radius={3} fill={WALL_COLOR} opacity={0.6} listening={false} />
                    </>
                  )}
                </Group>
              )
            })}

            {/* Live preview line while drawing */}
            {tool === 'wall' && drawState && (
              <Line
                points={[drawState.x1, drawState.y1, mousePos.x, mousePos.y]}
                stroke={SEL_COLOR}
                strokeWidth={2}
                dash={[6, 4]}
                lineCap="round"
                opacity={0.8}
                listening={false}
              />
            )}
          </Layer>
        </Stage>
      </div>

      {/* Hint bar */}
      <div className="editor-hint">
        {confirmed
          ? '✅ Layout locked — ready for Phase 3: 3D Generation'
          : tool === 'wall' && !drawState
          ? '📐 Click to place the first wall endpoint'
          : tool === 'wall' && drawState
          ? '📐 Click to place the second endpoint and finish the wall'
          : selectedId
          ? '↖ Drag the white handles to adjust wall endpoints · Press Delete to remove · Click elsewhere to deselect'
          : '↖ Click a wall to select it · Use Draw Wall to add new walls · Confirm when ready'}
      </div>
    </div>
  )
}
