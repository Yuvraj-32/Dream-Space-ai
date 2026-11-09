import * as THREE from 'three'

/* ─── Guided (cinematic) tour planner ───────────────────────────────────────
 * Plans a camera route through the confirmed layout the way a person would
 * walk it:
 *   - starts outside the entrance (a door whose outer side reaches open air
 *     without crossing a wall; the caller can also choose it) and walks in,
 *   - visits each proper room once, nearest by WALKING distance first,
 *   - moves only through doorways: routes come from a walkable grid built from
 *     the walls (inflated by a body-width clearance) with a narrow passage cut
 *     through the middle of each door, so the camera never passes through a
 *     wall and stays clear of door frames,
 *   - stops at each room's most open spot (furthest from any wall) and turns
 *     towards the room's best view (longest open sight line, windows),
 *   - walks back to the entrance and drifts out.
 *
 * Frames (consumed by CinematicController):
 *   { kind: 'travel', p0, p1, dur, lookAt }   straight glide (drone in/out)
 *   { kind: 'path',   points, dur }           constant-speed walk along a route
 *   { kind: 'reveal', pos, dur, name, dims, yaw }  look-around ending on the best view
 *
 * Works in image pixels (same space as walls/openings/rooms); `scale` converts
 * pixels to metres and (cx, cy) is the image point placed at the world origin.
 */

const EYE = 1.6                 // camera height, m
const CELL_M = 0.15             // walkable-grid resolution, m
const CLEARANCE_M = 0.18        // keep the camera this far from wall faces
const DEFAULT_WALL_M = 0.15     // wall thickness when the layout has none
const MIN_ROOM_SQFT = 35        // smaller spaces (closets, ducts) are not visited
const MIN_UNNAMED_SQFT = 50     // unnamed spaces must be at least this big (caption shows size only)
const DOOR_CENTRE = 0.35        // walk within this share of the door's half-width of its centre
const SKIP_TYPES = new Set(['wardrobe', 'closet', 'shaft', 'duct', 'void'])
const SPEED = 1.1               // walking speed, m/s
const REVEAL_DUR = 6.5          // seconds for a full look-around

// ── small helpers ──────────────────────────────────────────────────────────
const parsePoly = (r) => {
  const p = typeof r.polygon === 'string' ? JSON.parse(r.polygon) : r.polygon
  return Array.isArray(p) && p.length >= 3 ? p : null
}

function pointInPoly(x, y, pg) {
  let c = false
  for (let i = 0, j = pg.length - 1; i < pg.length; j = i++) {
    const [xi, yi] = pg[i]
    const [xj, yj] = pg[j]
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) c = !c
  }
  return c
}

function distToSegment(px, py, x1, y1, x2, y2) {
  const dx = x2 - x1, dy = y2 - y1
  const L = dx * dx + dy * dy
  const t = L ? Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / L)) : 0
  return Math.hypot(px - x1 - t * dx, py - y1 - t * dy)
}

// Readable room name: the label printed on the plan if there is one
// ("MASTER BEDROOM 12'-8" x 12'-0"" -> "MASTER BEDROOM"), else the detected type.
function roomName(r) {
  const printed = (r.label || '').split(/\d/)[0].replace(/[\s\-:,(]+$/, '').trim()
  if (printed.length >= 3) return printed.toUpperCase()
  return r.type && r.type !== 'undefined' ? r.type.replace(/_/g, ' ').toUpperCase() : null
}

// Tiny binary min-heap for Dijkstra.
class Heap {
  constructor() { this.a = [] }
  get size() { return this.a.length }
  push(k, v) {
    const a = this.a
    a.push([k, v])
    let i = a.length - 1
    while (i > 0) {
      const p = (i - 1) >> 1
      if (a[p][0] <= a[i][0]) break
      ;[a[p], a[i]] = [a[i], a[p]]
      i = p
    }
  }
  pop() {
    const a = this.a
    const top = a[0]
    const last = a.pop()
    if (a.length) {
      a[0] = last
      let i = 0
      for (;;) {
        const l = 2 * i + 1, r = l + 1
        let m = i
        if (l < a.length && a[l][0] < a[m][0]) m = l
        if (r < a.length && a[r][0] < a[m][0]) m = r
        if (m === i) break
        ;[a[m], a[i]] = [a[i], a[m]]
        i = m
      }
    }
    return top
  }
}

// ── walkable grid ──────────────────────────────────────────────────────────
function buildGrid(walls, doors, wallThicknessPx, pxPerM) {
  const cellPx = CELL_M * pxPerM
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  for (const w of walls) {
    minX = Math.min(minX, w.x1, w.x2); maxX = Math.max(maxX, w.x1, w.x2)
    minY = Math.min(minY, w.y1, w.y2); maxY = Math.max(maxY, w.y1, w.y2)
  }
  const nx = Math.max(2, Math.ceil((maxX - minX) / cellPx) + 1)
  const ny = Math.max(2, Math.ceil((maxY - minY) / cellPx) + 1)
  const blocked = new Uint8Array(nx * ny)
  const toPx = (i, j) => [minX + i * cellPx, minY + j * cellPx]
  const clearPx = CLEARANCE_M * pxPerM

  // Walls, inflated by half their thickness plus the body clearance.
  for (const w of walls) {
    const reach = (wallThicknessPx(w) / 2) + clearPx
    const i0 = Math.max(0, Math.floor((Math.min(w.x1, w.x2) - reach - minX) / cellPx))
    const i1 = Math.min(nx - 1, Math.ceil((Math.max(w.x1, w.x2) + reach - minX) / cellPx))
    const j0 = Math.max(0, Math.floor((Math.min(w.y1, w.y2) - reach - minY) / cellPx))
    const j1 = Math.min(ny - 1, Math.ceil((Math.max(w.y1, w.y2) + reach - minY) / cellPx))
    for (let j = j0; j <= j1; j++) {
      for (let i = i0; i <= i1; i++) {
        const [x, y] = toPx(i, j)
        if (distToSegment(x, y, w.x1, w.y1, w.x2, w.y2) <= reach) blocked[j * nx + i] = 1
      }
    }
  }

  // Doorways: cut a passage through the inflated wall band at each door.
  for (const d of doors) {
    const wall = d.wall
    const half = Math.max((d.width_px || 0.8 * pxPerM) / 2, 0.3 * pxPerM)
    const depth = (wall ? wallThicknessPx(wall) / 2 : DEFAULT_WALL_M * pxPerM / 2) + clearPx + 2 * cellPx
    // Unit vectors along and across the door's wall (fall back to a disk).
    let ux = 1, uy = 0
    if (wall) {
      const L = Math.hypot(wall.x2 - wall.x1, wall.y2 - wall.y1) || 1
      ux = (wall.x2 - wall.x1) / L; uy = (wall.y2 - wall.y1) / L
    }
    const r = Math.max(half, depth)
    const i0 = Math.max(0, Math.floor((d.x - r - minX) / cellPx))
    const i1 = Math.min(nx - 1, Math.ceil((d.x + r - minX) / cellPx))
    const j0 = Math.max(0, Math.floor((d.y - r - minY) / cellPx))
    const j1 = Math.min(ny - 1, Math.ceil((d.y + r - minY) / cellPx))
    for (let j = j0; j <= j1; j++) {
      for (let i = i0; i <= i1; i++) {
        const [x, y] = toPx(i, j)
        const along = (x - d.x) * ux + (y - d.y) * uy
        const across = -(x - d.x) * uy + (y - d.y) * ux
        const inside = wall
          ? Math.abs(along) <= Math.max(cellPx * 1.01, half * DOOR_CENTRE) && Math.abs(across) <= depth
          : Math.hypot(x - d.x, y - d.y) <= half
        if (inside) blocked[j * nx + i] = 0
      }
    }
  }

  const cellOf = (x, y) => {
    const i = Math.round((x - minX) / cellPx)
    const j = Math.round((y - minY) / cellPx)
    return i >= 0 && j >= 0 && i < nx && j < ny ? j * nx + i : -1
  }
  return { nx, ny, blocked, cellPx, minX, minY, toPx, cellOf }
}

// Nearest walkable cell to a pixel point (spiral search).
function nearestFree(grid, x, y, maxCells = 12) {
  const { nx, ny, blocked, cellPx, minX, minY } = grid
  const ci = Math.round((x - minX) / cellPx)
  const cj = Math.round((y - minY) / cellPx)
  for (let r = 0; r <= maxCells; r++) {
    let best = -1, bd = Infinity
    for (let j = cj - r; j <= cj + r; j++) {
      for (let i = ci - r; i <= ci + r; i++) {
        if (i < 0 || j < 0 || i >= nx || j >= ny) continue
        if (Math.max(Math.abs(i - ci), Math.abs(j - cj)) !== r) continue
        const c = j * nx + i
        if (blocked[c]) continue
        const d = (i - ci) ** 2 + (j - cj) ** 2
        if (d < bd) { bd = d; best = c }
      }
    }
    if (best >= 0) return best
  }
  return -1
}

// Dijkstra from one cell: distance (in cells) and parent of every reachable cell.
function dijkstra(grid, start) {
  const { nx, ny, blocked } = grid
  const dist = new Float64Array(nx * ny).fill(Infinity)
  const parent = new Int32Array(nx * ny).fill(-1)
  const heap = new Heap()
  dist[start] = 0
  heap.push(0, start)
  const steps = [[1, 0, 1], [-1, 0, 1], [0, 1, 1], [0, -1, 1],
    [1, 1, Math.SQRT2], [1, -1, Math.SQRT2], [-1, 1, Math.SQRT2], [-1, -1, Math.SQRT2]]
  while (heap.size) {
    const [d, c] = heap.pop()
    if (d > dist[c]) continue
    const i = c % nx, j = (c - i) / nx
    for (const [di, dj, w] of steps) {
      const ii = i + di, jj = j + dj
      if (ii < 0 || jj < 0 || ii >= nx || jj >= ny) continue
      const n = jj * nx + ii
      if (blocked[n]) continue
      // No corner-cutting through a blocked diagonal.
      if (di && dj && (blocked[j * nx + ii] || blocked[jj * nx + i])) continue
      const nd = d + w
      if (nd < dist[n]) { dist[n] = nd; parent[n] = c; heap.push(nd, n) }
    }
  }
  return { dist, parent }
}

// Straight line between two cells stays on walkable cells (supercover walk).
function lineOfSight(grid, a, b) {
  const { nx, blocked } = grid
  let i0 = a % nx, j0 = (a - i0) / nx
  const i1 = b % nx, j1 = (b - i1) / nx
  const di = Math.abs(i1 - i0), dj = Math.abs(j1 - j0)
  const si = i0 < i1 ? 1 : -1, sj = j0 < j1 ? 1 : -1
  let err = di - dj
  for (;;) {
    if (blocked[j0 * nx + i0]) return false
    if (i0 === i1 && j0 === j1) return true
    const e2 = 2 * err
    if (e2 > -dj && e2 < di) {               // diagonal step: both side cells must be open
      if (blocked[j0 * nx + i0 + si] || blocked[(j0 + sj) * nx + i0]) return false
    }
    if (e2 > -dj) { err -= dj; i0 += si }
    if (e2 < di) { err += di; j0 += sj }
  }
}

// Cells from start to `end` (via parents), then string-pulled into few waypoints.
function routeTo(grid, parent, end) {
  const cells = []
  for (let c = end; c !== -1; c = parent[c]) cells.push(c)
  cells.reverse()
  if (cells.length <= 2) return cells
  const out = [cells[0]]
  let k = 0
  while (k < cells.length - 1) {
    let far = k + 1
    for (let m = cells.length - 1; m > k + 1; m--) {
      if (lineOfSight(grid, cells[k], cells[m])) { far = m; break }
    }
    out.push(cells[far])
    k = far
  }
  return out
}

// Distance from every walkable cell to the nearest blocked cell (two-pass chamfer).
function openness(grid) {
  const { nx, ny, blocked } = grid
  const d = new Float32Array(nx * ny)
  for (let c = 0; c < d.length; c++) d[c] = blocked[c] ? 0 : 1e9
  for (let j = 0; j < ny; j++) {
    for (let i = 0; i < nx; i++) {
      const c = j * nx + i
      if (i > 0) d[c] = Math.min(d[c], d[c - 1] + 1)
      if (j > 0) d[c] = Math.min(d[c], d[c - nx] + 1)
      if (i > 0 && j > 0) d[c] = Math.min(d[c], d[c - nx - 1] + Math.SQRT2)
      if (i < nx - 1 && j > 0) d[c] = Math.min(d[c], d[c - nx + 1] + Math.SQRT2)
    }
  }
  for (let j = ny - 1; j >= 0; j--) {
    for (let i = nx - 1; i >= 0; i--) {
      const c = j * nx + i
      if (i < nx - 1) d[c] = Math.min(d[c], d[c + 1] + 1)
      if (j < ny - 1) d[c] = Math.min(d[c], d[c + nx] + 1)
      if (i < nx - 1 && j < ny - 1) d[c] = Math.min(d[c], d[c + nx + 1] + Math.SQRT2)
      if (i > 0 && j < ny - 1) d[c] = Math.min(d[c], d[c + nx - 1] + Math.SQRT2)
    }
  }
  return d
}

// ── planner ────────────────────────────────────────────────────────────────
/**
 * @returns {{ frames: object[], route: {x:number,y:number}[][], stops: object[], entrance: object|null }}
 *   frames for the camera, plus the planned routes in image pixels (for testing).
 */
export function planTour(detection, confirmedLayout, cx, cy, scale, options = {}) {
  const empty = { frames: [], route: [], stops: [], entrance: null, skipped: [] }
  const rooms = detection?.rooms || []
  const walls = confirmedLayout?.walls?.length ? confirmedLayout.walls : (detection?.walls || [])
  if (!rooms.length || !walls.length || !(scale > 0)) return empty
  const pxPerM = 1 / scale

  // Wall thickness: the layout keeps wall ids, detection keeps thickness.
  const thick = new Map((detection?.walls || []).map((w) => [w.id, w.thickness]))
  const wallThicknessPx = (w) => w.thickness || thick.get(w.id) || DEFAULT_WALL_M * pxPerM
  const wallById = new Map(walls.map((w) => [w.id, w]))
  const openingsAll = confirmedLayout?.openings || detection?.openings || []
  const doors = openingsAll
    .filter((o) => o.type === 'door')
    .map((o) => ({ ...o, wall: wallById.get(o.wall_id) || nearestWall(walls, o) }))
  if (!doors.length) return empty

  const grid = buildGrid(walls, doors, wallThicknessPx, pxPerM)
  const windows = openingsAll.filter((o) => o.type === 'window')
  const windowsOf = (s) => windows.filter((w) => nearOutline(w, s.pg, 0.6 * pxPerM))
  const open = openness(grid)
  const toWorld = (x, y, h = EYE) => new THREE.Vector3((x - cx) * scale, h, (y - cy) * scale)
  const cellPx = (c) => grid.toPx(c % grid.nx, Math.floor(c / grid.nx))

  // Rooms worth visiting, each with its most open walkable spot.
  const stops = []
  const skipped = []
  for (const r of rooms) {
    const pg = parsePoly(r)
    const type = (r.type || '').toLowerCase()
    if (!pg || SKIP_TYPES.has(type)) { skipped.push({ id: r.id, reason: 'closet or no outline' }); continue }
    const sqft = r.area_sqft ?? (r.area ? r.area * scale * scale * 10.7639 : 0)
    const name = roomName(r)
    if (sqft < (name ? MIN_ROOM_SQFT : MIN_UNNAMED_SQFT)) { skipped.push({ id: r.id, reason: 'too small' }); continue }
    let best = -1, bestOpen = 0
    for (let c = 0; c < grid.blocked.length; c++) {
      if (grid.blocked[c] || open[c] <= bestOpen) continue
      const [x, y] = cellPx(c)
      if (pointInPoly(x, y, pg)) { best = c; bestOpen = open[c] }
    }
    if (best < 0) { skipped.push({ id: r.id, reason: 'no walkable spot inside' }); continue }
    stops.push({ id: r.id, name, dims: roomDims(r, sqft), cell: best, sqft, pg })
  }
  if (!stops.length) return empty

  // Entrance: the chosen door, else an exterior door opening into the biggest room.
  const entrances = findEntrances(doors, walls, stops, grid, pxPerM, wallThicknessPx)
  const chosen = entrances.find((e) => e.door.id === options.entranceId) || entrances[0]
  if (!chosen) return { ...empty, skipped }
  const entranceList = entrances.map((e) => ({ id: e.door.id, label: e.label }))
  if (options.listOnly) return { ...empty, entrances: entranceList }
  const entrance = chosen.door
  const [ox, oy] = chosen.out

  const startCell = nearestFree(grid, entrance.x - ox * 0.3 * pxPerM, entrance.y - oy * 0.3 * pxPerM)
  if (startCell < 0) return empty

  // Visit order: nearest by walking distance, starting from the entrance.
  const frames = []
  const route = []
  let cur = startCell
  let curPos = toWorld(...cellPx(startCell))
  const outside = toWorld(entrance.x + ox * 1.2 * pxPerM, entrance.y + oy * 1.2 * pxPerM)
  const drone = toWorld(entrance.x + ox * 4.0 * pxPerM, entrance.y + oy * 4.0 * pxPerM, 3.4)
  frames.push({ kind: 'travel', p0: drone, p1: outside, dur: 3.2, lookAt: curPos.clone() })
  frames.push({ kind: 'travel', p0: outside, p1: curPos.clone(), dur: 1.6, lookAt: curPos.clone() })

  const walkTo = (parent, target) => {
    const cells = routeTo(grid, parent, target)
    const pts = cells.map((c) => toWorld(...cellPx(c)))
    route.push(cells.map((c) => { const [x, y] = cellPx(c); return { x, y } }))
    let len = 0
    for (let k = 1; k < pts.length; k++) len += pts[k].distanceTo(pts[k - 1])
    if (len > 0.05) frames.push({ kind: 'path', points: pts, dur: Math.max(1.5, len / SPEED) })
    return pts[pts.length - 1]
  }

  const todo = [...stops]
  const visited = []
  while (todo.length) {
    const { dist, parent } = dijkstra(grid, cur)
    let k = -1
    todo.forEach((s, i) => { if (dist[s.cell] < Infinity && (k < 0 || dist[s.cell] < dist[todo[k].cell])) k = i })
    if (k < 0) {                            // the rest can't be reached through doors
      todo.forEach((s) => skipped.push({ id: s.id, reason: 'no doorway route' }))
      break
    }
    const s = todo.splice(k, 1)[0]
    curPos = walkTo(parent, s.cell)
    const v = bestView(grid, s, windowsOf(s), pxPerM)
    frames.push({ kind: 'reveal', pos: curPos.clone(), dur: REVEAL_DUR, name: s.name, dims: s.dims, yaw: Math.atan2(v.x, v.y) })
    visited.push(s)
    cur = s.cell
  }

  // Walk back to the entrance and drift out.
  const back = dijkstra(grid, cur)
  if (back.dist[startCell] < Infinity && cur !== startCell) walkTo(back.parent, startCell)
  const exitFrom = toWorld(...cellPx(startCell))
  frames.push({ kind: 'travel', p0: exitFrom, p1: outside.clone(), dur: 1.6, lookAt: outside.clone() })
  const up = drone.clone()
  frames.push({ kind: 'travel', p0: outside.clone(), p1: up, dur: 3.2, lookAt: toWorld(entrance.x, entrance.y, 0.5) })

  return { frames, route, stops: visited, entrance, skipped, entrances: entranceList }
}

function nearOutline(p, pg, tol) {
  return pg.some((_, i) => {
    const a = pg[i], b = pg[(i + 1) % pg.length]
    return distToSegment(p.x, p.y, a[0], a[1], b[0], b[1]) < tol
  })
}

// Size caption: the printed size, unless it clearly belongs to a different
// space (e.g. an open-plan room carrying the dining area's label) — then the
// measured size.
function roomDims(r, sqft) {
  const measured = r.computed_dim_ft ? `${r.computed_dim_ft[0]} × ${r.computed_dim_ft[1]} ft` : ''
  if (!r.label_dim || !/\d/.test(r.label_dim)) return measured
  const printed = r.label_dim.replace(/^[^\d]*/, '')
  const lf = r.label_dim_ft
  if (Array.isArray(lf) && lf[0] > 0 && lf[1] > 0 && sqft > 0) {
    const ratio = (lf[0] * lf[1]) / sqft
    if (ratio < 0.65 || ratio > 1.5) return measured || printed
  }
  return printed
}

// Exterior doors: a straight line from one side of the door reaches past the
// building without crossing another wall. Returns [{ door, out:[ox,oy], into, label }]
// sorted best-first (opening into the biggest room).
function findEntrances(doors, walls, stops, grid, pxPerM, wallThicknessPx) {
  const maxX = grid.minX + (grid.nx - 1) * grid.cellPx
  const maxY = grid.minY + (grid.ny - 1) * grid.cellPx
  const reach = Math.hypot(maxX - grid.minX, maxY - grid.minY) + 10
  const crosses = (x1, y1, x2, y2, skip) => walls.some((w) => {
    if (w === skip) return false
    const den = (x2 - x1) * (w.y2 - w.y1) - (y2 - y1) * (w.x2 - w.x1)
    if (Math.abs(den) < 1e-9) return false
    const t = ((w.x1 - x1) * (w.y2 - w.y1) - (w.y1 - y1) * (w.x2 - w.x1)) / den
    const u = ((w.x1 - x1) * (y2 - y1) - (w.y1 - y1) * (x2 - x1)) / den
    return t > 0 && t <= 1 && u >= 0 && u <= 1
  })
  const sideName = (ox, oy) => (Math.abs(ox) > Math.abs(oy) ? (ox > 0 ? 'right' : 'left') : (oy > 0 ? 'bottom' : 'top'))
  const found = []
  for (const d of doors) {
    if (!d.wall) continue
    const L = Math.hypot(d.wall.x2 - d.wall.x1, d.wall.y2 - d.wall.y1) || 1
    const nx = -(d.wall.y2 - d.wall.y1) / L, ny = (d.wall.x2 - d.wall.x1) / L
    const off = wallThicknessPx(d.wall) / 2 + 2
    const outSides = [1, -1].filter((sgn) => {
      const sx = d.x + nx * sgn * off, sy = d.y + ny * sgn * off
      return !crosses(sx, sy, sx + nx * sgn * reach, sy + ny * sgn * reach, d.wall)
    })
    if (outSides.length !== 1) continue           // both open = a stray wall; none = interior
    const ox = nx * outSides[0], oy = ny * outSides[0]
    const into = roomAtDoor(d, stops, pxPerM)
    found.push({ door: d, out: [ox, oy], into, side: sideName(ox, oy) })
  }
  let list = found.sort((a, b) => (b.into?.sqft || 0) - (a.into?.sqft || 0))
  if (!list.length) {
    // No door clearly reaches the outside (e.g. an upper floor): offer every
    // door, nearest to the outer edge first, facing the nearest edge.
    const edge = (d) => Math.min(d.x - grid.minX, maxX - d.x, d.y - grid.minY, maxY - d.y)
    list = [...doors].sort((a, b) => edge(a) - edge(b)).map((d) => {
      const e = [[d.x - grid.minX, -1, 0], [maxX - d.x, 1, 0], [d.y - grid.minY, 0, -1], [maxY - d.y, 0, 1]]
        .sort((a, b) => a[0] - b[0])[0]
      const into = roomAtDoor(d, stops, pxPerM)
      return { door: d, out: [e[1], e[2]], into, side: sideName(e[1], e[2]) }
    })
  }
  // Labels people can tell apart: "Living Room door · bottom side"; unnamed
  // rooms go by their size, and any label that still repeats gets a number.
  const roomLabel = (r) => (r ? (r.name ? titleCase(r.name) : `${Math.round(r.sqft)} sq ft room`) : 'Outer')
  let base = list.map((e) => `${roomLabel(e.into)} door · ${e.side} side`)
  // Same name twice (two bedrooms): add the room size first.
  base = base.map((b, i) => (base.filter((x) => x === b).length > 1 && list[i].into?.name
    ? `${roomLabel(list[i].into)} (${Math.round(list[i].into.sqft)} sq ft) door · ${list[i].side} side`
    : b))
  const seen = {}
  list.forEach((e, i) => {
    const total = base.filter((b) => b === base[i]).length
    seen[base[i]] = (seen[base[i]] || 0) + 1
    e.label = total > 1 ? `${base[i]} (${seen[base[i]]})` : base[i]
  })
  return list
}

// The visited room whose outline the door sits on (closest outline wins).
function roomAtDoor(d, stops, pxPerM) {
  let best = null, bd = 0.6 * pxPerM
  for (const s of stops) {
    for (let i = 0; i < s.pg.length; i++) {
      const a = s.pg[i], b = s.pg[(i + 1) % s.pg.length]
      const dd = distToSegment(d.x, d.y, a[0], a[1], b[0], b[1])
      if (dd < bd) { bd = dd; best = s }
    }
  }
  return best
}

const titleCase = (t) => t.toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase())

// Best direction to face from a room's stop: the longest open sight lines
// (averaged over a 30° window) with a bonus towards the room's windows.
// Returns a unit vector in image space.
function bestView(grid, stop, windows, pxPerM) {
  const [sx, sy] = grid.toPx(stop.cell % grid.nx, Math.floor(stop.cell / grid.nx))
  const N = 72
  const rays = []
  for (let k = 0; k < N; k++) {
    const a = (k / N) * Math.PI * 2
    const dx = Math.cos(a), dy = Math.sin(a)
    let d = 0
    for (;;) {
      d += grid.cellPx * 0.5
      const c = grid.cellOf(sx + dx * d, sy + dy * d)
      if (c < 0 || grid.blocked[c]) break
    }
    let bonus = 0
    for (const w of windows) {
      const wa = Math.atan2(w.y - sy, w.x - sx)
      const diff = Math.abs(Math.atan2(Math.sin(wa - a), Math.cos(wa - a)))
      if (diff < 0.25) bonus = Math.max(bonus, 1.5 * pxPerM)
    }
    rays.push({ dx, dy, d: d + bonus })
  }
  let best = 0, bestScore = -1
  for (let k = 0; k < N; k++) {
    let sc = 0
    for (let m = -3; m <= 3; m++) sc += rays[(k + m + N) % N].d
    if (sc > bestScore) { bestScore = sc; best = k }
  }
  return { x: rays[best].dx, y: rays[best].dy }
}

/** Doors the tour could start from, best guess first: [{ id, label }]. */
export function listEntrances(detection, confirmedLayout, scale) {
  const plan = planTour(detection, confirmedLayout, 0, 0, scale, { listOnly: true })
  return plan.entrances || []
}

function nearestWall(walls, p) {
  let best = null, bd = Infinity
  for (const w of walls) {
    const d = distToSegment(p.x, p.y, w.x1, w.y1, w.x2, w.y2)
    if (d < bd) { bd = d; best = w }
  }
  return best
}

export function buildCinematicTour(detection, confirmedLayout, cx, cy, scale, options) {
  return planTour(detection, confirmedLayout, cx, cy, scale, options).frames
}
