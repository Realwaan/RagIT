import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwind from '@tailwindcss/vite';
export default defineConfig({
  root: 'frontend',
  envDir: '..',
  base: '/static/assistant/',
  plugins: [react(), tailwind()],
  build: { outDir: '../app/static/assistant', emptyOutDir: false },
  server: { proxy: Object.fromEntries(['/api', '/upload', '/vault', '/health', '/load-sample', '/export-report'].map(p => [p, 'http://127.0.0.1:8000'])) },
});
