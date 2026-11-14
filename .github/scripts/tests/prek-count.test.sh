#!/usr/bin/env bash
# prek-count.test.sh runs .github/scripts/prek-count.sh with a fake prek, given through PREK, that
# prints the hook lines and exits with the code each case sets, and checks prek-count's exit code:
# 0 when EXPECTED_HOOKS hooks passed or had nothing to check, 1 when a hook failed, 2 when the
# check did not run or the count is off. The pre-commit job of .github/workflows/pre-commit.yml
# runs it. The fake prek stays in a temporary directory under RUNNER_TEMP (or TMPDIR).
#
# Exit codes: 0 when every case gave the exit code it wants; 1 otherwise, with each failing case's
# output printed.
set -euo pipefail

script=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)/prek-count.sh
tmp=$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/prek-count-test.XXXXXX")
fake=$tmp/prek
cat >"$fake" <<'EOF'
#!/usr/bin/env bash
cat -- "$FAKE_OUTPUT"
exit "$FAKE_EXIT"
EOF
chmod +x "$fake"
failed=0
cases=0

# check <name> <want exit> <EXPECTED_HOOKS> <fake exit> <hook line>... runs prek-count once.
check() {
  local name=$1 want=$2 expected=$3 fake_exit=$4 got=0 out
  shift 4
  cases=$((cases + 1))
  printf '%s\n' "$@" >"$tmp/output"
  out=$(env -i PATH="$PATH" HOME="${HOME:-/}" PREK="${PREK_OVERRIDE:-$fake}" \
    EXPECTED_HOOKS="$expected" FAKE_OUTPUT="$tmp/output" FAKE_EXIT="$fake_exit" \
    RUNNER_TEMP="$tmp" "$script" ${EXTRA_ARG:+"$EXTRA_ARG"} 2>&1) || got=$?
  if [[ $got -eq $want ]]; then
    echo "ok - $name (exit $got)"
  else
    failed=$((failed + 1))
    echo "FAIL - $name: exit $got, want $want; its output:"
    printf '%s\n' "$out" | sed 's/^::/: :/'
  fi
}

passed='check yaml.....................................Passed'
nothing='ruff format.......................(no files to check)Skipped'
skipped='ruff check......................................Skipped'
failed_hook='zizmor..........................................Failed'

check "every hook passed" 0 3 0 "$passed" "$passed" "$passed"
check "a hook had nothing to check" 0 3 0 "$passed" "$passed" "$nothing"
check "a hook failed" 1 3 1 "$passed" "$passed" "$failed_hook"
check "a hook that SKIP skipped" 2 3 0 "$passed" "$passed" "$skipped"
check "a hook fewer than EXPECTED_HOOKS" 2 4 0 "$passed" "$passed" "$passed"
check "a hook more than EXPECTED_HOOKS" 2 2 0 "$passed" "$passed" "$passed"
check "prek exited with another code" 2 3 2 "$passed" "$passed" "$passed"
check "no hook line" 2 3 0 "prek: no configuration found"
check "EXPECTED_HOOKS is empty" 2 '' 0 "$passed"
check "EXPECTED_HOOKS is not a number" 2 three 0 "$passed"
PREK_OVERRIDE=$tmp/missing check "prek is missing" 2 1 0 "$passed"
EXTRA_ARG=extra check "an argument" 2 1 0 "$passed"

echo "prek-count.test.sh: $((cases - failed)) of $cases cases passed"
[[ $failed -eq 0 ]]
