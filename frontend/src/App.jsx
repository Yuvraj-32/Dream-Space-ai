import { useRef, useState } from 'react'
import axios from 'axios'
import UploadPanel from './components/UploadPanel'
import SceneCanvas from './components/SceneCanvas'
import DetectionOverlay from './components/DetectionOverlay'
import DetectionStats from './components/DetectionStats'
import FloorPlanEditor from './components/FloorPlanEditor'
import Icon from './components/Icon'
import Logo, { LogoMark } from './components/Logo'
import CadReviewPanel from '@cad/CadReviewPanel'
import { cadUrl, detectCad, inspectCad } from '@cad/cadApi'
import CadProgress from '@cad/CadProgress'
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
  const [cadFile,         setCadFile]         = useState(null)   // upload response for a .dwg/.dxf
  const [cadInspect,      setCadInspect]      = useState(null)
  const [cadLoading,      setCadLoading]      = useState(false)
  const [cadGenerating,   setCadGenerating]   = useState(false)
  const [cadError,        setCadError]        = useState(null)
  const [welcomeDrag,     setWelcomeDrag]     = useState(false)
  const uploadRef = useRef(null)
  // 'cad' | 'detect' | 'editor' | '3d'

  async function handleCadUpload(data) {
    setUploadData(data)
    setImageUrl(null)
    setDetection(null)
    setConfirmedLayout(null)
    setDetectionError(null)
    setCadFile(data)
    setCadInspect(null)
    setCadError(null)
    setCadLoading(true)
    setActiveView('cad')
    try {
      setCadInspect(await inspectCad(data.filename))
    } catch (err) {
      setCadError(err.message)
    } finally {
      setCadLoading(false)
    }
  }

  async function handleCadGenerate(choice) {
    setCadGenerating(true)
    setCadError(null)
    try {
      const res = await detectCad(cadFile.filename, choice)
      setImageUrl(cadUrl(res.preview_url))
      setDetection(res)
      setActiveView('editor')
    } catch (err) {
      setCadError(err.message)
    } finally {
      setCadGenerating(false)
    }
  }

  async function handleUploadSuccess(data, localObjectUrl) {
    if (data.kind === 'cad') return handleCadUpload(data)
    setCadFile(null)
    setCadInspect(null)
    setUploadData(data)
    setImageUrl(localObjectUrl)
    setDetection(null)
    setConfirmedLayout(null)
    setDetectionError(null)
    setDetectLoading(true)
    setDetectStep('Finding walls, rooms, doors and windows…')
    setActiveView('detect')

    try {
      const res = await axios.post(`${API_BASE}/detect/${encodeURIComponent(data.filename)}?engine=${DETECT_ENGINE}&measure=${MEASURE}`)
      setDetectStep('Preparing the editor…')
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
    setActiveView('3d')
  }

  function openFilePicker() {
    uploadRef.current?.openPicker()
  }

  function onWelcomeDrop(e) {
    e.preventDefault()
    setWelcomeDrag(false)
    uploadRef.current?.handleFile(e.dataTransfer.files[0])
  }

  /* ── header status ── */
  const busy = detectLoading || cadLoading || cadGenerating
  const headerStatus = detectLoading
    ? 'Detecting walls and rooms…'
    : cadLoading
    ? 'Reading the drawing…'
    : cadGenerating
    ? 'Building walls from the drawing…'
    : confirmedLayout
    ? `Layout confirmed · ${confirmedLayout.walls.length} walls`
    : detection
    ? `${detection.walls.length} walls found · review and confirm`
    : cadInspect
    ? 'Choose the floor plan to use'
    : 'No plan loaded'

  const showWelcome = !uploadData && activeView === '3d'

  return (
    <div className={`app ${showcaseMode ? 'showcase-mode' : ''}`}>
      {/* ── Header ── */}
      <header className="header">
        <div className="header-logo">
          <Logo size={28} />
        </div>

        {/* View tabs */}
        <nav className="view-toggle" aria-label="Views" style={{ visibility: showWelcome ? 'hidden' : 'visible' }}>
          {cadFile && (
            <button
              id="btn-view-cad"
              className={`view-btn ${activeView === 'cad' ? 'active' : ''}`}
              onClick={() => setActiveView('cad')}
            >
              <Icon name="drawing" size={15} /> Drawing
            </button>
          )}
          <button
            id="btn-view-detect"
            className={`view-btn ${activeView === 'detect' ? 'active' : ''}`}
            onClick={() => setActiveView('detect')}
            disabled={!imageUrl}
          >
            <Icon name="scan" size={15} /> Detection
          </button>
          <button
            id="btn-view-editor"
            className={`view-btn ${activeView === 'editor' ? 'active' : ''}`}
            onClick={() => setActiveView('editor')}
            disabled={!detection}
          >
            <Icon name="edit" size={15} /> Edit
          </button>
          <button
            id="btn-view-3d"
            className={`view-btn ${activeView === '3d' ? 'active' : ''}`}
            onClick={() => setActiveView('3d')}
          >
            <Icon name="cube" size={15} /> 3D
          </button>
        </nav>

        <div className="header-right">
          <div className="header-phase">
            <div className={`phase-dot ${busy ? 'busy' : confirmedLayout ? 'ready' : ''}`} />
            <span>{headerStatus}</span>
          </div>
          {confirmedLayout && (
            <button
              id="btn-showcase"
              className="btn btn-dark btn-sm"
              onClick={() => {
                setActiveView('3d')
                setShowcaseMode(true)
              }}
            >
              <Icon name="present" size={14} /> Present
            </button>
          )}
        </div>
      </header>

      {/* ── Main ── */}
      <main className={`main ${showWelcome ? 'no-sidebar' : ''}`}>
        <aside className="sidebar">
          <UploadPanel
            ref={uploadRef}
            onUploadSuccess={handleUploadSuccess}
            currentStep={confirmedLayout ? 3 : detection ? 2 : imageUrl || cadFile ? 1 : 0}
            detectionError={detectionError}
          />
          <DetectionStats detection={detection} loading={detectLoading} />
        </aside>

        <section className="canvas-area" aria-label="Preview">

          {/* ── CAD review: pick plan, confirm layers/units ── */}
          <div className="view-pane" style={{ display: activeView === 'cad' ? 'flex' : 'none', flexDirection: 'column' }}>
            {cadLoading && <CadProgress filename={cadFile?.filename} />}
            {!cadLoading && cadInspect && (
              <CadReviewPanel
                key={cadInspect.session_id}
                inspect={cadInspect}
                generating={cadGenerating}
                error={cadError}
                onGenerate={handleCadGenerate}
                onCancel={() => { setCadFile(null); setCadInspect(null); setActiveView('3d') }}
              />
            )}
            {!cadLoading && !cadInspect && cadError && (
              <div className="panel-card error" style={{ margin: 'auto', maxWidth: 520 }}>
                <b>We couldn't read this CAD file.</b><br />{cadError}
              </div>
            )}
          </div>

          {/* ── Detection view: read-only overlay ── */}
          <div className="view-pane" style={{ display: activeView === 'detect' ? 'flex' : 'none', alignItems: 'center', justifyContent: 'center' }}>
            {imageUrl ? (
              <DetectionOverlay imageUrl={imageUrl} detection={detection} />
            ) : (
              <div className="canvas-empty-state">
                <span className="canvas-empty-icon"><Icon name="scan" size={24} /></span>
                <div className="canvas-empty-title">Nothing to show yet</div>
                <div className="canvas-empty-sub">Upload a floor plan and the detected walls, rooms and openings appear here.</div>
              </div>
            )}
            {detectLoading && (
              <div className="busy-overlay">
                <div className="busy-card">
                  <div className="spinner spinner-lg" />
                  <div className="busy-title">{detectStep}</div>
                  <div className="busy-sub">This usually takes 10–20 seconds.</div>
                </div>
              </div>
            )}
          </div>

          {/* ── Editor view: interactive Konva canvas ── */}
          <div className="view-pane" style={{ display: activeView === 'editor' ? 'flex' : 'none', flexDirection: 'column' }}>
            {detection ? (
              <FloorPlanEditor
                imageUrl={imageUrl}
                detection={detection}
                onConfirm={handleConfirmLayout}
              />
            ) : (
              <div className="canvas-empty-state" style={{ margin: 'auto' }}>
                <span className="canvas-empty-icon"><Icon name="edit" size={24} /></span>
                <div className="canvas-empty-title">The editor opens after detection</div>
                <div className="canvas-empty-sub">Upload a floor plan first. You can then fix walls before building the 3D model.</div>
              </div>
            )}
          </div>

          {/* ── 3D scene view ── */}
          <div className="view-pane" style={{ display: activeView === '3d' ? 'block' : 'none' }}>
            <SceneCanvas
              uploadData={uploadData}
              detection={detection}
              confirmedLayout={confirmedLayout}
              showcaseMode={showcaseMode}
              setShowcaseMode={setShowcaseMode}
            />
          </div>

          {/* ── First-run welcome ── */}
          {showWelcome && (
            <div
              className={`welcome ${welcomeDrag ? 'dragging' : ''}`}
              onDragOver={(e) => { e.preventDefault(); setWelcomeDrag(true) }}
              onDragLeave={() => setWelcomeDrag(false)}
              onDrop={onWelcomeDrop}
            >
              <div className="welcome-card">
                <LogoMark size={44} className="welcome-mark" />
                <div className="welcome-eyebrow">AI interior design</div>
                <h1 className="welcome-title">Turn a floor plan into a space your clients can walk through</h1>
                <p className="welcome-sub">
                  Upload a plan image or an AutoCAD drawing. DreamSpace finds the walls, rooms, doors and
                  windows, lets you correct them, and builds a 3D model you can finish with real materials.
                </p>
                <div className="welcome-steps">
                  <div className="welcome-step"><Icon name="upload" size={18} /><b>Upload</b>JPG, PNG or AutoCAD DWG/DXF</div>
                  <div className="welcome-step"><Icon name="edit" size={18} /><b>Review</b>Check and fix the detected walls</div>
                  <div className="welcome-step"><Icon name="cube" size={18} /><b>Explore</b>Apply materials and walk through</div>
                </div>
                <div className="welcome-actions">
                  <button className="btn btn-primary" onClick={openFilePicker}>
                    <Icon name="upload" size={15} /> Upload floor plan
                  </button>
                  <span className="welcome-note">or drag and drop it anywhere on this page</span>
                </div>
              </div>
            </div>
          )}

          {/* Status pill after confirmation */}
          {confirmedLayout && activeView === '3d' && !showcaseMode && (
            <div className="canvas-badge" style={{ top: 'auto', bottom: 16, right: 'auto', left: 16, zIndex: 10 }}>
              <div className="canvas-badge-dot" />
              {confirmedLayout.walls.length} walls · {confirmedLayout.openings?.length ?? 0} openings
            </div>
          )}
        </section>
      </main>
    </div>
  )
}
