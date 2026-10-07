import { build } from 'esbuild';
const stub = (re, file) => ({ name: 'stub-'+file, setup(b){ b.onResolve({filter: re}, () => ({ path: '/root/workspace/BIGHat-Program/frontend/scripts/bingo/stubs/'+file })); } });
await build({
  entryPoints: ['/root/workspace/BIGHat-Program/frontend/src/pages/bingo/Lobby.jsx'],
  bundle: true, format: 'esm', platform: 'node', outfile: './lobby.bundle.mjs', logLevel: 'error',
  loader: { '.js': 'jsx', '.jsx': 'jsx' }, jsx: 'automatic',
  plugins: [
    stub(/components\/ui\/(button|card|radio-group|label)$/, 'ui.jsx'),
    stub(/components\/BIGHatFileButtons$/, 'ui.jsx'),
    stub(/^framer-motion$/, 'motion.jsx'),
  ],
  external: ['react','react-dom','react/jsx-runtime','react-router-dom','lucide-react','sonner','axios'],
  define: { 'process.env.REACT_APP_BACKEND_URL': '"http://x"' },
});
console.log('bundled');
