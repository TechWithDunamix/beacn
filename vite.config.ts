import { fileURLToPath } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  resolve: {
    alias: {
      // `@/views/ui/kit`, `@/js/format`. Kept in step with the `paths` entry in
      // tsconfig.json: Vite resolves at build time and tsc only type-checks, so
      // neither knows about the other and both have to be told.
      '@': fileURLToPath(new URL('.', import.meta.url)),
    },
  },

  // Tailwind v4 is a Vite plugin rather than a PostCSS step, so there is no
  // postcss.config.js and no tailwind.config.js. Content scanning is automatic;
  // the design tokens live in js/app.css under @theme.
  plugins: [tailwindcss(), react()],

  build: {
    // Where the Python side looks. app/inertia.py reads
    // static/build/.vite/manifest.json, and app/bootstrap.py serves
    // static/build/assets at /assets. Change this and change both.
    outDir: 'static/build',
    emptyOutDir: true,

    // Without this there is no manifest, and a production render has no way to
    // find the hashed filenames — the page comes back with no script tag.
    manifest: true,

    rollupOptions: {
      // This exact string is the key written into the manifest and the path the
      // dev server serves. It must match ENTRY in app/inertia.py; if the two
      // drift, development still works and production silently ships a page
      // with no JavaScript.
      input: 'js/main.tsx',
    },
  },

  server: {
    port: 5173,
    strictPort: true,
    // The browser is on the Janus origin (localhost:8000) and pulls modules
    // from this one, which is cross-origin. Without CORS the browser blocks
    // every module and the page renders blank with only a console error.
    cors: true,
    // Vite guesses the HMR host from the page, which is the Janus origin rather
    // than this one. Stating it means hot reload connects instead of falling
    // back to a full page refresh on every save.
    hmr: { host: 'localhost' },
  },
})
