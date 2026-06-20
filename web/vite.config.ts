import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import { viteSingleFile } from 'vite-plugin-singlefile';

// viteSingleFile inlines all JS/CSS into one index.html so the desktop shell
// loads it from a local file:// path with NO web server and no ES-module CORS
// issue. base: './' keeps references relative (also needed for the future PWA).
export default defineConfig({
  plugins: [svelte(), viteSingleFile()],
  base: './',
  build: { outDir: 'dist', emptyOutDir: true, target: 'es2020' },
  server: { port: 5174 },
});
