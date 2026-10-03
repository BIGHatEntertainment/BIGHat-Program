import { build } from 'esbuild';
const R = '/root/workspace/BIGHat-Program/frontend/src';
const S = '/root/workspace/BIGHat-Program/frontend/scripts/bingo/stubs/';
const alias = (re, file) => ({ name: 'a-' + file + re, setup(b) { b.onResolve({ filter: re }, () => ({ path: S + file })); } });
for (const [name, entry] of [['emgr', 'components/schedule/EmployeeManager.jsx'], ['hdr', 'components/Header.js']]) {
  await build({
    entryPoints: [R + '/' + entry], bundle: true, format: 'esm', platform: 'node', outfile: `/tmp/rtest/${name}.bundle.mjs`, logLevel: 'error',
    loader: { '.js': 'jsx', '.jsx': 'jsx' }, jsx: 'automatic',
    plugins: [alias(/ui\/(button|card|dialog|input|label|checkbox|badge)$/, 'emp_ui.jsx'), alias(/context\/AuthContext$/, 'trivia_env.jsx'),
              alias(/components\/(NativeBadge|LicenseActivationDialog)$|\/(NativeBadge|LicenseActivationDialog)$/, 'emp_misc.jsx')],
    external: ['react', 'react-dom', 'react/jsx-runtime', 'react-router-dom', 'lucide-react', 'sonner', 'axios'],
    define: { 'process.env.REACT_APP_BACKEND_URL': '"http://x"' },
  });
}
console.log('bundled');
