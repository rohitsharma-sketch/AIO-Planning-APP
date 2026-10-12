import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: './',
  server: {
    port: 5175,
    strictPort: true,
    proxy: {
      // the unified platform (Sales Plan's routers live there under /api/planning). Sign in once at
      // http://localhost:8010/login - the session cookie is host-only, so it is sent to :5175 too.
      '/api': {
        target: 'http://localhost:8010',
        changeOrigin: true,
      },
    },
  },
})
