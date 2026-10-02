import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const nodeModules = path.join(here, 'node_modules')

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: [
      // CAD UI lives in "../cad update folder/frontend" (outside this package), so
      // its imports of react must resolve to this project's copy, not nothing.
      { find: '@cad', replacement: path.resolve(here, '../cad update folder/frontend') },
      { find: /^(react|react-dom)(\/.*)?$/, replacement: `${nodeModules}/$1$2` },
    ],
  },
  server: {
    port: 5173,
    fs: { allow: [path.resolve(here, '..')] },
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
