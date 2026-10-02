import { build } from 'esbuild';
const stub = (re, file) => ({ name: 'stub-'+file, setup(b){ b.onResolve({filter: re}, () => ({ path: './stubs/'+file })); } });
await build({
  entryPoints: ['/root/workspace/BIGHat-Program/frontend/src/pages/bingo/AudienceView.jsx'],
  bundle: true, format: 'esm', platform: 'node', outfile: './aud.bundle.mjs', logLevel: 'error',
  loader: { '.js': 'jsx', '.jsx': 'jsx' }, jsx: 'automatic',
  plugins: [
    stub(/components\/ui\/(button|card)$/, 'ui.jsx'),
    stub(/components\/ui\/(slider|input|dialog)$/, 'misc.jsx'),
    stub(/^framer-motion$/, 'motion.jsx'),
    stub(/^qrcode\.react$/, 'misc.jsx'),
    stub(/^canvas-confetti$/, 'confetti.js'),
  ],
  external: ['@tauri-apps/api/webviewWindow','@tauri-apps/api/window','@tauri-apps/api/core','react','react-dom','react/jsx-runtime','react-router-dom','lucide-react','sonner','axios'],
  define: { 'process.env.REACT_APP_BACKEND_URL': '"http://x"' },
});
console.log('audience bundled');
