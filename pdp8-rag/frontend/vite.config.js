import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  // Load env file based on `mode` in the current working directory.
  // Set the third parameter to '' to load all env regardless of the `VITE_` prefix.
  const env = loadEnv(mode, process.cwd(), '');

  return {
    plugins: [react()],
    server: {
      port: 3000,
      proxy: {
        '/chat': {
          target: env.VITE_BACKEND_URL || 'http://localhost:8009',
          changeOrigin: true,
        },
        '/documents': {
          target: env.VITE_BACKEND_URL || 'http://localhost:8009',
          changeOrigin: true,
        },
        '/rag': {
          target: env.VITE_BACKEND_URL || 'http://localhost:8009',
          changeOrigin: true,
        },
      },
    },
    build: {
      outDir: 'dist',
      sourcemap: true,
    },
  };
});
