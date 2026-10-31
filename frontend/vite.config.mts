import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwind from '@tailwindcss/vite';

export default defineConfig({
  root: 'frontend',
  envDir: '..',
  base: '/static/assistant/',
  plugins: [react(), tailwind()],
  build: {
    outDir: '../app/static/assistant',
    emptyOutDir: false,
    chunkSizeWarningLimit: 800,
    rollupOptions: {
      output: {
        manualChunks: (id) => {
          if (id.includes('@clerk')) return 'clerk-auth';
          if (id.includes('react-dom') || id.includes('/node_modules/react/') || id.includes('\\node_modules\\react\\')) return 'react-vendor';
          if (id.includes('@assistant-ui/react-markdown') || id.includes('remark') || id.includes('rehype') || id.includes('katex')) return 'markdown-math';
          if (id.includes('@assistant-ui')) return 'assistant-ui';
          if (id.includes('lucide-react') || id.includes('@radix-ui')) return 'ui-primitives';
        },
      },
    },
  },
  server: {
    proxy: Object.fromEntries(
      ['/api', '/upload', '/vault', '/health', '/load-sample', '/export-report'].map((p) => [
        p,
        'http://127.0.0.1:8000',
      ])
    ),
  },
});
