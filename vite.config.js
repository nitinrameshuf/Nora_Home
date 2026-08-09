// Nora Home's front-end build.
//
// Story 43 ships the *existing* UI through this pipeline and changes not one
// pixel. That is the point: pipeline risk and design risk are separated, so if
// something breaks in the next fortnight it is one or the other and never both.
//
// One entry per file the templates already load. Bundling them together would
// have been tidier and wrong — the kiosk does not load todo.css today, and
// merging entries would change the cascade on surfaces nobody is looking at.
//
// The output lands in static/nora_home/dist/ and is committed. The house must
// boot with no network and no node; the Pi never builds. See CLAUDE.md §4.

import { defineConfig } from 'vite';
import tailwindcss from '@tailwindcss/vite';
import { readdirSync } from 'node:fs';
import { resolve } from 'node:path';

const entriesIn = (dir, ext) =>
  Object.fromEntries(
    readdirSync(resolve(import.meta.dirname, 'assets', dir))
      .filter((f) => f.endsWith(ext))
      .map((f) => [`${dir}/${f.slice(0, -ext.length)}`, resolve(import.meta.dirname, 'assets', dir, f)]),
  );

export default defineConfig({
  plugins: [tailwindcss()],
  base: '/static/nora_home/dist/',
  build: {
    outDir: 'static/nora_home/dist',
    emptyOutDir: true,
    manifest: true,
    // The Pi reads these over a LAN from a device three metres away. Shaving
    // bytes matters less than being able to read a stack trace off the wall.
    sourcemap: true,
    rollupOptions: {
      input: { ...entriesIn('css', '.css'), ...entriesIn('js', '.js') },
      output: {
        // Hashed, because whitenoise serves static/ with a long cache and the
        // wall's Chromium is never manually reloaded by anyone.
        entryFileNames: '[name].[hash].js',
        chunkFileNames: 'chunk/[name].[hash].js',
        assetFileNames: '[name].[hash][extname]',
      },
    },
  },
});
