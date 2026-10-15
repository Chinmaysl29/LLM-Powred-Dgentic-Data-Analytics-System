import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    // Windows edits on the Docker/WSL bind mount can miss native watch events.
    // Poll so transformed modules cannot silently lag behind the mounted source.
    watch: { usePolling: true, interval: 500 },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules')) {
            if (/[\\/]node_modules[\\/](react|react-dom|scheduler)[\\/]/.test(id)) {
              return 'vendor-react';
            }
            if (/[\\/]node_modules[\\/](react-router|react-router-dom|@remix-run)[\\/]/.test(id)) {
              return 'vendor-router';
            }
            if (/[\\/]node_modules[\\/]motion[\\/]/.test(id)) {
              return 'vendor-motion';
            }
            if (/[\\/]node_modules[\\/]lucide-react[\\/]/.test(id)) {
              return 'vendor-icons';
            }
          }
        },
      },
    },
  },
})
