import path from 'node:path';

import react from '@vitejs/plugin-react';
import { defineConfig, loadEnv } from 'vite';

import { mswServiceWorkerPlugin } from './vite-plugin-msw-worker';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_');

  return {
    publicDir: false,
    plugins: [react(), mswServiceWorkerPlugin()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, 'src'),
      },
    },
    server: {
      port: 5173,
      strictPort: false,
      host: true,
    },
    preview: {
      port: 4173,
      strictPort: false,
    },
    define: {
      __APP_MODE__: JSON.stringify(env.VITE_APP_ENV ?? mode),
    },
    build: {
      target: 'es2022',
      sourcemap: mode !== 'production',
      chunkSizeWarningLimit: 1024,
      rollupOptions: {
        output: {
          manualChunks: {
            react: ['react', 'react-dom', 'react-router-dom'],
            charts: ['chart.js', 'react-chartjs-2'],
            query: ['@tanstack/react-query'],
          },
        },
      },
    },
  };
});
