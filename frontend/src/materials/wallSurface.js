/**
 * wallSurface.js — turns a wall box's real-world dimensions into correctly
 * tiled materials, one per visible face.
 *
 * Why per-face: a wall segment is a BoxGeometry [length, height, thickness].
 * Its six faces have three different physical shapes, and BoxGeometry gives
 * each face the full 0..1 UV square. A single material (one repeat) would
 * therefore fit the texture to the *front* face and smear that same tiling
 * across the ~0.15 m thickness faces, stretching them by the wall's whole
 * aspect ratio. Supplying a 6-material array — the standard Three.js way to
 * texture a box, no geometry changes — gives every face its own repeat:
 *
 *   index 0,1  ±X  the wall's cut ends      (thickness × height)
 *   index 2,3  ±Y  top and bottom edges     (length × thickness)
 *   index 4,5  ±Z  the two big room faces   (length × height)
 *
 * Repeat is always (metres along that axis ÷ the texture's real-world tile
 * size), so a brick keeps its true size on every face of every wall, and a
 * rotated wall is unaffected: UVs are local to the box, so the texture turns
 * with the geometry and `u` always runs along the wall.
 */
import { useSyncExternalStore } from 'react'

import { getMaterialDef, resolveTint } from './registry'
import {
  getWallMaterial,
  subscribe as subscribeTextures,
  getVersion as getTextureVersion,
  preloadMaterial,
} from './textureManager'
import {
  subscribe as subscribeCustom,
  getVersion as getCustomVersion,
} from './customStore'

/* One snapshot covering both stores: texture loading progress and the user's
   material library (which hydrates asynchronously and can be edited). */
function subscribeAll(cb) {
  const a = subscribeTextures(cb)
  const b = subscribeCustom(cb)
  return () => { a(); b() }
}

function snapshot() {
  return getTextureVersion() * 1e6 + getCustomVersion()
}

/**
 * Re-renders the caller when texture loading or the custom library changes, so
 * surfaces upgrade from their flat fallback to the full material as maps
 * arrive, and pick up edits to uploaded materials.
 */
export function useMaterialVersion() {
  return useSyncExternalStore(subscribeAll, snapshot, snapshot)
}

/** Start fetching the maps for whichever materials are actually in use. */
export function preloadMaterials(materialIds) {
  new Set(materialIds).forEach((id) => preloadMaterial(getMaterialDef(id)))
}

/**
 * The tile size actually used, after the material's user `scale` multiplier.
 * Scale > 1 makes the pattern physically larger (fewer repeats).
 */
function effectiveTile(def) {
  const [tx, ty] = def.tile || [1, 1]
  const s = def.scale && def.scale > 0 ? def.scale : 1
  return [Math.max(tx * s, 1e-3), Math.max(ty * s, 1e-3)]
}

/**
 * Repeat for one rectangular face, honouring the material's rotation.
 *
 * At 90°/270° the texture's own axes are turned a quarter turn, so the repeat
 * components swap which surface dimension they cover — otherwise a rotated
 * texture would stretch by the face's aspect ratio.
 */
function faceRepeat(def, wMetres, hMetres) {
  const [tx, ty] = effectiveTile(def)
  const rot = ((Math.round(def.rotation || 0) % 360) + 360) % 360
  return rot === 90 || rot === 270
    ? [hMetres / tx, wMetres / ty]
    : [wMetres / tx, hMetres / ty]
}

/**
 * Six materials for one wall box, in BoxGeometry face order.
 *
 * @param materialId registry id ('brick', 'hardwood', 'custom:…', …)
 * @param userColor  the Surface Color the user picked (may be ignored,
 *                   depending on the material's tint mode)
 * @param length     segment length in metres (X)
 * @param height     segment height in metres (Y)
 * @param thickness  wall thickness in metres (Z)
 */
export function wallFaceMaterials(materialId, userColor, length, height, thickness) {
  const def = getMaterialDef(materialId)
  const tint = resolveTint(def, userColor)
  const rot = def.rotation || 0

  // Guard against zero-size faces producing a 0 repeat (degenerate UVs).
  const L = Math.max(length, 1e-3)
  const H = Math.max(height, 1e-3)
  const T = Math.max(thickness, 1e-3)

  const ends = getWallMaterial(def, tint, ...faceRepeat(def, T, H), rot)   // ±X
  const caps = getWallMaterial(def, tint, ...faceRepeat(def, L, T), rot)   // ±Y
  const faces = getWallMaterial(def, tint, ...faceRepeat(def, L, H), rot)  // ±Z

  return [ends, ends, caps, caps, faces, faces]
}

/**
 * One material for a flat rectangular surface — the floor today, a ceiling or
 * a worktop later. Deliberately the same registry, texture manager, cache and
 * repeat rule as the walls; only the face count differs.
 *
 * @param materialId registry id
 * @param userColor  chosen Surface Color (subject to the tint mode)
 * @param width      surface width in metres
 * @param depth      surface depth in metres
 */
export function surfaceMaterial(materialId, userColor, width, depth) {
  const def = getMaterialDef(materialId)
  const tint = resolveTint(def, userColor)
  const W = Math.max(width, 1e-3)
  const D = Math.max(depth, 1e-3)
  return getWallMaterial(def, tint, ...faceRepeat(def, W, D), def.rotation || 0)
}
