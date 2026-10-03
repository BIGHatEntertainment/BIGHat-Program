import { build } from 'esbuild';
const R = '/root/workspace/BIGHat-Program/frontend/src/lib/openExternal.js';
const S = '/root/workspace/BIGHat-Program/frontend/scripts/bingo/stubs/shell_stub.js';
// bundle 1: the real plugin is not there (normal browser) -> import is marked external and never reached
await build({ entryPoints: [R], bundle: true, format: 'esm', platform: 'node', outfile: '/tmp/rtest/openext.bundle.mjs', logLevel: 'error', external: ['@tauri-apps/plugin-shell'] });
// bundle 2: the desktop app -> the plugin is a recording stub
await build({ entryPoints: [R], bundle: true, format: 'esm', platform: 'node', outfile: '/tmp/rtest/openext_tauri.bundle.mjs', logLevel: 'error',
  plugins: [{ name: 'shell', setup(b) { b.onResolve({ filter: /plugin-shell$/ }, () => ({ path: S })); } }] });
console.log('bundled');
