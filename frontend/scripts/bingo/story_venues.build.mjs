import { build } from 'esbuild';
const R = '/root/workspace/BIGHat-Program/frontend/src';
const S = '/root/workspace/BIGHat-Program/frontend/scripts/bingo/stubs/';
await build({
  entryPoints: [R + '/components/story/StoryImagesManager.jsx'], bundle: true, format: 'esm', platform: 'node', outfile: '/tmp/rtest/storyimg.bundle.mjs', logLevel: 'error',
  loader: { '.js': 'jsx', '.jsx': 'jsx' }, jsx: 'automatic',
  plugins: [{ name: 'toast', setup(b) { b.onResolve({ filter: /utils\/toastCompat$/ }, () => ({ path: S + 'toast_stub.js' })); } }],
  external: ['react', 'react-dom', 'react/jsx-runtime', 'lucide-react', 'axios'],
  define: { 'process.env.REACT_APP_BACKEND_URL': '"http://x"' },
});
console.log('bundled story images');
