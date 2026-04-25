import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Treat .geojson files the same as .json — parse and export as default object.
const geojsonPlugin = {
  name: 'vite-plugin-geojson',
  transform(code, id) {
    if (id.endsWith('.geojson')) {
      return { code: `export default ${code}`, map: null };
    }
  },
};

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react(), geojsonPlugin],
  envPrefix: 'VITE_',

  // Use polling for file watching — required when the project lives on the
  // Windows filesystem and Vite runs inside WSL (/mnt/c/...).
  // inotify doesn't fire across the WSL boundary; polling does.
  server: {
    watch: {
      usePolling: true,
      interval:   300, // ms — fast enough for dev, low enough CPU cost
    },
  },

  build: {
    outDir:    'dist',
    sourcemap: true,
  },
});
