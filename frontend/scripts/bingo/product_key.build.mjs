import { build } from 'esbuild';
const R = '/root/workspace/BIGHat-Program/frontend/src';
await build({
  entryPoints: [R + '/components/admin/ProductKeyTab.jsx'], bundle: true, format: 'esm', platform: 'node', outfile: '/tmp/rtest/productkey.bundle.mjs', logLevel: 'error',
  loader: { '.js': 'jsx', '.jsx': 'jsx' }, jsx: 'automatic',
  plugins: [{ name: 'native', setup(b) { b.onResolve({ filter: /context\/NativeContext$/ }, () => ({ path: '/root/workspace/BIGHat-Program/frontend/scripts/bingo/stubs/native_stub.js' })); } }],
  external: ['react', 'react-dom', 'react/jsx-runtime', 'lucide-react', 'axios'],
  define: { 'process.env.REACT_APP_BACKEND_URL': '"http://x"' },
});
console.log('bundled product key tab');
