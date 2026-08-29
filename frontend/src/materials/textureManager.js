/**
 * textureManager.js — PBR texture loading + safe per-repeat caching.
 *
 * ── The problem this solves ────────────────────────────────────────────
 * In Three.js `repeat` is state on the Texture object, not on the mesh or
 * the material. So a single Texture shared by a 1.2 m wall and a 6 m wall
 * cannot show a correct tile count on both: whichever wall writes
 * `texture.repeat` last wins, and the other silently re-scales.
 *
 * ── The design ─────────────────────────────────────────────────────────
 * Two cache layers with one hard invariant between them:
 *
 *   1. MASTER (one per URL) — holds the decoded image. It is NEVER rendered
 *      and its `repeat` is NEVER read or written. It exists only to be cloned.
 *
 *   2. VARIANT (one per url + repeatX + repeatY) — a `master.clone()`.
 *      `Texture.clone()` shares the underlying `THREE.Source`, so all
 *      variants of a URL reference the same decoded image and the same GPU
 *      upload (WebGLTextures keys its upload cache by `source.uuid`), while
 *      each variant owns its own `repeat`/`offset`/`matrix`.
 *
 * INVARIANT: a variant's `repeat` is written exactly once, at creation, from
 * the same numbers that form its cache key. Nothing mutates a texture after
 * it is handed out. A 2× wall and an 8× wall therefore resolve to two
 * different variants and can never overwrite each other's scale.
 *
 * Materials are cached the same way, keyed by their full visual config
 * (material id + tint + repeat), so they are shared only between surfaces
 * that must look identical, and are likewise never mutated in place.
 */
import * as THREE from 'three'

const _loader = new THREE.TextureLoader()

/** url -> { texture: THREE.Texture (master), status, promise } */
const _masters = new Map()
/** `${url}|${rx}|${ry}` -> THREE.Texture (clone, owns its repeat) */
const _variants = new Map()
/** material cache key -> THREE.MeshStandardMaterial */
const _materials = new Map()

let _anisotropy = 1
const _listeners = new Set()
let _version = 0

/* ── change notification (lets React re-render when maps finish loading) ── */
/**
 * A material built before its images arrived has null maps. Rather than throw
 * it away and rely on every consumer re-rendering at the right moment, fill the
 * maps in on the material that is already on the mesh. Surfaces therefore
 * upgrade from flat to textured whether or not React re-renders.
 *
 * This does not weaken the texture invariant: the *textures* are still never
 * mutated — we only attach the correct pre-configured variant to a material
 * whose cache key already fixed that exact repeat/rotation.
 */
function _refreshMaterials() {
  _materials.forEach((mat) => {
    const src = mat.userData.__src
    if (!src) return
    let changed = false
    const attach = (slot, url) => {
      if (!url || mat[slot]) return
      const tex = getTextureVariant(url, src.rx, src.ry, src.rot)
      if (tex) { mat[slot] = tex; changed = true }
    }
    attach('map', src.maps.color)
    attach('normalMap', src.maps.normal)
    attach('roughnessMap', src.maps.roughness)
    if (changed) {
      if (mat.normalMap && src.normalScale != null) {
        mat.normalScale = new THREE.Vector2(src.normalScale, src.normalScale)
      }
      mat.needsUpdate = true
    }
  })
}

function _bump() {
  _version += 1
  _refreshMaterials()
  _listeners.forEach((fn) => fn())
}

export function subscribe(fn) {
  _listeners.add(fn)
  return () => _listeners.delete(fn)
}

export function getVersion() {
  return _version
}

/**
 * Anisotropic filtering keeps textures sharp on walls seen at grazing angles
 * (the common case in a first-person walkthrough). Applied to every variant,
 * existing and future.
 */
export function setAnisotropy(value) {
  const next = Math.max(1, Math.min(16, value || 1))
  if (next === _anisotropy) return
  _anisotropy = next
  _masters.forEach(({ texture }) => { texture.anisotropy = next })
  _variants.forEach((t) => { t.anisotropy = next; t.needsUpdate = true })
  _bump()
}

/* ── master loading ─────────────────────────────────────────────────── */
function _loadMaster(url, colorSpace) {
  const hit = _masters.get(url)
  if (hit) return hit.promise

  const entry = { texture: null, status: 'loading', promise: null }
  entry.promise = new Promise((resolve) => {
    _loader.load(
      url,
      (tex) => {
        tex.colorSpace = colorSpace
        tex.wrapS = THREE.RepeatWrapping
        tex.wrapT = THREE.RepeatWrapping
        tex.anisotropy = _anisotropy
        entry.texture = tex
        entry.status = 'ready'
        _bump()
        resolve(tex)
      },
      undefined,
      () => {
        // Missing asset is not fatal: the material falls back to its scalar
        // values (see registry `roughness`/`metalness`) and the app keeps
        // working. Surfaced once, not per frame.
        console.warn(`[textures] could not load ${url} — falling back to a flat material.`)
        entry.status = 'error'
        _bump()
        resolve(null)
      }
    )
  })
  _masters.set(url, entry)
  return entry.promise
}

function _isReady(url) {
  const e = _masters.get(url)
  return !!(e && e.status === 'ready' && e.texture && e.texture.image)
}

/* ── variants ───────────────────────────────────────────────────────── */
// Quantised so near-identical wall sizes share a variant, while genuinely
// different sizes (2× vs 8×) always land on different keys.
const _q = (n) => Math.round(n * 100) / 100

/**
 * A texture configured for exactly this repeat and rotation. Returns null until
 * the image has loaded — callers render a scalar-only material meanwhile.
 *
 * `rotation` is part of the cache key for the same reason `repeat` is: it is
 * state on the Texture object, so two surfaces wanting different rotations must
 * get different Texture instances.
 */
export function getTextureVariant(url, repeatX, repeatY, rotationDeg = 0) {
  if (!url || !_isReady(url)) return null

  const rx = _q(repeatX)
  const ry = _q(repeatY)
  const rot = ((Math.round(rotationDeg) % 360) + 360) % 360
  const key = `${url}|${rx}|${ry}|${rot}`

  const cached = _variants.get(key)
  if (cached) return cached

  const master = _masters.get(url).texture
  // clone() shares `source` (one decode, one GPU upload) but gives this
  // variant its own repeat/offset/rotation/matrix.
  const variant = master.clone()
  variant.wrapS = THREE.RepeatWrapping
  variant.wrapT = THREE.RepeatWrapping
  variant.anisotropy = _anisotropy
  variant.colorSpace = master.colorSpace
  variant.repeat.set(rx, ry)   // written once, matches the key, never touched again
  if (rot) {
    // Rotate about the middle of the tile so the pattern stays centred.
    variant.center.set(0.5, 0.5)
    variant.rotation = (rot * Math.PI) / 180
  }
  variant.needsUpdate = true

  _variants.set(key, variant)
  return variant
}

/* ── materials ──────────────────────────────────────────────────────── */
/**
 * Kick off loading for one registry entry. Idempotent; safe to call on every
 * render or from an effect.
 */
export function preloadMaterial(def) {
  if (!def || !def.maps) return
  const { color, normal, roughness } = def.maps
  if (color) _loadMaster(color, THREE.SRGBColorSpace)
  // Normal and roughness carry data, not colour — they must stay linear.
  if (normal) _loadMaster(normal, THREE.NoColorSpace)
  if (roughness) _loadMaster(roughness, THREE.NoColorSpace)
}

/**
 * Resolve a MeshStandardMaterial for one face of one wall segment.
 *
 * @param def       registry entry (see registry.js)
 * @param tintHex   user-chosen Surface Color, already resolved by the caller
 * @param repeatX   tiles across this face's width  (metres / tile metres)
 * @param repeatY   tiles across this face's height
 */
export function getWallMaterial(def, tintHex, repeatX, repeatY, rotationDeg = 0) {
  const rx = _q(repeatX)
  const ry = _q(repeatY)
  const rot = ((Math.round(rotationDeg) % 360) + 360) % 360
  // `rev` lets an edited material (type/scale/rotation changed) miss the cache
  // instead of serving the stale material built from its previous settings.
  const key = `${def.id}|${def.rev ?? 0}|${tintHex}|${rx}|${ry}|${rot}`

  const cached = _materials.get(key)
  if (cached) return cached

  const maps = def.maps || {}
  const colorMap = getTextureVariant(maps.color, rx, ry, rot)
  const normalMap = getTextureVariant(maps.normal, rx, ry, rot)
  const roughnessMap = getTextureVariant(maps.roughness, rx, ry, rot)

  const mat = new THREE.MeshStandardMaterial({
    color: new THREE.Color(tintHex),
    // With a roughnessMap present three multiplies map × scalar, so the
    // scalar acts as a gloss trim (0.35 = polished, 1.0 = as scanned).
    roughness: def.roughness,
    metalness: def.metalness,
    map: colorMap || null,
    normalMap: normalMap || null,
    roughnessMap: roughnessMap || null,
  })
  if (normalMap) {
    const s = def.normalScale ?? 1
    mat.normalScale = new THREE.Vector2(s, s)
  }

  // Everything _refreshMaterials needs to fill in maps that were not ready yet.
  mat.userData.__src = {
    maps, rx, ry, rot, normalScale: def.normalScale ?? 1,
  }

  _materials.set(key, mat)
  return mat
}

/* ── introspection (used by the dev/verification checks) ─────────────── */
export function __debugState() {
  return {
    masters: [..._masters.entries()].map(([url, e]) => ({ url, status: e.status })),
    variants: [..._variants.entries()].map(([key, t]) => ({
      key,
      repeat: [t.repeat.x, t.repeat.y],
      sharedSource: t.source.uuid,
    })),
    materials: [..._materials.keys()],
    version: _version,
  }
}

export function disposeAll() {
  _variants.forEach((t) => t.dispose())
  _masters.forEach((e) => e.texture && e.texture.dispose())
  _materials.forEach((m) => m.dispose())
  _variants.clear()
  _masters.clear()
  _materials.clear()
}
