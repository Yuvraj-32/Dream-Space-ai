#!/usr/bin/env node
/**
 * fetch-textures.mjs — download the CC0 PBR maps the material library needs.
 *
 *   node scripts/fetch-textures.mjs          # fetch anything missing
 *   node scripts/fetch-textures.mjs --force  # re-fetch everything
 *
 * Sources every map from ambientCG (https://ambientcg.com), whose materials
 * are released under CC0 1.0 (public domain). Nothing here is generated or
 * synthesised: each file is the published scan, so the normal and roughness
 * maps carry real measured surface data.
 *
 * No npm dependencies and no external unzip binary — ZIP entries are read
 * directly and inflated with Node's built-in zlib.
 */
import { mkdir, writeFile, access } from 'node:fs/promises'
import { inflateRawSync } from 'node:zlib'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const DEST = join(ROOT, 'public', 'textures')

/** slug → ambientCG asset id. Keep in sync with src/materials/registry.js. */
const ASSETS = [
  // ── Phase A: the original six presets ──
  { slug: 'plaster_matte', id: 'Plaster001' },
  { slug: 'wood_polished', id: 'WoodFloor043' },
  { slug: 'tile_glossy', id: 'Tiles074' },
  { slug: 'concrete_raw', id: 'Concrete034' },
  { slug: 'brick_exposed', id: 'Bricks086' },

  // ── Phase B: paint & plaster ──
  { slug: 'limewash', id: 'PaintedPlaster017' },
  { slug: 'venetian_plaster', id: 'Plaster006' },
  { slug: 'stucco', id: 'Plaster002' },
  { slug: 'microcement', id: 'Concrete016' },

  // ── Phase B: wood ──
  { slug: 'wood_light_oak', id: 'WoodFloor062' },
  { slug: 'wood_walnut', id: 'Wood027' },
  { slug: 'wood_dark_walnut', id: 'Wood051' },

  // ── Phase B: stone ──
  { slug: 'travertine_beige', id: 'Travertine009' },
  { slug: 'sandstone', id: 'Bricks099' },
  { slug: 'marble_white', id: 'Marble012' },
  { slug: 'marble_black', id: 'Marble016' },

  // ── Phase B: brick ──
  { slug: 'brick_whitewashed', id: 'PaintedBricks004' },
  { slug: 'brick_grey', id: 'Bricks061' },

  // ── Phase B: wallpaper ──
  { slug: 'wallpaper_linen', id: 'Fabric036' },
  { slug: 'wallpaper_grasscloth', id: 'Fabric061' },

  // ── Phase C: paint & plaster ──
  { slug: 'clay_plaster', id: 'Plaster003' },
  { slug: 'tadelakt', id: 'Concrete048' },

  // ── Phase C: wood ──
  { slug: 'wood_charred', id: 'Wood062' },
  { slug: 'bamboo', id: 'Bamboo002B' },
  { slug: 'wood_painted_panel', id: 'PaintedWood009C' },

  // ── Phase C: stone ──
  { slug: 'terrazzo', id: 'Terrazzo013' },
  { slug: 'tile_subway', id: 'Tiles010' },
  { slug: 'granite', id: 'Granite002A' },
  { slug: 'limestone', id: 'Tiles143' },
  { slug: 'onyx_polished', id: 'Onyx015' },

  // ── Phase C: brick ──
  { slug: 'brick_rustic_red', id: 'Bricks026' },
  { slug: 'brick_charcoal', id: 'Bricks056' },

  // ── Phase C: natural wallcoverings ──
  { slug: 'cork', id: 'Cork004' },
  { slug: 'rattan', id: 'Wicker010A' },

  // NOTE: 'Botanical' and 'Geometric' wallpapers have no CC0 PBR scan on
  // ambientCG or Poly Haven — printed patterns are not scanned surfaces.
  // They are registered in registry.js as assetPending and are hidden from
  // the picker until real assets are dropped in; see LICENSE.md.
]

/** Which map goes to which filename. Displacement is intentionally not used. */
const WANTED = [
  { suffix: '_Color.jpg', out: 'color.jpg' },
  { suffix: '_NormalGL.jpg', out: 'normal.jpg' }, // GL convention = what Three.js expects
  { suffix: '_Roughness.jpg', out: 'roughness.jpg' },
]

const force = process.argv.includes('--force')

/* ── minimal ZIP reader (central directory → inflate) ─────────────── */
function unzip(buf) {
  // End of central directory record, scanned back from the tail.
  let eocd = -1
  for (let i = buf.length - 22; i >= 0 && i > buf.length - 65558; i--) {
    if (buf.readUInt32LE(i) === 0x06054b50) { eocd = i; break }
  }
  if (eocd < 0) throw new Error('not a zip file (no end-of-central-directory record)')

  const count = buf.readUInt16LE(eocd + 10)
  let p = buf.readUInt32LE(eocd + 16)
  const files = new Map()

  for (let n = 0; n < count; n++) {
    if (buf.readUInt32LE(p) !== 0x02014b50) throw new Error('corrupt central directory')
    const method = buf.readUInt16LE(p + 10)
    const compSize = buf.readUInt32LE(p + 20)
    const nameLen = buf.readUInt16LE(p + 28)
    const extraLen = buf.readUInt16LE(p + 30)
    const commentLen = buf.readUInt16LE(p + 32)
    const localOff = buf.readUInt32LE(p + 42)
    const name = buf.toString('utf8', p + 46, p + 46 + nameLen)

    // Local header repeats the name/extra lengths; payload starts after them.
    const lNameLen = buf.readUInt16LE(localOff + 26)
    const lExtraLen = buf.readUInt16LE(localOff + 28)
    const start = localOff + 30 + lNameLen + lExtraLen
    const raw = buf.subarray(start, start + compSize)

    if (method === 0) files.set(name, Buffer.from(raw))
    else if (method === 8) files.set(name, inflateRawSync(raw))
    // other methods are not used by ambientCG archives

    p += 46 + nameLen + extraLen + commentLen
  }
  return files
}

async function exists(p) {
  try { await access(p); return true } catch { return false }
}

/** Per-attempt download budget. Assets are 3–10 MB, so this is generous. */
const TIMEOUT_MS = 120_000

async function withRetry(attempts, fn) {
  let last
  for (let i = 1; i <= attempts; i++) {
    try {
      return await fn(i)
    } catch (err) {
      last = err
      if (i < attempts) await new Promise((r) => setTimeout(r, 1500 * i))
    }
  }
  throw last
}

async function fetchAsset({ slug, id }) {
  const outDir = join(DEST, slug)
  await mkdir(outDir, { recursive: true })

  if (!force) {
    const have = await Promise.all(WANTED.map((w) => exists(join(outDir, w.out))))
    if (have.every(Boolean)) {
      console.log(`  ✓ ${slug.padEnd(15)} already present`)
      return
    }
  }

  const url = `https://ambientcg.com/get?file=${id}_1K-JPG.zip`
  process.stdout.write(`  … ${slug.padEnd(15)} downloading ${id}_1K-JPG.zip`)

  // A stalled CDN socket would otherwise hang the whole run indefinitely —
  // node's fetch has no default timeout. Bound each attempt and retry.
  const zip = await withRetry(3, async (attempt) => {
    if (attempt > 1) process.stdout.write(` [retry ${attempt}]`)
    const res = await fetch(url, { redirect: 'follow', signal: AbortSignal.timeout(TIMEOUT_MS) })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return Buffer.from(await res.arrayBuffer())
  })
  process.stdout.write(` (${(zip.length / 1e6).toFixed(1)} MB)\n`)

  const files = unzip(zip)
  for (const { suffix, out } of WANTED) {
    const entry = [...files.keys()].find((k) => k.endsWith(suffix))
    if (!entry) {
      console.warn(`      ! ${id} has no ${suffix} — ${out} skipped (material falls back to a scalar value)`)
      continue
    }
    await writeFile(join(outDir, out), files.get(entry))
    console.log(`      → ${slug}/${out}`)
  }
}

console.log('Fetching CC0 PBR textures from ambientCG…\n')
let failed = 0
for (const asset of ASSETS) {
  try {
    await fetchAsset(asset)
  } catch (err) {
    failed++
    console.error(`  ✗ ${asset.slug}: ${err.message}`)
  }
}
console.log(
  failed
    ? `\nDone with ${failed} failure(s). Materials missing maps render with their scalar fallback.`
    : '\nDone. All textures present.'
)
process.exit(failed ? 1 : 0)
