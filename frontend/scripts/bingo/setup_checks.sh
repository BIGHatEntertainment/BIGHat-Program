#!/usr/bin/env bash
# Rebuilds the scratch folder used by the Bingo click-through checks (it lives in /tmp and
# gets cleared). Usage:  bash setup_checks.sh   then   node /tmp/rtest/<name>.mjs
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
R=/tmp/rtest; mkdir -p $R && cd $R
[ -f package.json ] || npm init -y >/dev/null 2>&1
[ -d node_modules/jsdom ] || npm install react@18 react-dom@18 react-router-dom@6 sonner lucide-react axios framer-motion@11 esbuild jsdom@24 \
   @testing-library/react@14 @testing-library/dom qrcode.react canvas-confetti @radix-ui/react-slider --silent --no-audit --no-fund
cp -r "$HERE/stubs" $R/
for f in lobby_walk theme_walk host_walk aud_walk setup_walk; do cp "$HERE/$f.check.mjs" $R/$f.mjs; sed -i "s#\./#/tmp/rtest/#g" $R/$f.mjs; done
cp "$HERE/lobby_walk.build.mjs" $R/build.mjs
cp "$HERE/music_host.build.mjs" $R/build_host.mjs
cp "$HERE/music_aud.build.mjs" $R/build_aud.mjs
cp "$HERE/setup_walk.build.mjs" $R/build_setup.mjs
sed -i "s#\./#/tmp/rtest/#g" $R/build.mjs $R/build_host.mjs $R/build_aud.mjs $R/build_setup.mjs
node build.mjs >/dev/null; node build_host.mjs >/dev/null; node build_aud.mjs >/dev/null; node build_setup.mjs >/dev/null
echo "checks ready in $R"
