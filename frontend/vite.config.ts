import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import react, { reactCompilerPreset } from '@vitejs/plugin-react'
import babel from '@rolldown/plugin-babel'
import tailwindcss from '@tailwindcss/vite'

const frontendRoot = dirname(fileURLToPath(import.meta.url))
const projectRoot = resolve(frontendRoot, '..')
const backendRoot = resolve(projectRoot, 'backend')

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const frontendEnv = loadEnv(mode, frontendRoot, '')
  const rootEnv = loadEnv(mode, projectRoot, '')
  const backendEnv = loadEnv(mode, backendRoot, '')
  const supabaseUrl =
    frontendEnv.VITE_SUPABASE_URL ||
    rootEnv.VITE_SUPABASE_URL ||
    backendEnv.VITE_SUPABASE_URL ||
    backendEnv.SUPABASE_URL ||
    rootEnv.SUPABASE_URL ||
    ''
  const supabaseAnonKey =
    frontendEnv.VITE_SUPABASE_ANON_KEY ||
    rootEnv.VITE_SUPABASE_ANON_KEY ||
    backendEnv.VITE_SUPABASE_ANON_KEY ||
    backendEnv.SUPABASE_ANON_KEY ||
    rootEnv.SUPABASE_ANON_KEY ||
    ''
  const appUrl =
    frontendEnv.VITE_APP_URL ||
    rootEnv.VITE_APP_URL ||
    backendEnv.VITE_APP_URL ||
    'http://localhost:5173'
  const backendUrl =
    frontendEnv.VITE_BACKEND_URL ||
    rootEnv.VITE_BACKEND_URL ||
    backendEnv.VITE_BACKEND_URL ||
    'http://localhost:8000'

  return {
    define: {
      'import.meta.env.VITE_SUPABASE_URL': JSON.stringify(supabaseUrl),
      'import.meta.env.VITE_SUPABASE_ANON_KEY': JSON.stringify(supabaseAnonKey),
      'import.meta.env.VITE_APP_URL': JSON.stringify(appUrl),
      'import.meta.env.VITE_BACKEND_URL': JSON.stringify(backendUrl),
    },
    plugins: [
      react(),
      babel({ presets: [reactCompilerPreset()] }),
      tailwindcss(),
    ],
  }
})
