import {defineConfig, loadEnv} from 'vite';
import react from '@vitejs/plugin-react';
// NEXO_* configures the dev server; model/cloud secrets never use VITE_*.
export default defineConfig(({mode}) => {
  const env = loadEnv(mode, '.', 'NEXO_');
  const browserOnly = (process.env.NEXO_BROWSER_ONLY ?? env.NEXO_BROWSER_ONLY ?? 'true') === 'true';
  const target = process.env.NEXO_API_TARGET ?? env.NEXO_API_TARGET ?? 'http://127.0.0.1:8000';
  return {
    plugins: [react()],
    server: {host: '127.0.0.1', proxy: browserOnly ? undefined : {'/api': {target}}},
    preview: {host: '127.0.0.1'},
  };
});
