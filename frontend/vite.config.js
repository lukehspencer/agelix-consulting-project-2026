import path from 'path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // Read .env from the repo root, since this project keeps a single
  // top-level .env file rather than one per package.
  envDir: path.resolve(__dirname, '..'),
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
      '/upload': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/rag': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
  },
})
