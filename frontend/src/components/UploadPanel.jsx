import { useRef, useState, useEffect, forwardRef, useImperativeHandle } from 'react'
import axios from 'axios'
import { API_BASE } from '../config'
import { isCadFile } from '@cad/cadApi'
import Icon from './Icon'

const PIPELINE_STEPS = [
  { id: 0, label: 'Upload plan',      hint: 'Image or AutoCAD drawing' },
  { id: 1, label: 'Detect layout',    hint: 'Walls, rooms, doors, windows' },
  { id: 2, label: 'Review in 2D',     hint: 'Fix anything that is off' },
  { id: 3, label: 'Explore in 3D',    hint: 'Materials and walkthrough' },
]

export const ACCEPT = 'image/jpeg,image/png,image/bmp,image/tiff,image/webp,.dwg,.dxf'

/**
 * Sidebar upload + progress panel. The parent can also hand it a file (e.g. one
 * dropped on the welcome screen) through the ref: uploadRef.current.handleFile(file).
 */
const UploadPanel = forwardRef(function UploadPanel({ onUploadSuccess, currentStep, detectionError }, ref) {
  const [dragging, setDragging]   = useState(false)
  const [preview,  setPreview]    = useState(null)
  const [isCad,    setIsCad]      = useState(false)
  const [fileName, setFileName]   = useState(null)
  const [status,   setStatus]     = useState(null)
  const [loading,  setLoading]    = useState(false)
  const [localStep, setLocalStep] = useState(0)
  const fileInputRef = useRef(null)

  const step = currentStep !== undefined ? currentStep : localStep

  useImperativeHandle(ref, () => ({
    handleFile,
    openPicker: () => fileInputRef.current?.click(),
  }))

  useEffect(() => {
    if (detectionError) {
      setStatus({
        type: 'error',
        title: 'Detection failed',
        detail: detectionError,
      })
    }
  }, [detectionError])

  function handleFile(file) {
    if (!file) return
    setFileName(file.name)
    // CAD files aren't images: no blob preview (App shows drawing thumbnails instead).
    const cad = isCadFile(file)
    setIsCad(cad)
    const objectUrl = cad ? null : URL.createObjectURL(file)
    setPreview(cad ? 'cad' : objectUrl)
    setStatus(null)
    uploadFile(file, objectUrl)
  }

  async function uploadFile(file, objectUrl) {
    setLoading(true)
    setStatus({ type: 'loading', title: 'Uploading…', detail: file.name })
    const form = new FormData()
    form.append('file', file)
    try {
      const { data } = await axios.post(`${API_BASE}/upload`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setStatus(null)
      setLocalStep(1)
      // Pass both server response AND the local blob URL to parent
      onUploadSuccess?.(data, objectUrl)
    } catch (err) {
      const msg = err.response?.data?.error ?? err.response?.data?.detail ?? err.message
      setStatus({ type: 'error', title: 'Upload failed', detail: msg })
    } finally {
      setLoading(false)
    }
  }

  function onDragOver(e)  { e.preventDefault(); setDragging(true) }
  function onDragLeave()  { setDragging(false) }
  function onDrop(e) {
    e.preventDefault()
    setDragging(false)
    handleFile(e.dataTransfer.files[0])
  }
  function onInputChange(e) {
    handleFile(e.target.files[0])
    e.target.value = ''   // let the same file be picked again
  }

  return (
    <>
      <div className="sidebar-section">
        <div className="section-label">Floor plan</div>

        {preview && !loading ? (
          <div className="preview-container">
            {isCad
              ? <div className="preview-cad"><Icon name="drawing" size={30} strokeWidth={1.4} /></div>
              : <img src={preview} alt="Floor plan preview" />}
            <div className="preview-overlay">
              <Icon name={isCad ? 'drawing' : 'file'} size={15} />
              <span className="preview-filename" title={fileName}>{fileName}</span>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                style={{ marginLeft: 'auto' }}
                onClick={() => fileInputRef.current?.click()}
              >
                Replace
              </button>
            </div>
          </div>
        ) : (
          <div
            id="upload-zone"
            className={`upload-zone ${dragging ? 'dragging' : ''} ${loading ? 'loading' : ''}`}
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onDrop={onDrop}
            onClick={() => !loading && fileInputRef.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={e => e.key === 'Enter' && fileInputRef.current?.click()}
            aria-label="Upload floor plan"
          >
            {loading ? (
              <div className="upload-loading">
                <div className="spinner spinner-lg" />
                <div className="upload-loading-title">Uploading…</div>
                <div className="upload-loading-sub">{fileName}</div>
              </div>
            ) : (
              <>
                <span className="upload-icon"><Icon name="upload" size={20} /></span>
                <div className="upload-title">Drop a floor plan here</div>
                <div className="upload-sub">JPG, PNG, WebP, TIFF or AutoCAD DWG/DXF</div>
                <button className="upload-btn" type="button">Choose file</button>
              </>
            )}
          </div>
        )}

        <input
          ref={fileInputRef}
          className="file-input"
          type="file"
          id="file-input"
          accept={ACCEPT}
          onChange={onInputChange}
        />

        {status && (
          <div className={`status-card ${status.type}`} style={{ marginTop: 12 }}>
            <span className="status-icon">
              {status.type === 'error'
                ? <Icon name="alert" size={16} />
                : status.type === 'success'
                ? <Icon name="checkCircle" size={16} />
                : <div className="spinner" />}
            </span>
            <div className="status-body">
              <span className="status-title">{status.title}</span>
              <span className="status-detail">{status.detail}</span>
            </div>
          </div>
        )}
      </div>

      <div className="sidebar-section">
        <div className="section-label">Progress</div>
        <div className="pipeline">
          {PIPELINE_STEPS.map(s => (
            <div
              key={s.id}
              className={`pipeline-step ${step === s.id ? 'active' : ''} ${step > s.id ? 'done' : ''}`}
            >
              <div className="step-num">{step > s.id ? <Icon name="check" size={13} strokeWidth={2.5} /> : s.id + 1}</div>
              <span className="step-text">
                {s.label}
                <span className="step-hint">{s.hint}</span>
              </span>
            </div>
          ))}
        </div>
      </div>
    </>
  )
})

export default UploadPanel
