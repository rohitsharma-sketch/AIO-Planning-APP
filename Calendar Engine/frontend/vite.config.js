import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // Relative base: this app is only ever served mounted at /calendar/* in
  // the unified platform (no standalone mode) — a relative base resolves
  // built asset links correctly under that subpath. Same fix AOP
  // Forecaster's own vite.config.js already documents needing.
  base: './',
  server: {
    port: 5177,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8010',
        changeOrigin: true,
      }
    }
  }
})
