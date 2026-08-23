import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { theme } from '../theme'

// Global counter so multiple concurrent fetches each register
let _pending = 0
const _listeners = new Set()

function _notify() {
  _listeners.forEach(fn => fn(_pending))
}

// Patch fetch once at module load
const _origFetch = window.fetch
window.fetch = function (...args) {
  _pending++
  _notify()
  return _origFetch.apply(this, args).finally(() => {
    _pending = Math.max(0, _pending - 1)
    _notify()
  })
}

export default function TopBar() {
  const [active, setActive]     = useState(false)
  const [width, setWidth]       = useState(0)
  const [fading, setFading]     = useState(false)
  const timerRef                = useRef(null)
  const rafRef                  = useRef(null)
  const location                = useLocation()

  // Advance bar smoothly while loading
  const advance = (current) => {
    if (current >= 90) return current
    const step = current < 30 ? 12 : current < 60 ? 6 : current < 80 ? 3 : 1
    return Math.min(90, current + step)
  }

  useEffect(() => {
    const handlePending = (count) => {
      if (count > 0) {
        setFading(false)
        setActive(true)
        setWidth(w => w < 10 ? 15 : advance(w))
        clearTimeout(timerRef.current)
        timerRef.current = setInterval(() => {
          setWidth(w => advance(w))
        }, 300)
      } else {
        clearInterval(timerRef.current)
        setWidth(100)
        setFading(true)
        setTimeout(() => {
          setActive(false)
          setWidth(0)
          setFading(false)
        }, 400)
      }
    }
    _listeners.add(handlePending)
    return () => {
      _listeners.delete(handlePending)
      clearInterval(timerRef.current)
      cancelAnimationFrame(rafRef.current)
    }
  }, [])

  // Also flash on route changes
  useEffect(() => {
    setFading(false)
    setActive(true)
    setWidth(40)
    const t = setTimeout(() => {
      setWidth(100)
      setFading(true)
      setTimeout(() => { setActive(false); setWidth(0); setFading(false) }, 350)
    }, 180)
    return () => clearTimeout(t)
  }, [location.pathname])

  if (!active && width === 0) return null

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, height: 3,
      zIndex: 9999, pointerEvents: 'none',
    }}>
      <div style={{
        height: '100%',
        width: `${width}%`,
        background: `linear-gradient(90deg, ${theme.primary}, ${theme.accent})`,
        transition: fading
          ? 'width 0.2s ease, opacity 0.3s ease 0.1s'
          : 'width 0.25s ease',
        opacity: fading ? 0 : 1,
        boxShadow: `0 0 8px ${theme.primary}88`,
        borderRadius: '0 2px 2px 0',
      }} />
    </div>
  )
}
