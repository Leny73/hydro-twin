import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],

  // Expose only variables prefixed with VITE_ to the client bundle.
  // VITE_MAPBOX_TOKEN and VITE_API_ENDPOINT are consumed in App.jsx.
  envPrefix: 'VITE_',

  // Allow Vercel to deploy from the /frontend subfolder of the monorepo.
  // Set "Root Directory" to "frontend" in the Vercel project settings.
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
});
