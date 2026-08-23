// Standalone (`:8000`) serves this SPA at `/` and its API at `/api/*`.
// The unified platform serves it at `/aop/*` and mounts its router at
// `/api/aop/*` — so API calls there need the extra `/api/aop` prefix.
// Detect which mode we're in from the page's own path (a real, load-time
// signal — not guesswork) rather than hardcoding per build.
const isUnified = window.location.pathname.startsWith('/aop')

export const API_BASE = isUnified ? '/api/aop' : ''

export const apiUrl = (path) => `${API_BASE}${path}`
