// Guided-tour planner checks. Run: npm test  (node's built-in test runner)
//
// Fixtures are real detection results for the public sample plans in
// backend/tests/fixtures, trimmed to the fields the tour uses. The layout is
// used as confirmed, without manual edits.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { planTour, listEntrances } from '../src/components/cinematicTour.js'

const PLANS = ['3br_cad', 'truoba_render']
const load = (name) => JSON.parse(readFileSync(new URL(`./fixtures/${name}.detection.json`, import.meta.url)))

// Same world scale as SceneCanvas: printed-label scale when sane, else a 12 m house.
function sceneScale(det) {
  const xs = det.walls.flatMap((w) => [w.x1, w.x2])
  const ys = det.walls.flatMap((w) => [w.y1, w.y2])
  const b = { minX: Math.min(...xs), maxX: Math.max(...xs), minY: Math.min(...ys), maxY: Math.max(...ys) }
  const longPx = Math.max(b.maxX - b.minX, b.maxY - b.minY)
  let scale = det.stats?.scale_ft_per_px ? det.stats.scale_ft_per_px * 0.3048 : null
  if (!scale || longPx * scale < 3 || longPx * scale > 60) scale = 12 / longPx
  return { scale, cx: (b.minX + b.maxX) / 2, cy: (b.minY + b.maxY) / 2 }
}

function plan(det, options) {
  const { scale, cx, cy } = sceneScale(det)
  return planTour(det, { walls: det.walls, openings: det.openings }, cx, cy, scale, options)
}

function segmentHit(a, b, w) {
  const den = (b.x - a.x) * (w.y2 - w.y1) - (b.y - a.y) * (w.x2 - w.x1)
  if (Math.abs(den) < 1e-9) return null
  const t = ((w.x1 - a.x) * (w.y2 - w.y1) - (w.y1 - a.y) * (w.x2 - w.x1)) / den
  const u = ((w.x1 - a.x) * (b.y - a.y) - (w.y1 - a.y) * (b.x - a.x)) / den
  return t >= 0 && t <= 1 && u >= 0 && u <= 1 ? { x: a.x + t * (b.x - a.x), y: a.y + t * (b.y - a.y) } : null
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

for (const name of PLANS) {
  const det = load(name)

  test(`${name}: the tour visits rooms and has finite timings`, () => {
    const p = plan(det)
    assert.ok(p.stops.length >= 2, `expected at least 2 rooms, got ${p.stops.length}`)
    assert.ok(p.frames.some((f) => f.kind === 'reveal'))
    for (const f of p.frames) assert.ok(Number.isFinite(f.dur) && f.dur > 0, `bad duration in ${f.kind} frame`)
  })

  test(`${name}: the camera never walks through a wall`, () => {
    const p = plan(det)
    const doors = det.openings.filter((o) => o.type === 'door')
    const crossings = []
    for (const leg of p.route) {
      for (let k = 1; k < leg.length; k++) {
        for (const w of det.walls) {
          const hit = segmentHit(leg[k - 1], leg[k], w)
          if (!hit) continue
          const viaDoor = doors.some((d) => Math.hypot(hit.x - d.x, hit.y - d.y) <= (d.width_px || 30) / 2 + 6)
          if (!viaDoor) crossings.push(`${w.id} at (${Math.round(hit.x)}, ${Math.round(hit.y)})`)
        }
      }
    }
    assert.deepEqual(crossings, [])
  })

  test(`${name}: every stop is inside its room`, () => {
    const p = plan(det)
    for (const s of p.stops) {
      const leg = p.route.find((r) => r.length && pointInPoly(r[r.length - 1].x, r[r.length - 1].y, s.pg))
      assert.ok(leg, `no route ends inside ${s.name || s.id}`)
    }
  })

  test(`${name}: entrances are listed and the chosen one is used`, () => {
    const { scale } = sceneScale(det)
    const list = listEntrances(det, { walls: det.walls, openings: det.openings }, scale)
    assert.ok(list.length >= 1)
    assert.equal(new Set(list.map((e) => e.label)).size, list.length, 'entrance labels must be unique')
    const last = list[list.length - 1]
    assert.equal(plan(det, { entranceId: last.id }).entrance.id, last.id)
  })
}
