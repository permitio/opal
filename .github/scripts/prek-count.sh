#!/usr/bin/env bash
# prek-count.sh runs every hook in .pre-commit-config.yaml on every file with prek, and checks
# that EXPECTED_HOOKS hooks reported Passed, or Skipped with a reason such as
# "(no files to check)". A hook that the SKIP variable skips reports Skipped without a reason,
# and a hook removed from the configuration reports nothing, so either leaves the count short.
# prek's output is printed between stop-commands lines, so a hook's output cannot issue workflow
# commands. The pre-commit job of .github/workflows/pre-commit.yml runs it.
#
# It reads EXPECTED_HOOKS, the number of hooks, and PREK, the prek to run: bin/prek at the
# repository root by default, which .github/scripts/fetch-tool.sh prek installs.
#
# Exit codes: 0 when every hook passed or had nothing to check and EXPECTED_HOOKS hooks reported;
# 1 when a hook failed; 2 when the check did not run: the script was given arguments,
# EXPECTED_HOOKS is not a positive number, prek is not installed or exited with a code other than
# 0 or 1, or another number of hooks than EXPECTED_HOOKS reported.
set -euo pipefail

fail() {
  echo "prek-count: $*" >&2
  exit 2
}

[[ $# -eq 0 ]] || fail "usage: prek-count.sh (it takes no arguments)"
root=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
expected=${EXPECTED_HOOKS:-}
[[ $expected =~ ^[1-9][0-9]*$ ]] || fail "EXPECTED_HOOKS \"$expected\" is not a positive number"
prek=${PREK:-$root/bin/prek}
[[ -f $prek && -x $prek ]] ||
  fail "${prek#"$root"/} is not an executable; install it with .github/scripts/fetch-tool.sh prek"

tmp=$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/prek-count.XXXXXX") ||
  fail "creating a temporary directory failed"
log=$tmp/log
token=$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')

echo "prek-count: running every hook" >&2
code=0
echo "::stop-commands::$token"
(cd -- "$root" && "$prek" run --all-files --show-diff-on-failure --color=never \
  --no-progress --no-hide-status) 2>&1 | tee "$log" || code=$?
echo "::$token::"
case $code in
0) ;;
1)
  echo "prek-count: a hook failed; see its output above" >&2
  exit 1
  ;;
*) fail "prek exited $code, so the hooks did not run" ;;
esac
count=$(awk '/(Passed|\)Skipped)$/ { n++ } END { print n + 0 }' "$log")
[[ $count -eq $expected ]] || fail "$count of $expected hooks passed or had nothing to check;" \
  "a hook was skipped, added or removed: run every hook, or change EXPECTED_HOOKS"
echo "prek-count: $count of $expected hooks passed or had nothing to check" >&2
