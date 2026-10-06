// alpha.89: builds the Karaoke screens into /tmp/rtest/*.bundle.mjs so the karaoke_*.check.mjs files can run them.
// Run from a folder that has node_modules (jsdom, @testing-library/react, esbuild), e.g. /tmp/rtest.
import { build } from 'esbuild';
const R = '/root/workspace/BIGHat-Program/frontend/src';
const S = '/root/workspace/BIGHat-Program/frontend/scripts/bingo/stubs/';
const alias = (re, file) => ({ name: 'a-' + file + re, setup(b) { b.onResolve({ filter: re }, () => ({ path: S + file })); } });
for (const [name, entry] of [
  ['ksetup', 'pages/karaoke/KaraokeSetup.jsx'], ['klobby', 'pages/karaoke/KaraokeLobby.jsx'],
  ['kaud', 'pages/karaoke/KaraokeAudienceView.jsx'], ['kplayer', 'pages/karaoke/KaraokePlayer.jsx'],
  ['kreq', 'pages/karaoke/KaraokeRequestPage.jsx'],
]) {
  try {
    await build({
      entryPoints: [R + '/' + entry], bundle: true, format: 'esm', platform: 'node', outfile: `/tmp/rtest/${name}.bundle.mjs`, logLevel: 'error',
      loader: { '.js': 'jsx', '.jsx': 'jsx' }, jsx: 'automatic',
      plugins: [alias(/context\/AuthContext$/, 'trivia_env.jsx'), alias(/lib\/api$/, 'trivia_env.jsx'), alias(/lib\/audienceWindow$/, 'audience_window_stub.js'), alias(/^sonner$/, 'sonner_stub.js')],
      external: ['react', 'react-dom', 'react/jsx-runtime', 'react-router-dom', 'lucide-react', 'axios', 'qrcode.react', '@tauri-apps/plugin-dialog'],
      define: { 'process.env.REACT_APP_BACKEND_URL': '"http://x"' },
    });
  } catch (e) { console.log('skip', name, String(e.message || e).split('\n')[0]); }
}
console.log('bundled');
