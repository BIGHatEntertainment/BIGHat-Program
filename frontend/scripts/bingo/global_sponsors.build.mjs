import { build } from 'esbuild';
await build({
  entryPoints: ['/root/workspace/BIGHat-Program/frontend/src/components/GlobalSlidesPanel.jsx'], bundle: true, format: 'esm', platform: 'node',
  outfile: '/tmp/rtest/gsp.bundle.mjs', logLevel: 'error', loader: { '.js': 'jsx', '.jsx': 'jsx' }, jsx: 'automatic',
  external: ['react', 'react-dom', 'react/jsx-runtime', 'lucide-react', 'axios'],
  define: { 'process.env.REACT_APP_BACKEND_URL': '"http://x"' },
});
console.log('bundled');
