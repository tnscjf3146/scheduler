import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // dev: FastAPI runs on 8000 (uvicorn app.main:app --reload)
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
})
