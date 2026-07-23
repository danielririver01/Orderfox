import { defineConfig } from 'astro/config';
import vercel from '@astrojs/vercel';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  output: 'server',
  adapter: vercel(),
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
