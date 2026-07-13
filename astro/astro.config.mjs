import { defineConfig } from 'astro/config';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  output: 'server',
  server: {
    port: 4321,
  },
  vite: {
    plugins: [tailwindcss()],
    server: {
      allowedHosts: true,
      proxy: {
        '/menu/api': {
          target: 'http://localhost:5000',
          changeOrigin: true,
        },
      },
    },
  },
});
