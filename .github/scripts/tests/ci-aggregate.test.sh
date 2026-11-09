#!/usr/bin/env bash
# ci-aggregate.test.sh runs .github/scripts/ci-aggregate.sh on job results it makes up and checks
# each exit code: 0 when every selected job succeeded, 1 when one did not, 2 when the check could
# not run. Each case runs the script with only PATH and its own variables set. The pre-commit job
# of .github/workflows/pre-commit.yml runs it; it needs jq.
#
# Exit codes: 0 when every case gave the exit code it wants; 1 otherwise, with each failing case's
# output printed.
set -euo pipefail

script=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)/ci-aggregate.sh
failed=0
cases=0

# check <name> <want exit> <EVENT> <NEEDS> [<PULL_REQUEST_JOBS> [<EXPECTED_JOBS> [<arg>...]]]
check() {
  local name=$1 want=$2 event=$3 needs=$4 pr_jobs=${5:-} expected=${6:-3} got=0 out
  shift 6 2>/dev/null || shift $#
  cases=$((cases + 1))
  out=$(env -i PATH="$PATH" EVENT="$event" NEEDS="$needs" PULL_REQUEST_JOBS="$pr_jobs" \
    EXPECTED_JOBS="$expected" ADVISORY_JOBS="${ADVISORY:-}" "$script" "$@" 2>&1) || got=$?
  if [[ $got -eq $want ]]; then
    echo "ok - $name (exit $got)"
  else
    failed=$((failed + 1))
    echo "FAIL - $name: exit $got, want $want; its output:"
    printf '%s\n' "$out" | sed 's/^::/: :/'
  fi
}

ok='"result":"success"'
all_ok="{\"a\":{$ok},\"b\":{$ok},\"pr\":{$ok}}"
pr_skipped="{\"a\":{$ok},\"b\":{$ok},\"pr\":{\"result\":\"skipped\"}}"

check "every job succeeded on a pull request" 0 pull_request "$all_ok" pr
check "every job succeeded on a push" 0 push "$all_ok" pr
check "a pull-request job skipped on a push" 0 push "$pr_skipped" pr
check "a pull-request job skipped on a manual run" 0 workflow_dispatch "$pr_skipped" pr
check "a pull-request job skipped on a pull request" 1 pull_request "$pr_skipped" pr
check "a job failed" 1 pull_request "{\"a\":{\"result\":\"failure\"},\"b\":{$ok},\"pr\":{$ok}}" pr
check "a job was cancelled" 1 push "{\"a\":{$ok},\"b\":{\"result\":\"cancelled\"},\"pr\":{$ok}}" pr
check "another job skipped on a push" 1 push "{\"a\":{\"result\":\"skipped\"},\"b\":{$ok},\"pr\":{$ok}}" pr
ADVISORY="a" check "ADVISORY_JOBS does not excuse a failure" 1 push \
  "{\"a\":{\"result\":\"failure\"},\"b\":{$ok},\"pr\":{$ok}}" pr
check "fewer results than EXPECTED_JOBS" 2 push "{\"a\":{$ok},\"b\":{$ok}}" pr
check "more results than EXPECTED_JOBS" 2 push "$all_ok" pr 2
check "EXPECTED_JOBS is not a number" 2 push "$all_ok" pr x
check "EXPECTED_JOBS is 0" 2 push '{}' '' 0
check "NEEDS is empty" 2 push '' pr
check "NEEDS is not JSON" 2 push 'not json' pr
check "NEEDS is a list" 2 push '[1,2,3]' pr
check "a result CI does not know" 2 push "{\"a\":{\"result\":\"neutral\"},\"b\":{$ok},\"pr\":{$ok}}" pr
check "a job without a result" 2 push "{\"a\":{},\"b\":{$ok},\"pr\":{$ok}}" pr
check "a job id with other characters" 2 push "{\"a b\":{$ok},\"b\":{$ok},\"pr\":{$ok}}" pr
check "PULL_REQUEST_JOBS names a job CI does not need" 2 pull_request "$all_ok" "pr other"
check "an event CI does not run on" 2 schedule "$all_ok" pr
check "no event" 2 '' "$all_ok" pr
check "an argument" 2 push "$all_ok" pr 3 extra

echo "ci-aggregate.test.sh: $((cases - failed)) of $cases cases passed"
[[ $failed -eq 0 ]]
