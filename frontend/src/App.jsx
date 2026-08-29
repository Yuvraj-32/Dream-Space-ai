import { useState } from 'react'
import axios from 'axios'
import UploadPanel from './components/UploadPanel'
import SceneCanvas from './components/SceneCanvas'
import DetectionOverlay from './components/DetectionOverlay'
import DetectionStats from './components/DetectionStats'
import FloorPlanEditor from './components/FloorPlanEditor'
import './index.css'
import { API_BASE } from './config'

// Detection engine: 'ml' (CubiCasa5k model — accurate, ~5-13s/image) or
// 'classical' (OpenCV pipeline — fast, less accurate). Switch here.
const DETECT_ENGINE = 'ml'
// Read the plan's printed dimension labels (OCR) to report real-world wall
// lengths and room sizes. Adds ~10s the first time (OCR model load).
const MEASURE = true

export default function App() {
  const [uploadData,      setUploadData]      = useState(null)
  const [imageUrl,        setImageUrl]        = useState(null)
  const [detection,       setDetection]       = useState(null)
  const [detectLoading,   setDetectLoading]   = useState(false)
  const [confirmedLayout, setConfirmedLayout] = useState(null)
  const [detectionError,  setDetectionError]  = useState(null)
  const [showcaseMode,    setShowcaseMode]    = useState(false)
  const [activeView,      setActiveView]      = useState('3d')
  const [detectStep,      setDetectStep]      = useState('Idle')
  // 'detect' | 'editor' | '3d'

  async function handleUploadSuccess(data, localObjectUrl) {
    setUploadData(data)
    setImageUrl(localObjectUrl)
    setDetection(null)
    setConfirmedLayout(null)
    setDetectionError(null)
    setDetectLoading(true)
    setDetectStep('File uploaded successfully. Preparing wall detection request…')
    setActiveView('detect')

    try {
      setDetectStep('Sending POST request to /api/detect/' + encodeURIComponent(data.filename) + '…')
      await new Promise(r => setTimeout(r, 200))
      
      setDetectStep('FastAPI backend processing OpenCV pipeline (lines, rooms, openings)…')
      const res = await axios.post(`${API_BASE}/detect/${encodeURIComponent(data.filename)}?engine=${DETECT_ENGINE}&measure=${MEASURE}`)
      
      setDetectStep('Response received! Walls: ' + (res.data.walls?.length ?? 0) + '. Parsing data…')
      await new Promise(r => setTimeout(r, 200))
      
      setDetectStep('Initializing 2D layout editor component…')
      setDetection(res.data)
      
      // Auto-switch to editor once detection is done
      setActiveView('editor')
    } catch (err) {
      console.error('Detection failed:', err)
      const msg = err.response?.data?.error ?? err.response?.data?.detail ?? err.message
      setDetectionError(msg)
      setDetectStep('Error: ' + msg)
      setActiveView('detect')
    } finally {
      setDetectLoading(false)
    }
  }

  function handleConfirmLayout(layout) {
    setConfirmedLayout(layout)
    setActiveView('3d')  // jump to 3D preview — Phase 3 will use this layout
  }

  /* ── header status text ── */
  const headerStatus = detectLoading
    ? 'Running CV pipeline…'
    : confirmedLayout
    ? `Layout confirmed · ${confirmedLayout.walls.length} walls locked`
    : detection
    ? `${detection.walls.length} walls detected · Edit and confirm`
    : 'Upload a floor plan to start'

  /* ── header badge phase ── */
  const headerPhase = confirmedLayout ? 'Phase 3 Ready' : detection ? 'Phase 2' : 'Phase 1'

  return (
    <div className={`app ${showcaseMode ? 'showcase-mode' : ''}`}>
      {/* ── Header ── */}
      <header className="header">
        <div className="header-logo">
          <div className="header-logo-icon">🏠</div>
          <span className="header-logo-text">DreamSpace AI</span>
          <span className="header-badge">{headerPhase}</span>
        </div>

        {/* View toggle — only show relevant tabs */}
        <div className="view-toggle">
          <button
            id="btn-view-detect"
            className={`view-btn ${activeView === 'detect' ? 'active' : ''}`}
            onClick={() => setActiveView('detect')}
            disabled={!imageUrl}
          >
            🔍 Detect
          </button>
          <button
            id="btn-view-editor"
            className={`view-btn ${activeView === 'editor' ? 'active' : ''}`}
            onClick={() => setActiveView('editor')}
            disabled={!detection}
          >
            ✏️ Editor
          </button>
          <button
            id="btn-view-3d"
            className={`view-btn ${activeView === '3d' ? 'active' : ''}`}
            onClick={() => setActiveView('3d')}
          >
            🧊 3D
          </button>
          {confirmedLayout && (
            <button
              id="btn-showcase"
              className="view-btn"
              style={{
                background: 'linear-gradient(135deg, var(--teal), var(--accent))',
                color: '#fff',
                marginLeft: 4,
                boxShadow: '0 2px 8px var(--accent-glow)'
              }}
              onClick={() => {
                setActiveView('3d')
                setShowcaseMode(true)
              }}
            >
              ✨ Showcase
            </button>
          )}
        </div>

        <div className="header-phase">
          <div className="phase-dot" />
          <span>{headerStatus}</span>
        </div>
      </header>

      {/* ── Main ── */}
      <main className="main">
        {/* Sidebar */}
        <aside className="sidebar">
          <UploadPanel 
            onUploadSuccess={handleUploadSuccess} 
            currentStep={confirmedLayout ? 3 : detection ? 2 : imageUrl ? 1 : 0}
            detectionError={detectionError}
          />
          <DetectionStats detection={detection} loading={detectLoading} />
        </aside>

        {/* Canvas area */}
        <section className="canvas-area" aria-label="Preview">

          {/* ── Detect view: read-only SVG overlay ── */}
          <div style={{
            position: 'absolute', inset: 0,
            display: activeView === 'detect' ? 'flex' : 'none',
            alignItems: 'center', justifyContent: 'center',
            background: 'var(--bg-deep)',
          }}>
            {imageUrl ? (
              <DetectionOverlay imageUrl={imageUrl} detection={detection} />
            ) : (
              <div className="canvas-empty-state">
                <span className="canvas-empty-icon">🔍</span>
                <div className="canvas-empty-title">Detection View</div>
                <div className="canvas-empty-sub">Upload a floor plan to run CV detection</div>
              </div>
            )}
            {detectLoading && (
              <div style={{
                position: 'absolute', inset: 0,
                background: 'rgba(10,12,20,0.85)',
                display: 'flex', flexDirection: 'column',
                alignItems: 'center', justifyContent: 'center', gap: 16,
              }}>
                <div className="spinner" style={{ width: 40, height: 40, borderWidth: 3 }} />
                <div style={{ color: 'var(--text-secondary)', fontSize: 14, fontWeight: 600, textAlign: 'center', padding: '0 20px' }}>
                  {detectStep}
                </div>
                <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>
                  Hough lines · contour rooms · gap detection
                </div>
              </div>
            )}
          </div>

          {/* ── Editor view: interactive Konva canvas ── */}
          <div style={{
            position: 'absolute', inset: 0,
            display: activeView === 'editor' ? 'flex' : 'none',
            flexDirection: 'column',
          }}>
            {detection ? (
              <FloorPlanEditor
                imageUrl={imageUrl}
                detection={detection}
                onConfirm={handleConfirmLayout}
              />
            ) : (
              <div className="canvas-empty-state" style={{ margin: 'auto' }}>
                <span className="canvas-empty-icon">✏️</span>
                <div className="canvas-empty-title">2D Editor</div>
                <div className="canvas-empty-sub">Run detection first to open the editor</div>
              </div>
            )}
          </div>

          {/* ── 3D scene view ── */}
          <div style={{
            position: 'absolute', inset: 0,
            display: activeView === '3d' ? 'block' : 'none',
          }}>
            <SceneCanvas 
              uploadData={uploadData} 
              detection={detection} 
              confirmedLayout={confirmedLayout} 
              showcaseMode={showcaseMode}
              setShowcaseMode={setShowcaseMode}
            />
          </div>

          {/* Corner badge */}
          {activeView !== 'editor' && !showcaseMode && (
            <div className="canvas-badge" style={{ zIndex: 10 }}>
              <div className="canvas-badge-dot" />
              {activeView === 'detect'
                ? 'OpenCV · Hough Lines · Contours'
                : 'Three.js · react-three-fiber'}
            </div>
          )}

          {/* Bottom badge when layout confirmed */}
          {confirmedLayout && activeView === '3d' && !showcaseMode && (
            <div className="canvas-badge" style={{ top: 'auto', bottom: 16, zIndex: 10 }}>
              ✅ {confirmedLayout.walls.length} walls confirmed · Phase 3 ready
            </div>
          )}
        </section>
      </main>
    </div>
  )
}
