import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Режим разработки проксирует API на развернутую систему (https://localhost:8443)
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: process.env.VITE_BACKEND_URL || 'https://localhost:8443', changeOrigin: true, secure: false },
      '/health': { target: process.env.VITE_BACKEND_URL || 'https://localhost:8443', changeOrigin: true, secure: false },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          react: ['react', 'react-dom'],
          charts: ['chart.js', 'react-chartjs-2', 'chartjs-plugin-zoom', 'hammerjs'],
        },
      },
    },
  },
});
