// Single source of truth for the backend URL. Set VITE_API_BASE in
// frontend/.env.production (or your host's env var UI) when deploying —
// see DEPLOYMENT.md. Falls back to the local dev server so `npm run dev`
// keeps working with zero setup.
export const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8001'
