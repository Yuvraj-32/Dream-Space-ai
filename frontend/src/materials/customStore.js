/**
 * customStore.js — the user's own uploaded materials ("My Materials").
 *
 * ── Architecture ──────────────────────────────────────────────────────
 * Uploads are NOT a second material system. A stored upload is turned into
 * exactly the same definition shape the built-in registry produces, so walls,
 * the floor, the texture cache and the repeat logic treat it identically. The
 * only difference is where the bytes came from.
 *
 * Storage sits behind a small `MaterialSource` interface:
 *
 *     { id, label, list(), add(rec), update(id, patch), remove(id) }
 *
 * `localSource` below implements it over IndexedDB (chosen over localStorage
 * because images are far past the ~5 MB string quota). A future
 * `cloudSource`, `catalogSource` (manufacturer libraries) or `aiSource`
 * implements the same four methods and registers itself in SOURCES — no
 * changes needed in the renderer, the registry or the picker.
 *
 * Records are stored as Blobs and exposed to Three.js as object URLs. An
 * upload carries an albedo only; normal/roughness are deliberately left absent
 * so the scalar values from the type preset are used rather than a fabricated
 * map.
 */
import { getTypePreset, DEFAULT_TYPE_ID } from './typePresets'
import { TINT_FULL } from './tint'

const DB_NAME = 'dreamspace-materials'
const DB_VERSION = 1
const STORE = 'materials'

export const CUSTOM_ID_PREFIX = 'custom:'
export const ACCEPTED_MIME = ['image/jpeg', 'image/png', 'image/webp']

/* ── tiny IndexedDB helpers (no dependencies) ────────────────────────── */
function openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION)
    req.onupgradeneeded = () => {
      const db = req.result
      if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE, { keyPath: 'id' })
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

function run(mode, fn) {
  return openDB().then(
    (db) =>
      new Promise((resolve, reject) => {
        const t = db.transaction(STORE, mode)
        const store = t.objectStore(STORE)
        let out
        try {
          out = fn(store)
        } catch (err) {
          reject(err)
          return
        }
        t.oncomplete = () => resolve(out && out.result !== undefined ? out.result : out)
        t.onerror = () => reject(t.error)
        t.onabort = () => reject(t.error)
      })
  )
}

/* ── local (browser) source ──────────────────────────────────────────── */
const localSource = {
  id: 'local',
  label: 'My Materials',
  async list() {
    const req = await run('readonly', (s) => s.getAll())
    return req || []
  },
  async add(record) {
    await run('readwrite', (s) => s.put(record))
    return record
  },
  async update(id, patch) {
    const db = await openDB()
    const existing = await new Promise((res, rej) => {
      const t = db.transaction(STORE, 'readonly')
      const r = t.objectStore(STORE).get(id)
      r.onsuccess = () => res(r.result)
      r.onerror = () => rej(r.error)
    })
    if (!existing) return null
    const next = { ...existing, ...patch, rev: (existing.rev || 0) + 1 }
    await run('readwrite', (s) => s.put(next))
    return next
  },
  async remove(id) {
    await run('readwrite', (s) => s.delete(id))
  },
}

/** Registered material sources. Future providers register here. */
export const SOURCES = { local: localSource }

/* ── in-memory mirror so lookups during render stay synchronous ──────── */
const _records = new Map() // id -> record
const _urls = new Map() // id -> object URL
const _listeners = new Set()
let _version = 0
let _hydrated = false

function bump() {
  _version += 1
  _listeners.forEach((fn) => fn())
}

export function subscribe(fn) {
  _listeners.add(fn)
  return () => _listeners.delete(fn)
}

export function getVersion() {
  return _version
}

export function isHydrated() {
  return _hydrated
}

function urlFor(rec) {
  if (!_urls.has(rec.id)) _urls.set(rec.id, URL.createObjectURL(rec.blob))
  return _urls.get(rec.id)
}

/**
 * Turn a stored record into a registry-shaped material definition.
 * `rev` participates in the material cache key so edits (type, scale,
 * rotation) never serve a stale cached material.
 */
function toDef(rec) {
  const preset = getTypePreset(rec.type)
  return {
    id: rec.id,
    label: rec.name,
    category: preset.category,
    custom: true,
    sourceId: rec.sourceId || 'local',
    typeId: rec.type,
    rev: rec.rev || 0,
    maps: { color: urlFor(rec) },
    tile: preset.tile,
    roughness: preset.roughness,
    metalness: preset.metalness,
    tint: preset.tint,
    scale: rec.scale ?? 1,
    rotation: rec.rotation ?? 0,
    defaultColor: preset.tint === TINT_FULL ? '#ffffff' : undefined,
    note: preset.label,
  }
}

/* ── public API ──────────────────────────────────────────────────────── */
export function getCustomMaterialDef(id) {
  const rec = _records.get(id)
  return rec ? toDef(rec) : null
}

export function listCustomMaterials() {
  return [..._records.values()].sort((a, b) => a.createdAt - b.createdAt).map(toDef)
}

export async function hydrate() {
  if (_hydrated) return
  try {
    for (const source of Object.values(SOURCES)) {
      const recs = await source.list()
      recs.forEach((r) => _records.set(r.id, { ...r, sourceId: source.id }))
    }
  } catch (err) {
    console.warn('[materials] could not read saved materials:', err?.message || err)
  }
  _hydrated = true
  bump()
}

/**
 * Save an uploaded image as a new material.
 * @param file  a File/Blob from the picker (jpg/png/webp)
 * @param opts  { name, type } — type is a MATERIAL_TYPES id
 */
export async function addCustomMaterial(file, { name, type } = {}) {
  if (!file) throw new Error('no file')
  if (!ACCEPTED_MIME.includes(file.type)) {
    throw new Error('Unsupported image type. Use JPG, PNG or WEBP.')
  }
  const record = {
    id: CUSTOM_ID_PREFIX + (crypto.randomUUID ? crypto.randomUUID() : String(Date.now())),
    name: (name || file.name.replace(/\.[^.]+$/, '') || 'Custom material').slice(0, 60),
    type: type || DEFAULT_TYPE_ID,
    mime: file.type,
    blob: file,
    scale: 1,
    rotation: 0,
    rev: 0,
    createdAt: Date.now(),
    sourceId: 'local',
  }
  await SOURCES.local.add(record)
  _records.set(record.id, record)
  bump()
  return toDef(record)
}

export async function updateCustomMaterial(id, patch) {
  const source = SOURCES[_records.get(id)?.sourceId || 'local']
  const next = await source.update(id, patch)
  if (next) {
    _records.set(id, { ...next, sourceId: source.id })
    bump()
  }
  return next ? toDef(next) : null
}

export function renameCustomMaterial(id, name) {
  return updateCustomMaterial(id, { name: String(name || '').slice(0, 60) || 'Untitled' })
}

export async function deleteCustomMaterial(id) {
  const source = SOURCES[_records.get(id)?.sourceId || 'local']
  await source.remove(id)
  _records.delete(id)
  const url = _urls.get(id)
  if (url) {
    URL.revokeObjectURL(url)
    _urls.delete(id)
  }
  bump()
}

// Load saved materials as soon as the module is imported so ids referenced by
// an existing layout resolve on first render where possible.
if (typeof indexedDB !== 'undefined') hydrate()
