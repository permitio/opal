#!/usr/bin/env bash
# gitleaks-range.test.sh runs .github/scripts/gitleaks-range.sh in a throwaway repository and checks
# its exit code for each range: 0 for a clean range, 1 for a range that adds a Permit API key (also
# on a line with a gitleaks:allow comment), 2 for an empty range, the zero SHA, a revision that is
# not a commit and wrong arguments, and 0 for an empty range with --if-empty notice. It also checks
# that no output shows a key. The keys are random and made at run time, so this file holds none.
#
# The throwaway repository gets copies of gitleaks-range.sh, .gitleaks.toml and
# .github/binaries.lock, and a link to bin/gitleaks, which .github/scripts/fetch-tool.sh gitleaks
# installs. It stays in a temporary directory under RUNNER_TEMP (or TMPDIR). The secrets job of
# .github/workflows/tests.yml runs it.
#
# Exit codes: 0 when every case gave the exit code it wants and no output showed a key; 1
# otherwise, with each failing case's output printed; 2 when bin/gitleaks is missing.
set -euo pipefail

root=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
if [[ ! -x $root/bin/gitleaks ]]; then
  echo "gitleaks-range.test.sh: bin/gitleaks is missing; run .github/scripts/fetch-tool.sh gitleaks"
  exit 2
fi
repo=$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/gitleaks-range-test.XXXXXX")
mkdir -p "$repo/.github/scripts" "$repo/bin"
cp -- "$root/.github/scripts/gitleaks-range.sh" "$repo/.github/scripts/"
cp -- "$root/.github/binaries.lock" "$repo/.github/"
cp -- "$root/.gitleaks.toml" "$repo/"
ln -s -- "$root/bin/gitleaks" "$repo/bin/gitleaks"
printf '/bin/\n' >"$repo/.gitignore"

# fgit runs git in the throwaway repository without the user's or the system's configuration.
fgit() {
  GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 git -C "$repo" -c user.name=test \
    -c user.email=test@example.invalid -c commit.gpgsign=false -c core.hooksPath=/dev/null "$@"
}

# commit <file> <line> adds the line to the file and commits it, and prints the commit's SHA.
commit() {
  printf '%s\n' "$2" >>"$repo/$1"
  fgit add -- "$1" >/dev/null
  fgit commit --quiet -m "add $1"
  fgit rev-parse HEAD
}

random_key() {
  echo "permit_key_$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')"
}

fgit init --quiet
fgit add -- . >/dev/null
fgit commit --quiet -m "the scan's files"
base=$(fgit rev-parse HEAD)
clean=$(commit notes.txt "nothing to see here")
key1=$(random_key)
leak=$(commit settings.txt "PERMIT_API_KEY = \"$key1\"")
key2=$(random_key)
allowed=$(commit more.txt "permit = \"$key2\"  # gitleaks:allow")

failed=0
cases=0
# check <name> <want exit> <argument>... runs gitleaks-range.sh once. With WANT_TEXT set, the
# output must also hold that text.
check() {
  local name=$1 want=$2 got=0 out
  shift 2
  cases=$((cases + 1))
  out=$("$repo/.github/scripts/gitleaks-range.sh" "$@" 2>&1) || got=$?
  if [[ $out == *"$key1"* || $out == *"$key2"* ]]; then
    failed=$((failed + 1))
    echo "FAIL - $name: the output shows a key"
    return 0
  fi
  if [[ -n ${WANT_TEXT:-} && $out != *"$WANT_TEXT"* ]]; then
    failed=$((failed + 1))
    echo "FAIL - $name: the output does not hold \"$WANT_TEXT\"; its output:"
    printf '%s\n' "$out" | sed 's/^::/: :/'
    return 0
  fi
  if [[ $got -eq $want ]]; then
    echo "ok - $name (exit $got)"
  else
    failed=$((failed + 1))
    echo "FAIL - $name: exit $got, want $want; its output:"
    printf '%s\n' "$out" | sed 's/^::/: :/'
  fi
}

zero=0000000000000000000000000000000000000000
check "a clean range" 0 "$base" "$clean"
# The permit-api-key rule exists only in .gitleaks.toml, so its name shows the config was read.
WANT_TEXT="settings.txt:1: permit-api-key" check "a range that adds a key" 1 "$clean" "$leak"
check "a key on a line with gitleaks:allow" 1 "$leak" "$allowed"
check "the whole range" 1 "$base" "$allowed"
check "an empty range" 2 "$clean" "$clean"
check "an empty range with --if-empty error" 2 --if-empty error "$clean" "$clean"
check "an empty range with --if-empty notice" 0 --if-empty notice "$clean" "$clean"
check "a head behind its base" 2 "$allowed" "$clean"
check "the zero SHA as base" 2 "$zero" "$clean"
check "a base that is not a commit" 2 no-such-revision "$clean"
check "a head that is not a commit" 2 "$base" no-such-revision
check "--if-empty with another value" 2 --if-empty sometimes "$base" "$clean"
check "one argument" 2 "$base"
check "three arguments" 2 "$base" "$clean" "$leak"

echo "gitleaks-range.test.sh: $((cases - failed)) of $cases cases passed"
[[ $failed -eq 0 ]]
