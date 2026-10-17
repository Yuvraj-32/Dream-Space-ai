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
    <div style={{ margin: 'auto', textAlign: 'center', minWidth: 280 }}>
      <div className="spinner" style={{ width: 40, height: 40, borderWidth: 3, margin: '0 auto 14px' }} />
      <div style={{ color: 'var(--text-secondary)', fontSize: 14, fontWeight: 600 }}>Reading CAD drawing…</div>
      <div style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: 4 }}>
        {step > 0 ? `Step ${Math.min(step, total)} of ${total}: ${p.message}` : 'Starting…'}
        {p?.elapsed_s > 5 ? ` · ${Math.round(p.elapsed_s)} s` : ''}
      </div>
      <div style={{ height: 4, background: 'var(--border, #2a2f3a)', borderRadius: 2, marginTop: 12 }}>
        <div style={{
          height: '100%', borderRadius: 2, background: 'var(--accent, #3dd9c6)',
          width: `${Math.round((Math.max(step - 1, 0) / total) * 100)}%`, transition: 'width 0.4s',
        }} />
      </div>
      {p?.elapsed_s > 30 && (
        <div style={{ color: 'var(--text-muted)', fontSize: 11, marginTop: 10 }}>
          Large drawings can take a few minutes. Exporting just the floor plan as DXF is much faster.
        </div>
      )}
    </div>
  )
}
