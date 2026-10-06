import { build } from 'esbuild';
await build({ entryPoints: ['/root/workspace/BIGHat-Program/frontend/src/components/admin/IntegrationsTab.jsx'], bundle: true, format: 'esm', platform: 'node',
  outfile: '/tmp/rtest/integrations.bundle.mjs', logLevel: 'error', loader: { '.js': 'jsx', '.jsx': 'jsx' }, jsx: 'automatic',
  plugins: [{ name: 'savefile', setup(b) { b.onResolve({ filter: /lib\/saveFile$/ }, () => ({ path: '/root/workspace/BIGHat-Program/frontend/scripts/bingo/stubs/savefile_stub.js' })); } }],
  external: ['react', 'react-dom', 'react/jsx-runtime', 'lucide-react', 'axios'], define: { 'process.env.REACT_APP_BACKEND_URL': '"http://x"' } });
console.log('bundled integrations tab');
