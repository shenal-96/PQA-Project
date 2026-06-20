import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

// base: './' makes the built index.html reference assets with relative paths, so
// it loads from a local file:// path (the Windows desktop shell) and from any
// sub-path (the future iPad PWA) without a web server.
export default defineConfig({
  plugins: [svelte()],
  base: './',
  build: { outDir: 'dist', emptyOutDir: true, target: 'es2020' },
  server: { port: 5174 },
});
