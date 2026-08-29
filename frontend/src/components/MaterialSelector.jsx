import { useState, useEffect, useRef } from 'react'

import {
  AVAILABLE_MATERIALS,
  CATEGORIES,
  getMaterialDef,
  thumbnailFor,
  DEFAULT_MATERIAL_ID,
  DEFAULT_FLOOR_MATERIAL_ID,
  TINT_NONE,
  TINT_SUBTLE,
} from '../materials/registry'
import { MATERIAL_TYPES, DEFAULT_TYPE_ID } from '../materials/typePresets'
import {
  listCustomMaterials,
  addCustomMaterial,
  deleteCustomMaterial,
  renameCustomMaterial,
  updateCustomMaterial,
  ACCEPTED_MIME,
} from '../materials/customStore'
import { useMaterialVersion } from '../materials/wallSurface'

const COLOR_SWATCHES = [
  { name: 'Warm White', value: '#f4f3ef' },
  { name: 'Cool Gray', value: '#e2e8f0' },
  { name: 'Charcoal', value: '#2d3748' },
  { name: 'Warm Beige', value: '#ebdcb9' },
  { name: 'Terracotta', value: '#c05640' },
  { name: 'Sage Green', value: '#8a9a86' },
  { name: 'Navy Blue', value: '#1a365d' },
]

const ROTATIONS = [0, 90, 180, 270]

export default function MaterialSelector({ selectedSurface, currentCustomization, onChange, onReset, onClose }) {
  const [customColor, setCustomColor] = useState('#ffffff')
  const [pending, setPending] = useState(null)      // { file, previewUrl, name, type }
  const [renamingId, setRenamingId] = useState(null)
  const [renameDraft, setRenameDraft] = useState('')
  const [uploadError, setUploadError] = useState(null)
  const fileInputRef = useRef(null)

  // Re-render when the saved library hydrates or an uploaded material changes.
  useMaterialVersion()
  const customMaterials = listCustomMaterials()

  const isFloor = selectedSurface?.type === 'floor'
  const title = isFloor ? 'Customize Floor' : `Customize Wall (${selectedSurface?.id})`
  const defaultColor = isFloor ? '#141824' : '#f0f2f5'

  const activeMaterialId =
    currentCustomization?.materialId || (isFloor ? DEFAULT_FLOOR_MATERIAL_ID : DEFAULT_MATERIAL_ID)
  const activeDef = getMaterialDef(activeMaterialId)
  const activeColor = currentCustomization?.color || activeDef.defaultColor || defaultColor

  // Natural scans (wood, marble, brick) ship as-is: multiplying a strong user
  // colour over them destroys the detail they were added for.
  const tintable = activeDef.tint !== TINT_NONE

  useEffect(() => {
    if (activeColor) setCustomColor(activeColor)
  }, [activeColor])

  // Release the preview object URL if the upload form is abandoned.
  useEffect(() => () => { if (pending?.previewUrl) URL.revokeObjectURL(pending.previewUrl) }, [pending])

  function emit(materialId, colorHex) {
    const def = getMaterialDef(materialId)
    onChange({
      color: colorHex,
      materialId,
      // Kept for compatibility with anything reading the old preset shape;
      // the 3D material itself is resolved from the registry by id.
      roughness: def.roughness,
      metalness: def.metalness,
    })
  }

  function handleColorSelect(colorHex) {
    if (!tintable) return
    emit(activeMaterialId, colorHex)
  }

  function handleMaterialSelect(def) {
    // Switching material adopts that material's own base colour, so picking
    // Exposed Brick after tinting a wall navy doesn't carry the navy across.
    emit(def.id, def.defaultColor || activeColor)
  }

  /* ── upload ─────────────────────────────────────────────────────── */
  function handleFilePicked(e) {
    const file = e.target.files?.[0]
    e.target.value = ''             // allow re-picking the same file later
    if (!file) return
    if (!ACCEPTED_MIME.includes(file.type)) {
      setUploadError('Unsupported file. Use JPG, PNG or WEBP.')
      return
    }
    setUploadError(null)
    setPending({
      file,
      previewUrl: URL.createObjectURL(file),
      name: file.name.replace(/\.[^.]+$/, '').slice(0, 60),
      type: DEFAULT_TYPE_ID,
    })
  }

  async function handleSaveUpload() {
    if (!pending) return
    try {
      const def = await addCustomMaterial(pending.file, { name: pending.name, type: pending.type })
      URL.revokeObjectURL(pending.previewUrl)
      setPending(null)
      emit(def.id, def.defaultColor || activeColor)   // apply it straight away
    } catch (err) {
      setUploadError(err.message || 'Could not save that image.')
    }
  }

  function handleCancelUpload() {
    if (pending?.previewUrl) URL.revokeObjectURL(pending.previewUrl)
    setPending(null)
    setUploadError(null)
  }

  async function handleDelete(def) {
    await deleteCustomMaterial(def.id)
    if (activeMaterialId === def.id) {
      const fallback = isFloor ? DEFAULT_FLOOR_MATERIAL_ID : DEFAULT_MATERIAL_ID
      emit(fallback, getMaterialDef(fallback).defaultColor || defaultColor)
    }
  }

  function commitRename(def) {
    const next = renameDraft.trim()
    if (next && next !== def.label) renameCustomMaterial(def.id, next)
    setRenamingId(null)
  }

  const activeIsCustom = !!activeDef.custom

  return (
    <div className="material-selector-panel">
      <div className="selector-header">
        <span className="selector-title">{title}</span>
        <button className="selector-close-btn" onClick={onClose} aria-label="Close customizer">×</button>
      </div>

      <div className="selector-body">
        {/* Color Palette */}
        <div className="selector-section">
          <div className="selector-section-label">
            Surface Color
            {activeDef.tint === TINT_SUBTLE && <span className="tint-hint"> · subtle on this material</span>}
          </div>

          {tintable ? (
            <div className="color-swatches-grid">
              {COLOR_SWATCHES.map((swatch) => (
                <button
                  key={swatch.name}
                  className={`swatch-btn ${activeColor === swatch.value ? 'active' : ''}`}
                  style={{ backgroundColor: swatch.value }}
                  title={swatch.name}
                  onClick={() => handleColorSelect(swatch.value)}
                />
              ))}
              <div className="custom-color-container" title="Custom Color">
                <input
                  type="color"
                  value={customColor}
                  onChange={(e) => handleColorSelect(e.target.value)}
                  className="custom-color-input"
                />
                <span className="custom-color-label">Custom</span>
              </div>
            </div>
          ) : (
            <div className="tint-disabled-note">
              {activeDef.label} uses its natural scanned colour — tinting is disabled
              to keep the texture true.
            </div>
          )}
        </div>

        {/* Built-in library */}
        <div className="selector-section">
          <div className="selector-section-label">Built-in Materials</div>
          <div className="material-presets-list">
            {CATEGORIES.map((cat) => {
              const items = AVAILABLE_MATERIALS.filter((m) => m.category === cat.id)
              if (items.length === 0) return null
              return (
                <div key={cat.id} className="preset-group">
                  <div className="preset-group-label">{cat.label}</div>
                  {items.map((def) => (
                    <button
                      key={def.id}
                      className={`preset-btn ${activeMaterialId === def.id ? 'active' : ''}`}
                      onClick={() => handleMaterialSelect(def)}
                    >
                      <span
                        className="preset-thumb"
                        style={thumbnailFor(def)
                          ? { backgroundImage: `url(${thumbnailFor(def)})` }
                          : { background: def.defaultColor || '#f0f2f5' }}
                        aria-hidden="true"
                      />
                      <span className="preset-text">
                        <span className="preset-label">{def.label}</span>
                        <span className="preset-details">{def.note}</span>
                      </span>
                    </button>
                  ))}
                </div>
              )
            })}
          </div>
        </div>

        {/* User library */}
        <div className="selector-section">
          <div className="selector-section-label">My Materials</div>

          {customMaterials.length > 0 && (
            <div className="material-presets-list">
              {customMaterials.map((def) => (
                <div key={def.id} className="custom-row">
                  <button
                    className={`preset-btn ${activeMaterialId === def.id ? 'active' : ''}`}
                    onClick={() => handleMaterialSelect(def)}
                  >
                    <span
                      className="preset-thumb"
                      style={{ backgroundImage: `url(${thumbnailFor(def)})` }}
                      aria-hidden="true"
                    />
                    <span className="preset-text">
                      {renamingId === def.id ? (
                        <input
                          className="rename-input"
                          value={renameDraft}
                          autoFocus
                          onClick={(e) => e.stopPropagation()}
                          onChange={(e) => setRenameDraft(e.target.value)}
                          onBlur={() => commitRename(def)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') commitRename(def)
                            if (e.key === 'Escape') setRenamingId(null)
                          }}
                        />
                      ) : (
                        <span className="preset-label">{def.label}</span>
                      )}
                      <span className="preset-details">{def.note}</span>
                    </span>
                  </button>
                  <div className="custom-row-actions">
                    <button
                      className="icon-btn"
                      title="Rename"
                      onClick={() => { setRenamingId(def.id); setRenameDraft(def.label) }}
                    >✎</button>
                    <button className="icon-btn danger" title="Delete" onClick={() => handleDelete(def)}>×</button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Upload */}
          {!pending && (
            <>
              <button className="upload-material-btn" onClick={() => fileInputRef.current?.click()}>
                + Upload Custom Texture
              </button>
              <input
                ref={fileInputRef}
                type="file"
                accept={ACCEPTED_MIME.join(',')}
                style={{ display: 'none' }}
                onChange={handleFilePicked}
              />
              {customMaterials.length === 0 && (
                <div className="preset-details" style={{ marginTop: 2 }}>
                  JPG, PNG or WEBP · saved in this browser
                </div>
              )}
            </>
          )}

          {pending && (
            <div className="upload-form">
              <div className="upload-preview-row">
                <span className="preset-thumb" style={{ backgroundImage: `url(${pending.previewUrl})` }} />
                <input
                  className="rename-input"
                  value={pending.name}
                  onChange={(e) => setPending({ ...pending, name: e.target.value })}
                  placeholder="Material name"
                />
              </div>

              <div className="preset-group-label">What type of material is this?</div>
              <select
                className="type-select"
                value={pending.type}
                onChange={(e) => setPending({ ...pending, type: e.target.value })}
              >
                {MATERIAL_TYPES.map((t) => (
                  <option key={t.id} value={t.id}>{t.label}</option>
                ))}
              </select>
              <div className="preset-details">
                {MATERIAL_TYPES.find((t) => t.id === pending.type)?.hint}
              </div>

              <div className="upload-actions">
                <button className="confirm-btn-small" onClick={handleSaveUpload}>Add material</button>
                <button className="icon-btn" onClick={handleCancelUpload}>Cancel</button>
              </div>
            </div>
          )}

          {uploadError && <div className="upload-error">{uploadError}</div>}
        </div>

        {/* Per-material settings for uploads */}
        {activeIsCustom && (
          <div className="selector-section">
            <div className="selector-section-label">Texture Settings</div>

            <label className="setting-row">
              <span>Scale</span>
              <input
                type="range"
                min="0.25" max="4" step="0.05"
                value={activeDef.scale}
                onChange={(e) => updateCustomMaterial(activeDef.id, { scale: parseFloat(e.target.value) })}
              />
              <span className="setting-value">{Number(activeDef.scale).toFixed(2)}×</span>
            </label>

            <div className="setting-row">
              <span>Rotation</span>
              <div className="rotation-group">
                {ROTATIONS.map((deg) => (
                  <button
                    key={deg}
                    className={`rot-btn ${Number(activeDef.rotation) === deg ? 'active' : ''}`}
                    onClick={() => updateCustomMaterial(activeDef.id, { rotation: deg })}
                  >{deg}°</button>
                ))}
              </div>
            </div>

            <div className="preset-details">
              Applies wherever this material is used.
            </div>
          </div>
        )}
      </div>

      <div className="selector-footer">
        <button className="reset-btn-secondary" onClick={onReset}>
          Reset to Default
        </button>
      </div>
    </div>
  )
}
