import { useEffect, useState } from 'react'
import { getCadProgress } from './cadApi'

/**
 * Shown while a CAD file is being read. Polls /cad/progress once a second and shows which
 * step the backend is on, so a large file (up to a few minutes) never looks frozen.
 */
export default function CadProgress({ filename }) {
  const [p, setP] = useState(null)

  useEffect(() => {
    if (!filename) return undefined
    let alive = true
    const tick = async () => {
      try {
        const next = await getCadProgress(filename)
        if (alive) setP(next)
      } catch {
        /* progress is a courtesy; the main request reports real errors */
      }
    }
    tick()
    const id = setInterval(tick, 1000)
    return () => { alive = false; clearInterval(id) }
  }, [filename])

  const step = p?.step ?? 0
  const total = p?.total ?? 6
  return (
    <div className="progress-card panel-card">
      <div className="spinner spinner-lg" style={{ margin: '4px auto 14px' }} />
      <div className="busy-title">Reading the drawing…</div>
      <div className="busy-sub" style={{ marginTop: 4 }}>
        {step > 0 ? `Step ${Math.min(step, total)} of ${total}: ${p.message}` : 'Starting…'}
        {p?.elapsed_s > 5 ? ` · ${Math.round(p.elapsed_s)} s` : ''}
      </div>
      <div className="progress-track">
        <div className="progress-fill" style={{ width: `${Math.round((Math.max(step - 1, 0) / total) * 100)}%` }} />
      </div>
      {p?.elapsed_s > 30 && (
        <div className="inline-note" style={{ marginTop: 12 }}>
          Large drawings can take a few minutes. Exporting just the floor plan as DXF is much faster.
        </div>
      )}
    </div>
  )
}
