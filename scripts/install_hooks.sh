#!/usr/bin/env bash
# Installs a git hook that runs the release check on any commit that changes the version number.
cd "$(git rev-parse --show-toplevel)" || exit 1
cat > .git/hooks/pre-commit <<'H'
#!/usr/bin/env bash
if git diff --cached --name-only | grep -q '^src-tauri/tauri.conf.json$'; then
  if git diff --cached -U0 src-tauri/tauri.conf.json | grep -q '^+.*"version"'; then
    bash scripts/release_check.sh || { echo "Commit blocked: write the release docs first (memory/CHANGELOG.md block, PRD, TROUBLESHOOTING_LOG, failure reports)."; exit 1; }
  fi
fi
H
chmod +x .git/hooks/pre-commit; echo "hook installed"
