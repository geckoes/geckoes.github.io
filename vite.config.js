import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  base: '/geckoes.github.io/',   // sostituisci con il nome del tuo repo
})
