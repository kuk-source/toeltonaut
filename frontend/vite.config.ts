import http from 'node:http'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const apiTarget = process.env.VITE_API_TARGET ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
        // Kein Keep-Alive: frische Verbindung pro Request, keine stale-Connection-Resets
        // wenn der Backend-Container neustartet.
        agent: new http.Agent({ keepAlive: false }),
      },
      '/docs': {
        target: apiTarget,
        changeOrigin: true,
        agent: new http.Agent({ keepAlive: false }),
      },
    },
  },
})
