import { useState, useEffect } from 'react'

const COLOR_SWATCHES = [
  { name: 'Warm White', value: '#f4f3ef' },
  { name: 'Cool Gray', value: '#e2e8f0' },
  { name: 'Charcoal', value: '#2d3748' },
  { name: 'Warm Beige', value: '#ebdcb9' },
  { name: 'Terracotta', value: '#c05640' },
  { name: 'Sage Green', value: '#8a9a86' },
  { name: 'Navy Blue', value: '#1a365d' },
]

const MATERIAL_PRESETS = [
  { id: 'default', label: 'Default Paint', roughness: 0.8, metalness: 0.05, clearcoat: 0 },
  { id: 'hardwood', label: 'Polished Wood', roughness: 0.2, metalness: 0.1, clearcoat: 0.6 },
  { id: 'tile', label: 'Glossy Tile', roughness: 0.12, metalness: 0.25, clearcoat: 0.3 },
  { id: 'plaster', label: 'Matte Plaster', roughness: 0.9, metalness: 0.02, clearcoat: 0 },
  { id: 'concrete', label: 'Raw Concrete', roughness: 0.85, metalness: 0.05, clearcoat: 0 },
  { id: 'brick', label: 'Exposed Brick', roughness: 0.78, metalness: 0.04, clearcoat: 0 },
]

export default function MaterialSelector({ selectedSurface, currentCustomization, onChange, onReset, onClose }) {
  const [customColor, setCustomColor] = useState('#ffffff')

  const title = selectedSurface?.type === 'floor' ? 'Customize Floor' : `Customize Wall (${selectedSurface?.id})`
  const defaultColor = selectedSurface?.type === 'floor' ? '#141824' : '#f0f2f5'

  const activeColor = currentCustomization?.color || defaultColor
  const activeMaterialId = currentCustomization?.materialId || 'default'

  // Update custom color picker state when active color changes
  useEffect(() => {
    if (activeColor) {
      setCustomColor(activeColor)
    }
  }, [activeColor])

  function handleColorSelect(colorHex) {
    const preset = MATERIAL_PRESETS.find(p => p.id === activeMaterialId) || MATERIAL_PRESETS[0]
    onChange({
      color: colorHex,
      materialId: activeMaterialId,
      roughness: preset.roughness,
      metalness: preset.metalness,
      clearcoat: preset.clearcoat,
    })
  }

  function handleMaterialSelect(preset) {
    onChange({
      color: activeColor,
      materialId: preset.id,
      roughness: preset.roughness,
      metalness: preset.metalness,
      clearcoat: preset.clearcoat,
    })
  }

  return (
    <div className="material-selector-panel">
      <div className="selector-header">
        <span className="selector-title">{title}</span>
        <button className="selector-close-btn" onClick={onClose} aria-label="Close customizer">×</button>
      </div>

      <div className="selector-body">
        {/* Color Palette */}
        <div className="selector-section">
          <div className="selector-section-label">Surface Color</div>
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
            {/* Custom Color Input */}
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
        </div>

        {/* Material Presets */}
        <div className="selector-section">
          <div className="selector-section-label">Material Preset</div>
          <div className="material-presets-list">
            {MATERIAL_PRESETS.map((preset) => (
              <button
                key={preset.id}
                className={`preset-btn ${activeMaterialId === preset.id ? 'active' : ''}`}
                onClick={() => handleMaterialSelect(preset)}
              >
                <span className="preset-label">{preset.label}</span>
                <span className="preset-details">
                  Roughness: {preset.roughness} · Metalness: {preset.metalness}
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="selector-footer">
        <button className="reset-btn-secondary" onClick={onReset}>
          Reset to Default
        </button>
      </div>
    </div>
  )
}
