import { fileURLToPath, URL } from 'node:url';
import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

// The player app. Output lands in ../web, which the bot serves: index.html at
// "/" and the hashed chunks under /assets (behind the same session cookie as
// everything else). emptyOutDir stays off because ../web also holds the
// uploaded covers/ directory and the separately built login.html.
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  build: {
    outDir: '../web',
    emptyOutDir: false,
    assetsDir: 'assets',
    target: 'es2020',
    rollupOptions: {
      input: fileURLToPath(new URL('./index.html', import.meta.url)),
    },
  },
  // `npm run dev` against a bot already running on :5000.
  server: {
    proxy: {
      '/api': 'http://localhost:5000',
      '/covers': 'http://localhost:5000',
      '/login': 'http://localhost:5000',
    },
  },
});
