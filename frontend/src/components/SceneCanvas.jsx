import { useRef, useState, useEffect, useMemo } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { OrbitControls, Grid, Text, PointerLockControls } from '@react-three/drei'
import * as THREE from 'three'

// Suppress internal react-three-fiber / Three.js deprecation warnings
if (typeof window !== 'undefined') {
  const _cw = console.warn
  console.warn = (...args) => {
    if (typeof args[0] === 'string') {
      if (args[0].includes('THREE.Clock')) return
      if (args[0].includes('PCFSoftShadowMap')) return
    }
    _cw(...args)
  }
}

import MaterialSelector from './MaterialSelector'

/* ─── Math Helpers ───────────────────────────────────────────── */
function distToSegment(px, pz, ax, az, bx, bz) {
  const dx = bx - ax
  const dz = bz - az
  const lenSq = dx * dx + dz * dz
  if (lenSq === 0) return Math.hypot(px - ax, pz - az)
  let t = ((px - ax) * dx + (pz - az) * dz) / lenSq
  t = Math.max(0, Math.min(1, t))
  return Math.hypot(px - (ax + t * dx), pz - (az + t * dz))
}

/* ─── Slowly spinning placeholder box ───────────────────────── */
function PlaceholderBuilding() {
  const groupRef = useRef(null)

  useFrame((_, delta) => {
    if (groupRef.current) {
      groupRef.current.rotation.y += delta * 0.25
    }
  })

  return (
    <group ref={groupRef}>
      {/* Main body */}
      <mesh castShadow receiveShadow position={[0, 1, 0]}>
        <boxGeometry args={[2, 2, 2]} />
        <meshStandardMaterial
          color="#1c2235"
          roughness={0.4}
          metalness={0.3}
          emissive="#6378ff"
          emissiveIntensity={0.08}
        />
      </mesh>

      {/* Wireframe overlay */}
      <mesh position={[0, 1, 0]}>
        <boxGeometry args={[2.01, 2.01, 2.01]} />
        <meshBasicMaterial
          color="#6378ff"
          wireframe
          transparent
          opacity={0.4}
        />
      </mesh>

      {/* Roof slab */}
      <mesh castShadow position={[0, 2.1, 0]}>
        <boxGeometry args={[2.2, 0.12, 2.2]} />
        <meshStandardMaterial
          color="#6378ff"
          roughness={0.3}
          metalness={0.5}
          emissive="#6378ff"
          emissiveIntensity={0.15}
        />
      </mesh>

      {/* Door cutout illusion */}
      <mesh position={[0, 0.5, 1.02]}>
        <planeGeometry args={[0.5, 1]} />
        <meshBasicMaterial color="#0a0c14" />
      </mesh>

      {/* Window left */}
      <mesh position={[-0.6, 1.2, 1.02]}>
        <planeGeometry args={[0.45, 0.35]} />
        <meshStandardMaterial
          color="#3dd9c6"
          emissive="#3dd9c6"
          emissiveIntensity={0.6}
          transparent
          opacity={0.6}
        />
      </mesh>

      {/* Window right */}
      <mesh position={[0.6, 1.2, 1.02]}>
        <planeGeometry args={[0.45, 0.35]} />
        <meshStandardMaterial
          color="#3dd9c6"
          emissive="#3dd9c6"
          emissiveIntensity={0.6}
          transparent
          opacity={0.6}
        />
      </mesh>
    </group>
  )
}

/* ─── Floating label above box ────────────────────────────── */
function SceneLabel({ text }) {
  return (
    <Text
      position={[0, 3.2, 0]}
      fontSize={0.22}
      color="#8892b0"
      anchorX="center"
      anchorY="middle"
    >
      {text}
    </Text>
  )
}

/* ─── Animated ground grid ring ───────────────────────────── */
function GroundGlow() {
  const ref = useRef(null)
  useFrame(({ clock }) => {
    if (ref.current) {
      ref.current.material.opacity = 0.08 + Math.sin(clock.elapsedTime * 1.5) * 0.04
    }
  })
  return (
    <mesh ref={ref} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.001, 0]}>
      <circleGeometry args={[4, 64]} />
      <meshBasicMaterial color="#6378ff" transparent opacity={0.08} />
    </mesh>
  )
}

/* ─── Extruded Walls rendering with door/window gaps ──────── */
function Walls3D({ walls, openings, cx, cy, scale, onSelectWall, selectedSurface, surfaceCustomizations }) {
  const wall_height = 2.6
  const wall_thickness = 0.15
  const door_height = 2.0
  const window_sill = 0.9
  const window_head = 2.1

  const meshes = []

  walls.forEach((wall) => {
    const rawP1x = (wall.x1 - cx) * scale
    const rawP1z = (wall.y1 - cy) * scale
    const p2x = (wall.x2 - cx) * scale
    const p2z = (wall.y2 - cy) * scale

    const dx = p2x - rawP1x
    const dz = p2z - rawP1z
    const rawLen = Math.hypot(dx, dz)
    if (rawLen < 0.05) return

    const ux = dx / rawLen
    const uz = dz / rawLen
    const angle = Math.atan2(dz, dx)

    // Extend both ends by half the wall thickness so perpendicular walls
    // overlap at junctions and fill the corner square (otherwise thin
    // center-line boxes meet at a point and leave a visible gap). Openings
    // are measured from p1x below, so shifting the start keeps them aligned.
    const ext = wall_thickness / 2
    const p1x = rawP1x - ux * ext
    const p1z = rawP1z - uz * ext
    const length = rawLen + 2 * ext

    const isSelected = selectedSurface?.type === 'wall' && selectedSurface?.id === wall.id
    const custom = surfaceCustomizations[wall.id] || {}
    const color = custom.color || '#f0f2f5'
    const roughness = custom.roughness !== undefined ? custom.roughness : 0.8
    const metalness = custom.metalness !== undefined ? custom.metalness : 0.05
    const clearcoat = custom.clearcoat !== undefined ? custom.clearcoat : 0

    // Filter and project openings belonging to this wall
    const wallOpenings = (openings || [])
      .filter((op) => op.wallId === wall.id)
      .map((op) => {
        const op_x = (op.x - cx) * scale
        const op_z = (op.y - cy) * scale
        const dist_from_p1 = (op_x - p1x) * ux + (op_z - p1z) * uz
        const op_width = (op.width_px || 90) * scale
        return {
          t1: Math.max(0, dist_from_p1 - op_width / 2),
          t2: Math.min(length, dist_from_p1 + op_width / 2),
          type: op.type,
          id: op.id,
        }
      })
      .filter((op) => op.t1 < length && op.t2 > 0)
      .sort((a, b) => a.t1 - b.t1)

    let current_t = 0

    wallOpenings.forEach((op, idx) => {
      // 1. Solid wall segment before opening
      if (op.t1 > current_t) {
        const seg_len = op.t1 - current_t
        const mid_t = current_t + seg_len / 2
        const sx = p1x + mid_t * ux
        const sz = p1z + mid_t * uz
        meshes.push(
          <mesh
            key={`${wall.id}-seg-${idx}`}
            castShadow
            receiveShadow
            position={[sx, wall_height / 2, sz]}
            rotation={[0, -angle, 0]}
            onClick={(e) => { e.stopPropagation(); onSelectWall?.(wall.id); }}
          >
            <boxGeometry args={[seg_len, wall_height, wall_thickness]} />
            <meshStandardMaterial color={color} roughness={roughness} metalness={metalness} clearcoat={clearcoat} />
          </mesh>
        )

        if (isSelected) {
          meshes.push(
            <mesh
              key={`${wall.id}-seg-${idx}-glow`}
              position={[sx, wall_height / 2, sz]}
              rotation={[0, -angle, 0]}
            >
              <boxGeometry args={[seg_len + 0.005, wall_height + 0.005, wall_thickness + 0.005]} />
              <meshBasicMaterial color="#3dd9c6" wireframe opacity={0.35} transparent />
            </mesh>
          )
        }
      }

      // 2. The opening itself
      const seg_len = op.t2 - op.t1
      if (seg_len > 0.02) {
        const mid_t = op.t1 + seg_len / 2
        const sx = p1x + mid_t * ux
        const sz = p1z + mid_t * uz

        if (op.type === 'door') {
          // Lintel above door
          const lintel_h = wall_height - door_height
          const lintel_y = door_height + lintel_h / 2
          meshes.push(
            <mesh
              key={`${wall.id}-door-lintel-${op.id}`}
              castShadow
              position={[sx, lintel_y, sz]}
              rotation={[0, -angle, 0]}
              onClick={(e) => { e.stopPropagation(); onSelectWall?.(wall.id); }}
            >
              <boxGeometry args={[seg_len, lintel_h, wall_thickness]} />
              <meshStandardMaterial color={color} roughness={roughness} metalness={metalness} clearcoat={clearcoat} />
            </mesh>
          )

          if (isSelected) {
            meshes.push(
              <mesh
                key={`${wall.id}-door-lintel-${op.id}-glow`}
                position={[sx, lintel_y, sz]}
                rotation={[0, -angle, 0]}
              >
                <boxGeometry args={[seg_len + 0.005, lintel_h + 0.005, wall_thickness + 0.005]} />
                <meshBasicMaterial color="#3dd9c6" wireframe opacity={0.35} transparent />
              </mesh>
            )
          }

          // Decorative door frame
          meshes.push(
            <group key={`${wall.id}-door-frame-${op.id}`} position={[sx, door_height / 2, sz]} rotation={[0, -angle, 0]}>
              {/* Left casing */}
              <mesh position={[-seg_len / 2 + 0.02, 0, 0]}>
                <boxGeometry args={[0.04, door_height, wall_thickness + 0.015]} />
                <meshStandardMaterial color="#3a2512" roughness={0.6} />
              </mesh>
              {/* Right casing */}
              <mesh position={[seg_len / 2 - 0.02, 0, 0]}>
                <boxGeometry args={[0.04, door_height, wall_thickness + 0.015]} />
                <meshStandardMaterial color="#3a2512" roughness={0.6} />
              </mesh>
              {/* Top header frame */}
              <mesh position={[0, door_height / 2 - 0.02, 0]}>
                <boxGeometry args={[seg_len, 0.04, wall_thickness + 0.015]} />
                <meshStandardMaterial color="#3a2512" roughness={0.6} />
              </mesh>
            </group>
          )
        } else {
          // Window
          // Sill below window
          meshes.push(
            <mesh
              key={`${wall.id}-win-sill-${op.id}`}
              castShadow
              receiveShadow
              position={[sx, window_sill / 2, sz]}
              rotation={[0, -angle, 0]}
              onClick={(e) => { e.stopPropagation(); onSelectWall?.(wall.id); }}
            >
              <boxGeometry args={[seg_len, window_sill, wall_thickness]} />
              <meshStandardMaterial color={color} roughness={roughness} metalness={metalness} clearcoat={clearcoat} />
            </mesh>
          )

          if (isSelected) {
            meshes.push(
              <mesh
                key={`${wall.id}-win-sill-${op.id}-glow`}
                position={[sx, window_sill / 2, sz]}
                rotation={[0, -angle, 0]}
              >
                <boxGeometry args={[seg_len + 0.005, window_sill + 0.005, wall_thickness + 0.005]} />
                <meshBasicMaterial color="#3dd9c6" wireframe opacity={0.35} transparent />
              </mesh>
            )
          }

          // Lintel above window
          const lintel_h = wall_height - window_head
          const lintel_y = window_head + lintel_h / 2
          meshes.push(
            <mesh
              key={`${wall.id}-win-lintel-${op.id}`}
              castShadow
              position={[sx, lintel_y, sz]}
              rotation={[0, -angle, 0]}
              onClick={(e) => { e.stopPropagation(); onSelectWall?.(wall.id); }}
            >
              <boxGeometry args={[seg_len, lintel_h, wall_thickness]} />
              <meshStandardMaterial color={color} roughness={roughness} metalness={metalness} clearcoat={clearcoat} />
            </mesh>
          )

          if (isSelected) {
            meshes.push(
              <mesh
                key={`${wall.id}-win-lintel-${op.id}-glow`}
                position={[sx, lintel_y, sz]}
                rotation={[0, -angle, 0]}
              >
                <boxGeometry args={[seg_len + 0.005, lintel_h + 0.005, wall_thickness + 0.005]} />
                <meshBasicMaterial color="#3dd9c6" wireframe opacity={0.35} transparent />
              </mesh>
            )
          }

          // Glass pane
          const glass_h = window_head - window_sill
          const glass_y = window_sill + glass_h / 2
          meshes.push(
            <mesh
              key={`${wall.id}-win-glass-${op.id}`}
              position={[sx, glass_y, sz]}
              rotation={[0, -angle, 0]}
            >
              <boxGeometry args={[seg_len, glass_h, 0.03]} />
              <meshStandardMaterial
                color="#aae6ff"
                transparent
                opacity={0.4}
                roughness={0.1}
                metalness={0.9}
              />
            </mesh>
          )
        }
      }
      current_t = op.t2
    })

    // 3. Final wall segment after all openings
    if (current_t < length) {
      const seg_len = length - current_t
      const mid_t = current_t + seg_len / 2
      const sx = p1x + mid_t * ux
      const sz = p1z + mid_t * uz
      meshes.push(
        <mesh
          key={`${wall.id}-seg-end`}
          castShadow
          receiveShadow
          position={[sx, wall_height / 2, sz]}
          rotation={[0, -angle, 0]}
          onClick={(e) => { e.stopPropagation(); onSelectWall?.(wall.id); }}
        >
          <boxGeometry args={[seg_len, wall_height, wall_thickness]} />
          <meshStandardMaterial color={color} roughness={roughness} metalness={metalness} clearcoat={clearcoat} />
        </mesh>
      )

      if (isSelected) {
        meshes.push(
          <mesh
            key={`${wall.id}-seg-end-glow`}
            position={[sx, wall_height / 2, sz]}
            rotation={[0, -angle, 0]}
          >
            <boxGeometry args={[seg_len + 0.005, wall_height + 0.005, wall_thickness + 0.005]} />
            <meshBasicMaterial color="#3dd9c6" wireframe opacity={0.35} transparent />
          </mesh>
        )
      }
    }
  })

  return <>{meshes}</>
}

function PlayerController({ walls, openings, cx, cy, scale, rooms, active }) {
  const { camera } = useThree()
  const keys = useRef({ w: false, a: false, s: false, d: false })
  const dir = useRef(new THREE.Vector3())
  const side = useRef(new THREE.Vector3())
  const move = useRef(new THREE.Vector3())

  // Doorways in world space — collision is disabled within a doorway so the
  // player can actually walk through doors (the wall segments are otherwise
  // solid across the opening).
  const doorways = useMemo(() => (openings || [])
    .filter(o => (o.type === 'door'))
    .map(o => ({
      x: (o.x - cx) * scale,
      z: (o.y - cy) * scale,
      r: ((o.width_px || 90) * scale) / 2 + 0.25,   // half-width + margin
    })), [openings, cx, cy, scale])
  const inDoorway = (px, pz) => doorways.some(d => Math.hypot(px - d.x, pz - d.z) < d.r)

  // Position spawn point safely in the center of the first room
  useEffect(() => {
    if (active) {
      let spawnX = 0
      let spawnZ = 2
      if (rooms && rooms.length > 0) {
        const firstRoom = rooms[0]
        const rx = firstRoom.bbox.x + firstRoom.bbox.w / 2
        const ry = firstRoom.bbox.y + firstRoom.bbox.h / 2
        spawnX = (rx - cx) * scale
        spawnZ = (ry - cy) * scale
      }
      camera.position.set(spawnX, 1.6, spawnZ)
      camera.lookAt(spawnX, 1.6, spawnZ - 1)
      camera.fov = 72          // wide interior FOV to match a human's sense of space
      camera.updateProjectionMatrix()
    }
    return () => { camera.fov = 55; camera.updateProjectionMatrix() }
  }, [active, camera, rooms, cx, cy, scale])

  useEffect(() => {
    const handleKeyDown = (e) => {
      const k = e.key.toLowerCase()
      if (k in keys.current) keys.current[k] = true
    }
    const handleKeyUp = (e) => {
      const k = e.key.toLowerCase()
      if (k in keys.current) keys.current[k] = false
    }
    window.addEventListener('keydown', handleKeyDown)
    window.addEventListener('keyup', handleKeyUp)
    return () => {
      window.removeEventListener('keydown', handleKeyDown)
      window.removeEventListener('keyup', handleKeyUp)
    }
  }, [])

  useFrame((_, delta) => {
    if (!active) return

    const speed = 2.4 * delta // Movement speed (m/s)
    camera.getWorldDirection(dir.current)
    dir.current.y = 0
    dir.current.normalize()

    side.current.copy(dir.current).cross(camera.up).normalize()

    move.current.set(0, 0, 0)
    if (keys.current.w) move.current.add(dir.current)
    if (keys.current.s) move.current.sub(dir.current)
    if (keys.current.a) move.current.sub(side.current)
    if (keys.current.d) move.current.add(side.current)

    if (move.current.lengthSq() > 0) {
      move.current.normalize().multiplyScalar(speed)

      const nextX = camera.position.x + move.current.x
      const nextZ = camera.position.z + move.current.z

      let collisionX = false
      let collisionZ = false
      const playerRadius = 0.24 // Collision envelope (small enough for doorways)

      // A candidate inside a doorway is always allowed (skip wall collision).
      const freeX = inDoorway(nextX, camera.position.z)
      const freeZ = inDoorway(camera.position.x, nextZ)

      if (!freeX || !freeZ) {
        for (const w of walls) {
          const ax = (w.x1 - cx) * scale
          const az = (w.y1 - cy) * scale
          const bx = (w.x2 - cx) * scale
          const bz = (w.y2 - cy) * scale

          if (!freeX && distToSegment(nextX, camera.position.z, ax, az, bx, bz) < playerRadius) {
            collisionX = true
          }
          if (!freeZ && distToSegment(camera.position.x, nextZ, ax, az, bx, bz) < playerRadius) {
            collisionZ = true
          }
        }
      }

      if (!collisionX) camera.position.x = nextX
      if (!collisionZ) camera.position.z = nextZ
    }

    // Lock player height to eye-level
    camera.position.y = 1.6
  })

  if (!active) return null
  return <PointerLockControls />
}

/* ─── Cinematic Tour: keyframe path builder ─────────────────────
 * Produces an ordered list of camera keyframes:
 *   - a "drone-in" entry through an exterior door,
 *   - for each room: travel to its center then a slow 360° reveal,
 *   - doorway threading between rooms (segments pass THROUGH door
 *     positions, so the camera never crosses a wall),
 *   - an exit back out through a door.
 * Falls back to eased room-center visits if no doors were detected.
 */
function buildCinematicTour(detection, confirmedLayout, cx, cy, scale) {
  const rooms = detection?.rooms || []
  if (rooms.length === 0) return []

  const EYE = 1.6
  const toWorld = (ix, iy) => new THREE.Vector3((ix - cx) * scale, EYE, (iy - cy) * scale)

  // Rooms in world space with a display label.
  const R = rooms.map(r => {
    const center = r.centroid
      ? toWorld(r.centroid.x, r.centroid.y)
      : toWorld(r.bbox.x + r.bbox.w / 2, r.bbox.y + r.bbox.h / 2)
    const dims = r.label_dim
      || (r.computed_dim_ft ? `${r.computed_dim_ft[0]} × ${r.computed_dim_ft[1]} ft` : '')
    const name = (r.type && r.type !== 'undefined')
      ? r.type.replace(/_/g, ' ').toUpperCase() : 'ROOM'
    return { center, name, dims }
  })

  // Doors in world space (prefer the user-edited layout).
  const doors = (confirmedLayout?.openings || detection?.openings || [])
    .filter(o => o.type === 'door')
    .map(o => toWorld(o.x, o.y))

  // Building center = mean room center (for "outward" direction at doors).
  const bc = new THREE.Vector3()
  R.forEach(r => bc.add(r.center))
  bc.multiplyScalar(1 / R.length)

  const nearestDoor = (p) => {
    let best = null, bd = Infinity
    for (const d of doors) { const dd = d.distanceTo(p); if (dd < bd) { bd = dd; best = d } }
    return best
  }
  const outward = (p) => new THREE.Vector3().subVectors(p, bc).setY(0).normalize()

  // Order rooms: start from the room furthest from centre (likely near an
  // entrance), then nearest-neighbour chain for a spatially smooth path.
  const order = []
  const used = new Array(R.length).fill(false)
  let startIdx = 0, far = -1
  R.forEach((r, i) => { const d = r.center.distanceTo(bc); if (d > far) { far = d; startIdx = i } })
  order.push(startIdx); used[startIdx] = true
  while (order.length < R.length) {
    const last = R[order[order.length - 1]].center
    let ni = -1, nd = Infinity
    R.forEach((r, i) => { if (!used[i]) { const d = r.center.distanceTo(last); if (d < nd) { nd = d; ni = i } } })
    if (ni < 0) break
    order.push(ni); used[ni] = true
  }

  // ── Calm, constant-speed choreography ─────────────────────────
  // For each room in order: come to its door → glide to the centre → slow
  // 360° reveal → return to the door → move on to the next room's door.
  // Durations scale with distance so the whole tour moves at one gentle pace.
  const SPEED = 1.25          // metres / second — a slow, calm glide
  const REVEAL_DUR = 6.5      // seconds for a full 360° room reveal
  const frames = []
  let cursor = null
  const travel = (target, lookAt, p0 = null) => {
    const from = p0 || cursor
    const dur = from ? Math.max(1.6, from.distanceTo(target) / SPEED) : 2.8
    frames.push({ kind: 'travel', p0, p1: target.clone(), dur, lookAt: (lookAt || target).clone() })
    cursor = target.clone()
  }

  const STEP = 2.0            // metres — a few steps into the hall after a room

  const first = R[order[0]]
  const entry0 = nearestDoor(first.center) || first.center.clone()
  const droneOut = entry0.clone().add(outward(entry0).multiplyScalar(2.6))
  droneOut.y = 3.6
  // Drone-in: descend from just outside the entry door, looking into the room.
  travel(entry0, first.center, droneOut)

  for (let k = 0; k < order.length; k++) {
    const room = R[order[k]]
    const door = nearestDoor(room.center) || room.center.clone()
    if (k > 0) travel(door, room.center)      // hallway → this room's door
    travel(room.center, room.center)          // door → room centre
    frames.push({ kind: 'reveal', pos: room.center.clone(), dur: REVEAL_DUR, name: room.name, dims: room.dims })
    cursor = room.center.clone()
    // Leave: glide OUT through the door (the centre→ahead line passes through
    // it) and take a few steps into the hall, so we don't jump straight to the
    // next room — it reads like a person stepping out and walking on.
    const outDir = new THREE.Vector3().subVectors(door, room.center).setY(0)
    if (outDir.lengthSq() < 1e-4) outDir.copy(outward(door))
    outDir.normalize()
    const ahead = door.clone().add(outDir.multiplyScalar(STEP))
    ahead.y = EYE
    travel(ahead, ahead)                      // centre → through door → into the hall
  }

  // Exit: from where we ended up, drift back outside.
  const exitOut = cursor.clone().add(outward(cursor).multiplyScalar(2.8))
  exitOut.y = 3.6
  travel(exitOut, bc)
  return frames
}

/* ─── Cinematic Tour Controller ────────────────────────────── */
function CinematicController({ tour, active, onComplete, onCaption }) {
  const { camera } = useThree()
  const idx = useRef(0)
  const t = useRef(0)
  const started = useRef(false)
  const p0 = useRef(new THREE.Vector3())
  const lookDir = useRef(new THREE.Vector3(0, 0, -1))
  const revealYaw = useRef(0)

  useEffect(() => {
    if (active && tour && tour.length > 0) {
      idx.current = 0
      t.current = 0
      started.current = false
      onCaption?.(null)
      camera.fov = 72          // wide interior FOV — space reads as spacious
      camera.updateProjectionMatrix()
    }
    return () => { camera.fov = 55; camera.updateProjectionMatrix() }
  }, [active, tour, onCaption, camera])

  const smooth = (x) => x * x * (3 - 2 * x)   // smoothstep ease-in-out

  useFrame((_, delta) => {
    if (!active || !tour || tour.length === 0) return
    const f = tour[idx.current]
    if (!f) { onComplete?.(); return }

    // Segment init.
    if (t.current === 0 && !started.current) {
      p0.current.copy(f.p0 || camera.position)
      if (f.p0) camera.position.copy(f.p0)
      if (f.kind === 'reveal') {
        camera.getWorldDirection(lookDir.current)
        revealYaw.current = Math.atan2(lookDir.current.x, lookDir.current.z)
        onCaption?.({ name: f.name, dims: f.dims })
      }
      started.current = true
    }

    t.current += delta / f.dur
    const e = smooth(Math.min(t.current, 1))

    if (f.kind === 'travel') {
      camera.position.lerpVectors(p0.current, f.p1, e)
      const desired = new THREE.Vector3().subVectors(f.lookAt, camera.position)
      if (desired.lengthSq() > 1e-4) {
        desired.normalize()
        lookDir.current.lerp(desired, 0.05).normalize()   // gentle, calm turns
      }
      camera.lookAt(new THREE.Vector3().addVectors(camera.position, lookDir.current))
    } else if (f.kind === 'reveal') {
      camera.position.copy(f.pos)
      const yaw = revealYaw.current + e * Math.PI * 2
      const dir = new THREE.Vector3(Math.sin(yaw), -0.12, Math.cos(yaw)) // gentle look-down surveys the room
      camera.lookAt(new THREE.Vector3().addVectors(f.pos, dir))
    }

    if (t.current >= 1) {
      idx.current += 1
      t.current = 0
      started.current = false
      if (idx.current >= tour.length) { onCaption?.(null); onComplete?.() }
    }
  })

  return null
}

/* ─── Main Canvas Wrapper ────────────────────────────────────── */
export default function SceneCanvas({ uploadData, detection, confirmedLayout, showcaseMode, setShowcaseMode }) {
  const [isWalkthrough, setIsWalkthrough] = useState(false)
  const [isCinematic, setIsCinematic] = useState(false)
  const [selectedSurface, setSelectedSurface] = useState(null)
  const [surfaceCustomizations, setSurfaceCustomizations] = useState({})
  const [cineCaption, setCineCaption] = useState(null)   // {name, dims} during reveals

  // World scale in metres-per-pixel. When the plan was measured (OCR read its
  // dimension labels), use the REAL scale so the house is life-sized — a 12'
  // room is genuinely 12', ceilings feel like ceilings, and walking at ~1.3 m/s
  // feels like a person. Falls back to 1px=1cm if unmeasured.
  const ftPerPx = detection?.stats?.scale_ft_per_px
              ?? detection?.measurements?.scale_ft_per_px ?? null
  const scale = ftPerPx ? ftPerPx * 0.3048 : 0.01   // ft→m

  const imgW = detection?.image_size?.width || 1000
  const imgH = detection?.image_size?.height || 1000
  const cx = imgW / 2
  const cy = imgH / 2

  const floor_w = imgW * scale
  const floor_h = imgH * scale

  // Reset FPP and materials state if layout changes or is reset
  useEffect(() => {
    setIsWalkthrough(false)
    setIsCinematic(false)
    setSelectedSurface(null)
    setSurfaceCustomizations({})
  }, [confirmedLayout])

  // Reset selection when showcase modes change
  useEffect(() => {
    setSelectedSurface(null)
    if (!isCinematic) setCineCaption(null)
  }, [showcaseMode, isWalkthrough, isCinematic])

  // Build the cinematic tour keyframes (door-aware path + room reveals)
  const cinematicTour = useMemo(
    () => buildCinematicTour(detection, confirmedLayout, cx, cy, scale),
    [detection, confirmedLayout, cx, cy, scale]
  )

  function handleCustomizationChange(customization) {
    if (!selectedSurface) return
    const targetId = selectedSurface.type === 'floor' ? 'floor' : selectedSurface.id
    setSurfaceCustomizations(prev => ({
      ...prev,
      [targetId]: customization
    }))
  }

  function handleCustomizationReset() {
    if (!selectedSurface) return
    const targetId = selectedSurface.type === 'floor' ? 'floor' : selectedSurface.id
    setSurfaceCustomizations(prev => {
      const next = { ...prev }
      delete next[targetId]
      return next
    })
  }

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%', overflow: 'hidden' }}>
      
      {/* Regular HUD overlay */}
      {confirmedLayout && !showcaseMode && (
        <div style={{
          position: 'absolute',
          top: 16,
          left: 16,
          zIndex: 10,
          background: 'rgba(10, 12, 20, 0.95)',
          border: '1px solid rgba(255, 255, 255, 0.08)',
          borderRadius: 8,
          padding: '12px 16px',
          color: '#ffffff',
          display: 'flex',
          flexDirection: 'column',
          gap: 10,
          boxShadow: '0 4px 20px rgba(0,0,0,0.5)',
          fontFamily: 'Inter, sans-serif'
        }}>
          <div style={{ fontWeight: 600, fontSize: 13, color: '#f3f4f6', display: 'flex', alignItems: 'center', gap: 6 }}>
            <span>🧊</span> 3D Reconstructed Space
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={() => setIsWalkthrough(false)}
              style={{
                background: !isWalkthrough ? '#6378ff' : '#1c2235',
                color: '#ffffff',
                border: 'none',
                padding: '6px 12px',
                borderRadius: 4,
                cursor: 'pointer',
                fontWeight: 600,
                fontSize: 11,
                transition: 'background 0.2s'
              }}
            >
              🛸 Orbit View
            </button>
            <button
              onClick={() => setIsWalkthrough(true)}
              style={{
                background: isWalkthrough ? '#3dd9c6' : '#1c2235',
                color: isWalkthrough ? '#0a0c14' : '#ffffff',
                border: 'none',
                padding: '6px 12px',
                borderRadius: 4,
                cursor: 'pointer',
                fontWeight: 600,
                fontSize: 11,
                transition: 'background 0.2s'
              }}
            >
              🚶 First-Person walk
            </button>
          </div>
          <div style={{ fontSize: 10, color: 'var(--text-muted)', lineHeight: '1.4' }}>
            {!isWalkthrough 
              ? 'Click any wall/floor to customize PBR surface · Orbit drag'
              : 'Click viewport to capture mouse · WASD to walk · Move mouse to look · Esc to exit'
            }
          </div>
        </div>
      )}

      {/* Showcase HUD Overlay */}
      {confirmedLayout && showcaseMode && (
        <div className="showcase-hud">
          <span className="showcase-title-badge">DREAMSPACE PRESENTATION</span>
          <button
            className={`hud-btn ${isWalkthrough ? 'active' : ''}`}
            onClick={() => {
              setIsWalkthrough(!isWalkthrough)
              setIsCinematic(false)
            }}
          >
            🚶 Walkthrough
          </button>
          {cinematicTour.length > 0 && (
            <button
              className={`hud-btn ${isCinematic ? 'active' : ''}`}
              onClick={() => {
                setIsCinematic(!isCinematic)
                setIsWalkthrough(false)
              }}
            >
              🎬 Cinematic Tour
            </button>
          )}
          <button
            className="hud-btn exit-btn"
            onClick={() => {
              setIsCinematic(false)
              setIsWalkthrough(false)
              setShowcaseMode(false)
            }}
          >
            Exit Showcase
          </button>
        </div>
      )}

      {/* Cinematic lower-third caption (room name + real dimensions) */}
      {isCinematic && cineCaption && (
        <div className="cine-caption">
          <div className="cine-room-name">{cineCaption.name}</div>
          {cineCaption.dims && <div className="cine-room-dims">{cineCaption.dims}</div>}
        </div>
      )}

      {/* Material/Texture Selection Sidebar */}
      {selectedSurface && !isWalkthrough && !isCinematic && !showcaseMode && (
        <MaterialSelector
          selectedSurface={selectedSurface}
          currentCustomization={surfaceCustomizations[selectedSurface.type === 'floor' ? 'floor' : selectedSurface.id]}
          onChange={handleCustomizationChange}
          onReset={handleCustomizationReset}
          onClose={() => setSelectedSurface(null)}
        />
      )}

      {/* 3D Scene */}
      <Canvas
        shadows={{ type: THREE.PCFShadowMap }}
        camera={{ position: [0, 8, 8], fov: 55 }}
        gl={{ antialias: true, toneMapping: THREE.ACESFilmicToneMapping }}
        style={{ background: 'transparent' }}
      >
        {/* Lighting */}
        <ambientLight intensity={isWalkthrough || isCinematic ? 0.65 : 0.4} />
        <directionalLight
          castShadow
          position={[10, 18, 12]}
          intensity={1.3}
          shadow-mapSize={[2048, 2048]}
          shadow-bias={-0.0001}
          color="#ffffff"
        />
        <pointLight position={[-6, 4, -6]} intensity={0.4} color="#6378ff" />
        <pointLight position={[6, 3, 6]} intensity={0.3} color="#3dd9c6" />

        {/* Environment / Fog */}
        <fog attach="fog" args={['#0a0c14', 18, 55]} />

        {/* Render building or placeholder */}
        {confirmedLayout ? (
          <group>
            {/* Extruded Walls */}
            <Walls3D
              walls={confirmedLayout.walls}
              openings={confirmedLayout.openings}
              cx={cx}
              cy={cy}
              scale={scale}
              onSelectWall={setSelectedSurface ? (id) => setSelectedSurface({ type: 'wall', id }) : null}
              selectedSurface={selectedSurface}
              surfaceCustomizations={surfaceCustomizations}
            />

            {/* Glossy Floor */}
            <mesh 
              rotation={[-Math.PI / 2, 0, 0]} 
              position={[0, -0.005, 0]} 
              receiveShadow
              onClick={(e) => {
                if (isWalkthrough || isCinematic || showcaseMode) return
                e.stopPropagation()
                setSelectedSurface({ type: 'floor' })
              }}
            >
              <planeGeometry args={[floor_w, floor_h]} />
              <meshStandardMaterial
                color={surfaceCustomizations['floor']?.color || "#141824"}
                roughness={surfaceCustomizations['floor']?.roughness !== undefined ? surfaceCustomizations['floor']?.roughness : 0.22}
                metalness={surfaceCustomizations['floor']?.metalness !== undefined ? surfaceCustomizations['floor']?.metalness : 0.4}
                clearcoat={surfaceCustomizations['floor']?.clearcoat !== undefined ? surfaceCustomizations['floor']?.clearcoat : 0}
              />
            </mesh>

            {/* Glowing selection highlight for Floor */}
            {selectedSurface?.type === 'floor' && !showcaseMode && (
              <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.002, 0]}>
                <planeGeometry args={[floor_w + 0.01, floor_h + 0.01]} />
                <meshBasicMaterial color="#3dd9c6" wireframe opacity={0.25} transparent />
              </mesh>
            )}

            {/* Soft border indicator */}
            {!isWalkthrough && !isCinematic && (
              <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.001, 0]}>
                <planeGeometry args={[floor_w + 0.1, floor_h + 0.1]} />
                <meshBasicMaterial color="#6378ff" wireframe opacity={0.15} transparent />
              </mesh>
            )}
          </group>
        ) : (
          <group>
            <PlaceholderBuilding />
            <GroundGlow />
            <SceneLabel
              text={
                uploadData
                  ? 'Confirm layout in 2D Editor to view 3D model'
                  : 'Upload a floor plan to begin'
              }
            />
          </group>
        )}

        {/* Scene floor grid (hidden in walkthrough mode for immersion) */}
        {!isWalkthrough && !isCinematic && (
          <Grid
            position={[0, 0, 0]}
            args={[28, 28]}
            cellSize={1}
            cellThickness={0.4}
            cellColor="#1c2235"
            sectionSize={4}
            sectionThickness={0.8}
            sectionColor="#252a45"
            fadeDistance={22}
            fadeStrength={1}
            infiniteGrid
          />
        )}

        {/* Camera controllers */}
        {confirmedLayout && isWalkthrough && (
          <PlayerController
            walls={confirmedLayout.walls}
            openings={confirmedLayout.openings}
            cx={cx}
            cy={cy}
            scale={scale}
            rooms={detection?.rooms}
            active={isWalkthrough}
          />
        )}

        {confirmedLayout && isCinematic && (
          <CinematicController
            tour={cinematicTour}
            active={isCinematic}
            onComplete={() => setIsCinematic(false)}
            onCaption={setCineCaption}
          />
        )}

        {!isWalkthrough && !isCinematic && (
          <OrbitControls
            makeDefault
            minDistance={2}
            maxDistance={22}
            maxPolarAngle={Math.PI / 2.05}
            enablePan={true}
            target={[0, 0.8, 0]}
          />
        )}
      </Canvas>
    </div>
  )
}
