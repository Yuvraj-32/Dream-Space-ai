/**
 * registry.js — the material library.
 *
 * Phase A: the original six presets, now backed by real CC0 PBR scans from
 * ambientCG (see public/textures/LICENSE.md). Ids are unchanged from the
 * previous MATERIAL_PRESETS so existing saved customizations keep working.
 *
 * Each entry declares:
 *   maps        Albedo / NormalGL / Roughness URLs. Only maps that genuinely
 *               ship with the scan are listed — a missing roughness map means
 *               a scalar value is used instead, never a fabricated map.
 *               No displacement in this phase.
 *   tile        The real-world size of the texture in metres, [width, height],
 *               taken from the scan's published dimensions. Tiling is derived
 *               from this and the surface's true size, so a brick is the same
 *               physical size on a 1 m wall and a 9 m wall.
 *   roughness   Multiplied over roughnessMap when one exists (so < 1 = glossier
 *               than scanned); used directly as a scalar when it doesn't.
 *   tint        How Surface Color is allowed to affect the material:
 *                 'full'   — paint/plaster: colour is the point of the material
 *                 'subtle' — pigmented surfaces: colour nudged, texture intact
 *                 'none'   — natural wood/stone/brick: colour would destroy the
 *                            scan, so the swatch is disabled in the UI
 */

import {
  TINT_FULL,
  TINT_SUBTLE,
  TINT_NONE,
  SUBTLE_TINT_STRENGTH,
  resolveTint,
} from './tint'
import { getCustomMaterialDef } from './customStore'

// Re-exported so existing importers of registry.js keep working unchanged.
export { TINT_FULL, TINT_SUBTLE, TINT_NONE, SUBTLE_TINT_STRENGTH, resolveTint }

// Vite serves `public/` from BASE_URL, so this resolves correctly both in dev
// and under a deployed sub-path.
const BASE = import.meta.env.BASE_URL || '/'
const T = (dir) => ({
  color: `${BASE}textures/${dir}/color.jpg`,
  normal: `${BASE}textures/${dir}/normal.jpg`,
  roughness: `${BASE}textures/${dir}/roughness.jpg`,
})

export const CATEGORIES = [
  { id: 'paint', label: 'Paint & Plaster' },
  { id: 'wood', label: 'Wood' },
  { id: 'stone', label: 'Stone & Tile' },
  { id: 'brick', label: 'Brick' },
  { id: 'wallpaper', label: 'Wallpaper & Natural' },
]

export const MATERIALS = [
  {
    id: 'default',
    label: 'Default Paint',
    category: 'paint',
    // Flat paint has no meaningful surface relief at room scale — a scalar
    // material is the honest representation, not a scanned map.
    maps: null,
    tile: [1, 1],
    roughness: 0.85,
    metalness: 0.02,
    tint: TINT_FULL,
    defaultColor: '#f0f2f5',
    note: 'Clean matte paint · tintable',
  },
  {
    // Not offered in the picker — this is what a floor renders as before the
    // user chooses anything, so the scene's default look is unchanged while
    // still going through the normal material pipeline.
    id: 'floor_default',
    label: 'Default Floor',
    category: 'paint',
    hidden: true,
    maps: null,
    tile: [1, 1],
    roughness: 0.22,
    metalness: 0.4,
    tint: TINT_FULL,
    defaultColor: '#141824',
    note: 'Default floor finish',
  },
  {
    id: 'plaster',
    label: 'Matte Plaster',
    category: 'paint',
    maps: T('plaster_matte'),
    source: 'ambientCG Plaster001 (CC0)',
    tile: [2.0, 2.0],
    roughness: 1.0,
    metalness: 0.0,
    normalScale: 0.7,
    tint: TINT_FULL,
    defaultColor: '#eceae5',
    note: 'Troweled plaster relief · tintable',
  },
  {
    id: 'hardwood',
    label: 'Polished Wood',
    category: 'wood',
    maps: T('wood_polished'),
    source: 'ambientCG WoodFloor043 (CC0)',
    // Published scan size: 130 × 65 cm. Non-square, so plank width and grain
    // stay in proportion instead of being stretched to a square tile.
    tile: [1.3, 0.65],
    roughness: 0.5,      // polished: glossier than the scanned matte planks
    metalness: 0.0,
    normalScale: 0.6,
    tint: TINT_NONE,
    note: 'Natural grain — colour tint disabled',
  },
  {
    id: 'tile',
    label: 'Glossy Tile',
    category: 'stone',
    maps: T('tile_glossy'),
    source: 'ambientCG Tiles074 (CC0)',
    // 210 cm scan across 6 tiles ≈ 35 cm tiles.
    tile: [2.1, 2.1],
    roughness: 0.35,     // glossy glaze
    metalness: 0.0,
    normalScale: 0.5,
    tint: TINT_NONE,
    note: 'Marble tile & grout — colour tint disabled',
  },
  {
    id: 'concrete',
    label: 'Raw Concrete',
    category: 'stone',
    maps: T('concrete_raw'),
    source: 'ambientCG Concrete034 (CC0)',
    tile: [1.1, 0.55],
    roughness: 1.0,
    metalness: 0.0,
    normalScale: 0.8,
    tint: TINT_SUBTLE,
    defaultColor: '#cfcfcb',
    note: 'Cast concrete variation · lightly tintable',
  },
  {
    id: 'brick',
    label: 'Exposed Brick',
    category: 'brick',
    maps: T('brick_exposed'),
    source: 'ambientCG Bricks086 (CC0)',
    // Published scan size: 260 × 130 cm — keeps courses at true brick height
    // (~14 courses per 130 cm ≈ a real 65 mm brick + 10 mm joint).
    tile: [2.6, 1.3],
    roughness: 1.0,
    metalness: 0.0,
    normalScale: 1.0,
    tint: TINT_NONE,
    note: 'Brick & mortar relief — colour tint disabled',
  },

  /* ══ Phase B ═══════════════════════════════════════════════════════ */

  // ── Paint & plaster ──
  {
    id: 'limewash',
    label: 'Limewash',
    category: 'paint',
    maps: T('limewash'),
    source: 'ambientCG PaintedPlaster017 (CC0)',
    tile: [2.0, 2.0],
    roughness: 1.0,
    metalness: 0.0,
    normalScale: 0.6,
    tint: TINT_FULL,
    defaultColor: '#efe9df',
    note: 'Soft mottled lime finish · tintable',
  },
  {
    id: 'venetian_plaster',
    label: 'Venetian Plaster',
    category: 'paint',
    maps: T('venetian_plaster'),
    source: 'ambientCG Plaster006 (CC0)',
    tile: [2.0, 2.0],
    roughness: 0.55,     // burnished sheen
    metalness: 0.0,
    normalScale: 0.4,
    tint: TINT_FULL,
    defaultColor: '#e8e0d4',
    note: 'Burnished polished plaster · tintable',
  },
  {
    id: 'stucco',
    label: 'Stucco',
    category: 'paint',
    maps: T('stucco'),
    source: 'ambientCG Plaster002 (CC0)',
    tile: [2.0, 2.0],
    roughness: 1.0,
    metalness: 0.0,
    normalScale: 1.0,
    tint: TINT_FULL,
    defaultColor: '#eceae6',
    note: 'Coarse render texture · tintable',
  },
  {
    id: 'microcement',
    label: 'Microcement',
    category: 'paint',
    maps: T('microcement'),
    source: 'ambientCG Concrete016 (CC0)',
    tile: [2.0, 2.0],
    roughness: 0.85,
    metalness: 0.0,
    normalScale: 0.5,
    tint: TINT_SUBTLE,
    defaultColor: '#d8d6d2',
    note: 'Seamless cement skim · lightly tintable',
  },

  // ── Wood ──
  {
    id: 'wood_light_oak',
    label: 'Light Oak',
    category: 'wood',
    maps: T('wood_light_oak'),
    source: 'ambientCG WoodFloor062 (CC0)',
    tile: [1.2, 1.2],
    roughness: 0.6,
    metalness: 0.0,
    normalScale: 0.6,
    tint: TINT_NONE,
    note: 'Pale golden oak planks — colour tint disabled',
  },
  {
    id: 'wood_walnut',
    label: 'Walnut',
    category: 'wood',
    maps: T('wood_walnut'),
    source: 'ambientCG Wood027 (CC0)',
    tile: [1.0, 1.0],
    roughness: 0.55,
    metalness: 0.0,
    normalScale: 0.6,
    tint: TINT_NONE,
    note: 'Rich mid-brown grain — colour tint disabled',
  },
  {
    id: 'wood_dark_walnut',
    label: 'Dark Walnut',
    category: 'wood',
    maps: T('wood_dark_walnut'),
    source: 'ambientCG Wood051 (CC0)',
    // Published scan size: 80 × 80 cm.
    tile: [0.8, 0.8],
    roughness: 0.5,
    metalness: 0.0,
    normalScale: 0.5,
    tint: TINT_NONE,
    note: 'Deep espresso grain — colour tint disabled',
  },

  // ── Stone ──
  {
    id: 'travertine_beige',
    label: 'Travertine Beige',
    category: 'stone',
    maps: T('travertine_beige'),
    source: 'ambientCG Travertine009 (CC0)',
    tile: [1.2, 1.2],
    roughness: 0.8,
    metalness: 0.0,
    normalScale: 0.8,
    tint: TINT_NONE,
    note: 'Pitted natural travertine — tint disabled',
  },
  {
    id: 'sandstone',
    label: 'Sandstone',
    category: 'stone',
    maps: T('sandstone'),
    source: 'ambientCG Bricks099 (CC0)',
    tile: [2.0, 1.0],
    roughness: 1.0,
    metalness: 0.0,
    normalScale: 1.0,
    tint: TINT_NONE,
    note: 'Sandstone block masonry — tint disabled',
  },
  {
    id: 'marble_white',
    label: 'White Marble',
    category: 'stone',
    maps: T('marble_white'),
    source: 'ambientCG Marble012 (CC0)',
    tile: [1.5, 1.5],
    roughness: 0.28,     // polished slab
    metalness: 0.0,
    normalScale: 0.3,
    tint: TINT_NONE,
    note: 'Carrara veining, polished — tint disabled',
  },
  {
    id: 'marble_black',
    label: 'Black Marble',
    category: 'stone',
    maps: T('marble_black'),
    source: 'ambientCG Marble016 (CC0)',
    tile: [1.5, 1.5],
    roughness: 0.25,
    metalness: 0.0,
    normalScale: 0.3,
    tint: TINT_NONE,
    note: 'Polished black slab — tint disabled',
  },

  // ── Brick ──
  {
    id: 'brick_whitewashed',
    label: 'Whitewashed Brick',
    category: 'brick',
    maps: T('brick_whitewashed'),
    source: 'ambientCG PaintedBricks004 (CC0)',
    tile: [1.55, 1.55],
    roughness: 1.0,
    metalness: 0.0,
    normalScale: 0.9,
    tint: TINT_NONE,
    note: 'Painted brick relief — tint disabled',
  },
  {
    id: 'brick_grey',
    label: 'Grey Brick',
    category: 'brick',
    maps: T('brick_grey'),
    source: 'ambientCG Bricks061 (CC0)',
    tile: [1.05, 1.05],
    roughness: 1.0,
    metalness: 0.0,
    normalScale: 1.0,
    tint: TINT_NONE,
    note: 'Grey stock brick — tint disabled',
  },

  // ── Wallpaper ──
  // Woven wallcoverings: tinted "carefully" (a limited blend) so a colour
  // choice reads through without flattening the weave.
  {
    id: 'wallpaper_linen',
    label: 'Linen',
    category: 'wallpaper',
    maps: T('wallpaper_linen'),
    source: 'ambientCG Fabric036 (CC0)',
    // Fine weave: a 0.25 m repeat keeps the thread visible at room distance
    // instead of averaging out to flat grey.
    tile: [0.25, 0.25],
    roughness: 0.95,
    metalness: 0.0,
    normalScale: 0.8,
    tint: TINT_SUBTLE,
    defaultColor: '#e6e1d8',
    note: 'Fine woven linen · lightly tintable',
  },
  {
    id: 'wallpaper_grasscloth',
    label: 'Grasscloth',
    category: 'wallpaper',
    maps: T('wallpaper_grasscloth'),
    source: 'ambientCG Fabric061 (CC0)',
    // Published scan size: 40 × 40 cm — a coarse open weave that stays legible.
    tile: [0.4, 0.4],
    roughness: 1.0,
    metalness: 0.0,
    normalScale: 1.0,
    tint: TINT_SUBTLE,
    defaultColor: '#ded3bf',
    note: 'Coarse natural weave · lightly tintable',
  },

  /* ══ Phase C ═══════════════════════════════════════════════════════ */

  // ── Paint & plaster ──
  {
    id: 'clay_plaster',
    label: 'Clay Plaster',
    category: 'paint',
    maps: T('clay_plaster'),
    source: 'ambientCG Plaster003 (CC0)',
    tile: [2.0, 2.0],
    roughness: 1.0,
    metalness: 0.0,
    normalScale: 0.9,
    tint: TINT_FULL,
    defaultColor: '#e8e2d6',
    note: 'Earthy hand-applied clay · tintable',
  },
  {
    id: 'tadelakt',
    label: 'Tadelakt',
    category: 'paint',
    maps: T('tadelakt'),
    source: 'ambientCG Concrete048 (CC0)',
    tile: [2.0, 2.0],
    roughness: 0.45,     // burnished, soft mineral sheen
    metalness: 0.0,
    normalScale: 0.35,
    tint: TINT_FULL,
    defaultColor: '#e7dfd0',
    note: 'Polished mineral plaster · tintable',
  },

  // ── Wood ──
  {
    id: 'wood_charred',
    label: 'Charred Wood',
    category: 'wood',
    maps: T('wood_charred'),
    source: 'ambientCG Wood062 (CC0)',
    tile: [1.0, 1.0],
    roughness: 0.85,
    metalness: 0.0,
    normalScale: 0.9,
    tint: TINT_NONE,
    note: 'Shou sugi ban burnt grain — tint disabled',
  },
  {
    id: 'bamboo',
    label: 'Bamboo',
    category: 'wood',
    maps: T('bamboo'),
    source: 'ambientCG Bamboo002B (CC0)',
    // Published scan size: 260 × 260 cm — keeps the poles at true diameter.
    tile: [2.6, 2.6],
    roughness: 0.7,
    metalness: 0.0,
    normalScale: 1.0,
    tint: TINT_NONE,
    note: 'Natural bamboo poles — tint disabled',
  },
  {
    id: 'wood_painted_panel',
    label: 'Painted Panel',
    category: 'wood',
    maps: T('wood_painted_panel'),
    source: 'ambientCG PaintedWood009C (CC0)',
    tile: [1.5, 1.5],
    roughness: 0.8,
    metalness: 0.0,
    normalScale: 0.7,
    // Paint over timber: the colour is applied, not intrinsic, so a full tint
    // is honest here — the grain relief still reads through it.
    tint: TINT_FULL,
    defaultColor: '#eceae4',
    note: 'Painted timber boarding · tintable',
  },

  // ── Stone & tile ──
  {
    id: 'terrazzo',
    label: 'Terrazzo',
    category: 'stone',
    maps: T('terrazzo'),
    source: 'ambientCG Terrazzo013 (CC0)',
    tile: [1.5, 1.5],
    roughness: 0.4,
    metalness: 0.0,
    normalScale: 0.3,
    tint: TINT_NONE,
    note: 'Polished chip aggregate — tint disabled',
  },
  {
    id: 'tile_subway',
    label: 'Subway Tile',
    category: 'stone',
    maps: T('tile_subway'),
    source: 'ambientCG Tiles010 (CC0)',
    // ~20 cm bricks across a 1.2 m tile.
    tile: [1.2, 1.2],
    roughness: 0.25,     // glazed ceramic
    metalness: 0.0,
    normalScale: 0.6,
    // Glazed ceramic is manufactured in any colour, and the scan is near-white,
    // so tinting produces a genuine product rather than a stained stone.
    tint: TINT_FULL,
    defaultColor: '#f2f3f1',
    note: 'Glazed ceramic brick-bond · tintable',
  },
  {
    id: 'granite',
    label: 'Granite',
    category: 'stone',
    maps: T('granite'),
    source: 'ambientCG Granite002A (CC0)',
    tile: [1.5, 1.5],
    roughness: 0.4,
    metalness: 0.0,
    normalScale: 0.4,
    tint: TINT_NONE,
    note: 'Speckled polished granite — tint disabled',
  },
  {
    id: 'limestone',
    label: 'Limestone',
    category: 'stone',
    maps: T('limestone'),
    source: 'ambientCG Tiles143 (CC0)',
    // Published scan size: 200 × 200 cm.
    tile: [2.0, 2.0],
    roughness: 0.85,
    metalness: 0.0,
    normalScale: 0.7,
    tint: TINT_NONE,
    note: 'Honed limestone courses — tint disabled',
  },
  {
    id: 'onyx_polished',
    label: 'Polished Onyx',
    category: 'stone',
    maps: T('onyx_polished'),
    source: 'ambientCG Onyx015 (CC0)',
    tile: [1.8, 1.8],
    roughness: 0.2,      // mirror-polished slab
    metalness: 0.0,
    normalScale: 0.25,
    tint: TINT_NONE,
    note: 'Mirror-polished veined slab — tint disabled',
  },

  // ── Brick ──
  {
    id: 'brick_rustic_red',
    label: 'Rustic Red Brick',
    category: 'brick',
    maps: T('brick_rustic_red'),
    source: 'ambientCG Bricks026 (CC0)',
    tile: [2.0, 1.0],
    roughness: 1.0,
    metalness: 0.0,
    normalScale: 1.0,
    tint: TINT_NONE,
    note: 'Aged reclaimed brick — tint disabled',
  },
  {
    id: 'brick_charcoal',
    label: 'Charcoal Brick',
    category: 'brick',
    maps: T('brick_charcoal'),
    source: 'ambientCG Bricks056 (CC0)',
    // Published scan size: 105 × 105 cm.
    tile: [1.05, 1.05],
    roughness: 1.0,
    metalness: 0.0,
    normalScale: 1.0,
    tint: TINT_NONE,
    note: 'Dark engineering brick — tint disabled',
  },

  // ── Natural wallcoverings ──
  {
    id: 'cork',
    label: 'Cork',
    category: 'wallpaper',
    maps: T('cork'),
    source: 'ambientCG Cork004 (CC0)',
    tile: [0.9, 0.9],
    roughness: 0.95,
    metalness: 0.0,
    normalScale: 0.8,
    tint: TINT_SUBTLE,
    defaultColor: '#d8bb87',
    note: 'Granulated cork panel · lightly tintable',
  },
  {
    id: 'rattan',
    label: 'Rattan',
    category: 'wallpaper',
    maps: T('rattan'),
    source: 'ambientCG Wicker010A (CC0)',
    tile: [0.7, 0.7],
    roughness: 0.9,
    metalness: 0.0,
    normalScale: 1.0,
    tint: TINT_NONE,
    note: 'Woven cane panel — tint disabled',
  },

  // Printed wallpapers are artwork, not scanned surfaces — there is no
  // genuine CC0 PBR scan of them on ambientCG or Poly Haven, and inventing
  // normal/roughness maps for them would be exactly the fake-PBR shortcut we
  // are avoiding. They stay registered (folder + required files documented in
  // public/textures/LICENSE.md) but are hidden from the picker until real
  // assets are installed; drop the maps in and delete `assetPending`.
  {
    id: 'wallpaper_botanical',
    label: 'Botanical',
    category: 'wallpaper',
    assetPending: true,
    maps: T('wallpaper_botanical'),
    tile: [0.7, 0.7],
    roughness: 0.9,
    metalness: 0.0,
    normalScale: 0.5,
    tint: TINT_SUBTLE,
    defaultColor: '#e9e6dc',
    note: 'Printed botanical · asset required',
  },
  {
    id: 'wallpaper_geometric',
    label: 'Geometric',
    category: 'wallpaper',
    assetPending: true,
    maps: T('wallpaper_geometric'),
    tile: [0.6, 0.6],
    roughness: 0.9,
    metalness: 0.0,
    normalScale: 0.5,
    tint: TINT_SUBTLE,
    defaultColor: '#e9e6dc',
    note: 'Printed geometric · asset required',
  },
]

/**
 * Built-in materials the picker offers: everything with real assets installed,
 * minus internal entries like the floor's default finish.
 */
export const AVAILABLE_MATERIALS = MATERIALS.filter((m) => !m.assetPending && !m.hidden)

/** Default material id for a surface kind. */
export const DEFAULT_FLOOR_MATERIAL_ID = 'floor_default'

export const MATERIALS_BY_ID = Object.fromEntries(MATERIALS.map((m) => [m.id, m]))

export const DEFAULT_MATERIAL_ID = 'default'

/**
 * Resolve any material id to a definition. Built-ins win; ids from other
 * sources (today the user's own uploads, tomorrow a catalogue or cloud
 * library) are looked up through their store. Everything downstream — walls,
 * floor, texture cache — consumes the same shape, so no caller needs to know
 * where a material came from.
 */
export function getMaterialDef(id) {
  if (MATERIALS_BY_ID[id]) return MATERIALS_BY_ID[id]
  const custom = getCustomMaterialDef(id)
  if (custom) return custom
  return MATERIALS_BY_ID[DEFAULT_MATERIAL_ID]
}

/**
 * Preview swatch for the picker. This is the albedo map itself, scaled down by
 * the browser: it avoids shipping a second set of derived files, and it warms
 * the HTTP cache for the exact texture the wall will request when picked.
 */
export function thumbnailFor(def) {
  return def.maps ? def.maps.color : null
}

