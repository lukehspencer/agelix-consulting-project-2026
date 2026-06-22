import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/ahp': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/rul': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
