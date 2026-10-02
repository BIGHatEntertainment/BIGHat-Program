Lobby walk-through check (Bingo first screen -> Traditional / Music -> Regular / Lightning -> ...).
Needs (not in the app's own packages): jsdom@24 @testing-library/react@14 @testing-library/dom esbuild
  cd frontend/scripts/bingo && npm i --no-save jsdom@24 @testing-library/react@14 @testing-library/dom esbuild
  node lobby_walk.build.mjs && node lobby_walk.check.mjs
Last run: all checks ok. The check FAILS on the pre-alpha.67 Lobby (verified).

Music Bingo checks (alpha.67): host_walk.check.mjs (host page: song list, Start Game with rewards 404, load 40 videos, Next Song + 5s cooldown) and
aud_walk.check.mjs (audience: fullscreen gate, preload-next, plays the host's song, audio on). Build first:
  node music_host.build.mjs && node music_aud.build.mjs   (extra deps: qrcode.react canvas-confetti @radix-ui/react-slider)
Backend: backend/tests/test_alpha67_music_bingo_restore.py (game survives a restart; local-mode song code still present).
