// CAD (.dwg/.dxf) API helpers. Lives in "cad update folder" with the backend half.
const API_BASE = 'http://localhost:8001'

export const CAD_EXTS = ['.dwg', '.dxf']
export const UNIT_OPTIONS = [
  { id: 'mm', label: 'Millimetres', mpu: 0.001 },
  { id: 'cm', label: 'Centimetres', mpu: 0.01 },
  { id: 'm', label: 'Metres', mpu: 1 },
  { id: 'in', label: 'Inches', mpu: 0.0254 },
  { id: 'ft', label: 'Feet', mpu: 0.3048 },
]
export const ROLE_OPTIONS = [
  { id: 'wall', label: 'Walls' },
  { id: 'door', label: 'Doors' },
  { id: 'window', label: 'Windows' },
  { id: 'room_label', label: 'Room names' },
  { id: 'ignore', label: 'Ignore' },
]

export const isCadFile = (file) =>
  CAD_EXTS.some((ext) => (file?.name || '').toLowerCase().endsWith(ext))

export const cadUrl = (path) => (path.startsWith('http') ? path : `${API_BASE}${path}`)

async function post(path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const detail = Array.isArray(data.detail) ? data.detail.map((d) => d.msg).join('; ') : data.detail
    throw new Error(detail || data.error || `Request failed (${res.status})`)
  }
  return data
}

export const inspectCad = (filename) => post(`/cad/inspect/${encodeURIComponent(filename)}`)

export const detectCad = (filename, { clusterId, layerRoles, units }) =>
  post(`/cad/detect/${encodeURIComponent(filename)}`, {
    cluster_id: clusterId,
    layer_roles: layerRoles,
    units,
  })
