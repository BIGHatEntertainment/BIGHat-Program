import { build } from 'esbuild';
const R = '/root/workspace/BIGHat-Program/frontend/src';
const alias = (re, file) => ({ name: 'a-'+file, setup(b){ b.onResolve({ filter: re }, () => ({ path: '/root/workspace/BIGHat-Program/frontend/scripts/bingo/stubs/' + file })); } });
for (const [name, entry] of [['tsetup','pages/trivia/TriviaSetupPage.jsx'],['tdash','pages/trivia/TriviaDashboard.jsx'],['admin','pages/AdminPage.js']]) {
  await build({
    entryPoints: [R + '/' + entry], bundle: true, format: 'esm', platform: 'node', outfile: `/tmp/rtest/${name}.bundle.mjs`, logLevel: 'error',
    loader: { '.js': 'jsx', '.jsx': 'jsx' }, jsx: 'automatic',
    plugins: [
      alias(/context\/AuthContext$/, 'trivia_env.jsx'),
      alias(/lib\/api$/, 'trivia_env.jsx'),
      alias(/components\/(SlideStylePanel|GlobalSlidesPanel)$/, 'trivia_panel.jsx'),
      alias(/components\/Header$/, 'trivia_header.jsx'),
      alias(/components\/BIGHatFileButtons$/, 'trivia_filebuttons.jsx'),
    ],
    external: ['react','react-dom','react/jsx-runtime','react-router-dom','lucide-react','sonner','axios'],
    define: { 'process.env.REACT_APP_BACKEND_URL': '"http://x"' },
  });
}
console.log('bundled');
