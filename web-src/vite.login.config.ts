import { fileURLToPath, URL } from 'node:url';
import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { viteSingleFile } from 'vite-plugin-singlefile';

// The login page is built as ONE self-contained file on purpose: /login is the
// only path the auth middleware serves without a session, so a page that had to
// fetch /assets/*.js could never load for a signed-out visitor — the fetch would
// be redirected to /login. Inlining everything keeps the public surface at
// exactly one path and leaves the rest of the site behind the cookie.
export default defineConfig({
  plugins: [vue(), viteSingleFile()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  build: {
    outDir: '../web',
    emptyOutDir: false,
    target: 'es2020',
    // Big enough that the font and every chunk end up inline rather than as
    // files under /assets.
    assetsInlineLimit: 10 * 1024 * 1024,
    rollupOptions: {
      input: fileURLToPath(new URL('./login.html', import.meta.url)),
    },
  },
});
