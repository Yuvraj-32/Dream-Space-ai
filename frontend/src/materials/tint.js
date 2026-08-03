/**
 * tint.js — how a user-chosen Surface Color is allowed to affect a material.
 *
 * Extracted from registry.js so that the custom-material store and the type
 * presets can share it without importing the registry (which would create a
 * cycle: registry → customStore → typePresets → registry).
 */

export const TINT_FULL = 'full'      // paint/plaster: the colour is the point
export const TINT_SUBTLE = 'subtle'  // pigmented surfaces: nudge, keep texture
export const TINT_NONE = 'none'      // natural scans: colour would destroy them

/** Strength of the colour blend for TINT_SUBTLE materials (0 = ignore colour). */
export const SUBTLE_TINT_STRENGTH = 0.35

export function blendHex(fromHex, toHex, t) {
  const p = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16))
  const [r1, g1, b1] = p(fromHex)
  const [r2, g2, b2] = p(toHex)
  const mix = (a, b) => Math.round(a + (b - a) * t).toString(16).padStart(2, '0')
  return `#${mix(r1, r2)}${mix(g1, g2)}${mix(b1, b2)}`
}

/**
 * Resolve the colour actually handed to the material, honouring the tint mode
 * so a strong user colour can never wash out a natural scan.
 */
export function resolveTint(def, userColor) {
  if (def.tint === TINT_NONE) return '#ffffff'
  if (!userColor) return def.defaultColor || '#ffffff'
  if (def.tint === TINT_SUBTLE) return blendHex('#ffffff', userColor, SUBTLE_TINT_STRENGTH)
  return userColor
}
