#!/usr/bin/env bash
# Release documentation check. Run before every release commit/push:  bash scripts/release_check.sh
# Fails (exit 1) unless the docs for the CURRENT version are written. Simple on purpose.
cd "$(git rev-parse --show-toplevel)" || exit 1
VER=$(grep -m1 '"version"' src-tauri/tauri.conf.json | sed 's/.*alpha\.\([0-9]*\).*/\1/')
[ -z "$VER" ] && { echo "RELEASE CHECK: cannot read the alpha number from src-tauri/tauri.conf.json"; exit 1; }
TAG="alpha.$VER"; BAD=0
fail() { echo "RELEASE CHECK FAILED ($TAG): $1"; BAD=1; }
for f in memory/CHANGELOG.md memory/PRD.md memory/TROUBLESHOOTING_LOG.md memory/DO_NOT_REPEAT.md FILE_MAP.md; do
  [ -f "$f" ] || fail "missing file $f"
done
grep -q "$TAG" memory/CHANGELOG.md        || fail "memory/CHANGELOG.md has no entry for $TAG"
grep -q "$TAG" memory/PRD.md              || fail "memory/PRD.md does not mention $TAG (update the STATUS section)"
grep -q "$TAG" memory/TROUBLESHOOTING_LOG.md || fail "memory/TROUBLESHOOTING_LOG.md has no line for $TAG (time, what was tried, result)"
# the changelog block for this release must say what was tested and what was NOT verified
BLOCK=$(awk -v t="## $TAG " 'index($0,t)==1{f=1;next} /^## /{f=0} f' memory/CHANGELOG.md)
[ -z "$BLOCK" ] && fail "memory/CHANGELOG.md needs a block that starts with '## $TAG (' (see the alpha.102 block)"
echo "$BLOCK" | grep -q "^TESTED:"       || fail "the $TAG changelog block has no 'TESTED:' line"
echo "$BLOCK" | grep -q "^NOT VERIFIED:" || fail "the $TAG changelog block has no 'NOT VERIFIED:' line"
echo "$BLOCK" | grep -q "^FILES:"        || fail "the $TAG changelog block has no 'FILES:' line"
echo "$BLOCK" | grep -q "^TIME (MST):"   || fail "the $TAG changelog block has no 'TIME (MST):' line"
# a fix for a failure, or a regression, needs a failure report that names this release
if echo "$BLOCK" | grep -qE "^FIXES FAILURE:|REGRESSION|FAILED"; then
  grep -rlq "$TAG" memory/failures/F-*.md 2>/dev/null || fail "this release is a fix/regression but no memory/failures/F-*.md file mentions $TAG"
fi
# every failure report must have all 14 sections filled in (not left as the template)
for f in memory/failures/F-*.md; do
  [ -f "$f" ] || continue
  n=$(grep -c '^## [0-9]*\.' "$f"); [ "$n" -ge 14 ] || fail "$f has only $n of 14 sections"
  grep -q '^Status:' "$f" || fail "$f has no Status line"
done
[ "$BAD" = 0 ] && echo "RELEASE CHECK OK ($TAG): changelog block, PRD, troubleshooting log and failure reports are in place."
exit $BAD
