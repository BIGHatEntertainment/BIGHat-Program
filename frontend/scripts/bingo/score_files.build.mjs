import { build } from 'esbuild';
const R = '/root/workspace/BIGHat-Program/frontend/src';
await build({ entryPoints: [R + '/lib/scoreFiles.js'], bundle: true, format: 'esm', platform: 'node', outfile: '/tmp/rtest/sfiles.bundle.mjs', logLevel: 'error',
  external: ['axios'], define: { 'process.env.REACT_APP_BACKEND_URL': '"http://x"' } });
console.log('bundled');
await build({ entryPoints: [R + '/lib/scoreboardApi.js'], bundle: true, format: 'esm', platform: 'node', outfile: '/tmp/rtest/sapi.bundle.mjs', logLevel: 'error',
  external: ['axios'], define: { 'process.env.REACT_APP_BACKEND_URL': '"http://x"' } });
