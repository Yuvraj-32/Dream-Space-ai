/**
 * typePresets.js — sensible defaults for an uploaded texture.
 *
 * A user uploading a photo of a laminate has no reason to reason about metres
 * per tile or roughness multipliers. They know *what kind of thing* it is, so
 * we ask only that and derive the rest:
 *
 *   tile       real-world size the image is assumed to cover, in metres.
 *              Drives repeat exactly like a built-in scan's published size.
 *   roughness  multiplier — with no roughness map it is used directly, so it
 *              is what makes tile glossy and concrete flat.
 *   metalness  0 for every architectural surface here.
 *   tint       how Surface Color may act (see tint.js). Paint is fully
 *              tintable; wood and stone are not, so an uploaded oak photo is
 *              never washed out by a leftover colour.
 *   category   which group the material appears under in the picker.
 *
 * Uploads carry an albedo only. We deliberately do NOT synthesise normal or
 * roughness maps from it — a fabricated normal map is worse than none.
 */
import { TINT_FULL, TINT_SUBTLE, TINT_NONE } from './tint'

export const MATERIAL_TYPES = [
  {
    id: 'paint',
    label: 'Wall Paint',
    hint: 'Flat colour · tintable',
    tile: [2.0, 2.0],
    roughness: 0.9,
    metalness: 0.02,
    tint: TINT_FULL,
    category: 'paint',
  },
  {
    id: 'wallpaper',
    label: 'Wallpaper',
    hint: 'Repeating print · pattern preserved',
    // Wallpaper is sold in ~0.5–0.7 m repeats; keeping the tile near that
    // makes an uploaded pattern read at a believable size.
    tile: [0.7, 0.7],
    roughness: 0.9,
    metalness: 0.0,
    tint: TINT_SUBTLE,
    category: 'wallpaper',
  },
  {
    id: 'wood',
    label: 'Wood / Laminate',
    hint: 'Natural colour kept · medium sheen',
    tile: [1.2, 1.2],
    roughness: 0.55,
    metalness: 0.0,
    tint: TINT_NONE,
    category: 'wood',
  },
  {
    id: 'stone',
    label: 'Marble / Stone',
    hint: 'Veins preserved · low repeat, natural gloss',
    // Large tile = few repeats, so veining reads as one slab rather than a
    // busy grid.
    tile: [1.8, 1.8],
    roughness: 0.3,
    metalness: 0.0,
    tint: TINT_NONE,
    category: 'stone',
  },
  {
    id: 'tile',
    label: 'Tile',
    hint: 'Glazed sheen · even repeat',
    tile: [1.2, 1.2],
    roughness: 0.25,
    metalness: 0.0,
    tint: TINT_SUBTLE,
    category: 'stone',
  },
  {
    id: 'concrete',
    label: 'Concrete',
    hint: 'Matte · lightly tintable',
    tile: [2.0, 2.0],
    roughness: 0.95,
    metalness: 0.0,
    tint: TINT_SUBTLE,
    category: 'paint',
  },
  {
    id: 'fabric',
    label: 'Fabric',
    hint: 'Fine weave · matte',
    tile: [0.5, 0.5],
    roughness: 1.0,
    metalness: 0.0,
    tint: TINT_SUBTLE,
    category: 'wallpaper',
  },
  {
    id: 'custom',
    label: 'Custom',
    hint: 'Neutral defaults · adjust scale below',
    tile: [1.0, 1.0],
    roughness: 0.7,
    metalness: 0.0,
    tint: TINT_SUBTLE,
    category: 'wallpaper',
  },
]

export const MATERIAL_TYPES_BY_ID = Object.fromEntries(MATERIAL_TYPES.map((t) => [t.id, t]))

export const DEFAULT_TYPE_ID = 'custom'

export function getTypePreset(id) {
  return MATERIAL_TYPES_BY_ID[id] || MATERIAL_TYPES_BY_ID[DEFAULT_TYPE_ID]
}
