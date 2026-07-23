import { useRef, useState, useEffect } from 'react'
import axios from 'axios'

const API_BASE = 'http://localhost:8001'

const PIPELINE_STEPS = [
  { id: 0, label: 'Upload floor plan' },
  { id: 1, label: 'Wall detection (Phase 1)' },
  { id: 2, label: '2D editor confirmation (Phase 2)' },
  { id: 3, label: '3D model generation (Phase 3)' },
  { id: 4, label: 'FPP walkthrough (Phase 4)' },
]

export default function UploadPanel({ onUploadSuccess, currentStep, detectionError }) {
  const [dragging, setDragging]   = useState(false)
  const [preview,  setPreview]    = useState(null)
  const [fileName, setFileName]   = useState(null)
  const [status,   setStatus]     = useState(null)
  const [loading,  setLoading]    = useState(false)
  const [localStep, setLocalStep] = useState(0)
  const fileInputRef = useRef(null)

  const step = currentStep !== undefined ? currentStep : localStep

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
    const objectUrl = URL.createObjectURL(file)
    setPreview(objectUrl)
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
      setStatus({
        type:   'success',
        title:  'Uploaded! Running detection…',
        detail: `${data.filename} · ${(data.size_bytes / 1024).toFixed(1)} KB`,
      })
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
  function onInputChange(e) { handleFile(e.target.files[0]) }

  return (
    <>
      <div className="sidebar-section">
        <div className="section-label">Floor Plan</div>

        <div
          id="upload-zone"
          className={`upload-zone ${dragging ? 'dragging' : ''} ${preview ? 'has-file' : ''} ${loading ? 'loading' : ''}`}
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
          onDrop={onDrop}
          onClick={() => !loading && fileInputRef.current?.click()}
          role="button"
          tabIndex={0}
          onKeyDown={e => e.key === 'Enter' && fileInputRef.current?.click()}
          aria-label="Upload floor plan image"
        >
          {loading ? (
            <div style={{
              display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 10, padding: '8px 0'
            }}>
              <div className="spinner" style={{ width: 28, height: 28, borderWidth: 3 }} />
              <div style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: 14 }}>Uploading floor plan…</div>
              <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>Sending image to FastAPI server</div>
            </div>
          ) : (
            <>
              <span className="upload-icon">{preview ? '🗺️' : '⬆️'}</span>
              <div className="upload-title">
                {preview ? 'Change floor plan' : 'Drop your floor plan here'}
              </div>
              <div className="upload-sub">JPEG, PNG, BMP, TIFF, WebP supported</div>
              <button className="upload-btn" type="button" disabled={loading}>
                📂 Browse file
              </button>
            </>
          )}
        </div>

        <input
          ref={fileInputRef}
          className="file-input"
          type="file"
          id="file-input"
          accept="image/jpeg,image/png,image/bmp,image/tiff,image/webp"
          onChange={onInputChange}
        />

        {status && (
          <div className={`status-card ${status.type}`} style={{ marginTop: 12 }}>
            <span className="status-icon">
              {status.type === 'success'
                ? '✅'
                : status.type === 'error'
                ? '❌'
                : <div className="spinner" />}
            </span>
            <div className="status-body">
              <span className="status-title">{status.title}</span>
              <span className="status-detail">{status.detail}</span>
            </div>
          </div>
        )}

        {preview && (
          <div className="preview-container" style={{ marginTop: 14 }}>
            <img src={preview} alt="Floor plan preview" />
            <div className="preview-overlay">
              <span className="preview-filename">{fileName}</span>
            </div>
          </div>
        )}
      </div>

      <div className="sidebar-section">
        <div className="section-label">Build Pipeline</div>
        <div className="pipeline">
          {PIPELINE_STEPS.map(s => (
            <div
              key={s.id}
              className={`pipeline-step ${step === s.id ? 'active' : ''} ${step > s.id ? 'done' : ''}`}
            >
              <div className="step-num">{step > s.id ? '✓' : s.id}</div>
              <span className="step-text">{s.label}</span>
            </div>
          ))}
        </div>
      </div>
    </>
  )
}
