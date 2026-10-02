import { build } from 'esbuild';
const R = '/root/workspace/BIGHat-Program/frontend/src';
const S = '/root/workspace/BIGHat-Program/frontend/scripts/bingo/stubs/';
const alias = (re, file) => ({ name: 'a-'+file, setup(b){ b.onResolve({ filter: re }, () => ({ path: S + file })); } });
for (const [name, entry] of [['ksetup','pages/karaoke/KaraokeSetup.jsx'],['klobby','pages/karaoke/KaraokeLobby.jsx']]) {
  await build({
    entryPoints: [R + '/' + entry], bundle: true, format: 'esm', platform: 'node', outfile: `/tmp/rtest/${name}.bundle.mjs`, logLevel: 'error',
    loader: { '.js': 'jsx', '.jsx': 'jsx' }, jsx: 'automatic',
    plugins: [alias(/context\/AuthContext$/, 'trivia_env.jsx'), alias(/lib\/api$/, 'trivia_env.jsx')],
    external: ['react','react-dom','react/jsx-runtime','react-router-dom','lucide-react','sonner','axios','@tauri-apps/plugin-dialog'],
    define: { 'process.env.REACT_APP_BACKEND_URL': '"http://x"' },
  });
}
console.log('bundled');
