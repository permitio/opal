#!/usr/bin/env bash
# ci-aggregate.sh decides the result of the CI job, the one check the ruleset requires besides
# pre-commit, from the results of the jobs it needs. The CI job in .github/workflows/tests.yml
# runs it with:
#   NEEDS              toJSON(needs): the id and result of each job CI needs
#   EXPECTED_JOBS      the number of jobs CI needs
#   EVENT              github.event_name: pull_request, push or workflow_dispatch
#   PULL_REQUEST_JOBS  the jobs that run on pull requests only (space separated)
#
# Every run selects every job, except that a job in PULL_REQUEST_JOBS is selected on a pull
# request only. A job the run does not select may be skipped. Every other result than success
# fails CI.
#
# Exit codes: 0 when every needed job succeeded or was not selected; 1 when a job failed, was
# cancelled, or was skipped in a run that selects it; 2 when the check did not run: the script
# was given arguments, jq is not installed, NEEDS is not a JSON object of job results or does not
# hold EXPECTED_JOBS of them, PULL_REQUEST_JOBS names a job CI does not need, or the event is not
# one CI knows.
set -euo pipefail

fail() {
  echo "::error title=CI::$*"
  exit 2
}

# contains <list> <word> succeeds when the space-separated list holds the word.
contains() {
  [[ " $1 " == *" $2 "* ]]
}

[[ $# -eq 0 ]] || fail "usage: ci-aggregate.sh (it takes no arguments)"
command -v jq >/dev/null 2>&1 || fail "jq is not installed, so the job results cannot be read"

expected=${EXPECTED_JOBS:-}
[[ $expected =~ ^[1-9][0-9]*$ ]] || fail "EXPECTED_JOBS \"$expected\" is not a positive number"
event=${EVENT:-}
pull_request_jobs=${PULL_REQUEST_JOBS:-}
contains "pull_request push workflow_dispatch" "$event" ||
  fail "CI does not run on the event \"${event//[^a-z_]/}\""

if ! results=$(jq -r 'if type == "object" then to_entries[] | "\(.key)\t\(.value.result)"
  else error("not an object") end' <<<"${NEEDS:-}" 2>/dev/null); then
  fail "NEEDS is not a JSON object of job results"
fi

jobs=''
count=0
while IFS=$'\t' read -r job result; do
  [[ -n $job ]] || continue
  [[ $job =~ ^[A-Za-z0-9_-]+$ ]] ||
    fail "NEEDS has a job id with characters other than letters, digits, - and _"
  jobs+=" $job"
  count=$((count + 1))
done <<<"$results"
[[ $count -eq $expected ]] ||
  fail "$count job results, but EXPECTED_JOBS is $expected; CI did not check every job"

for job in $pull_request_jobs; do
  contains "$jobs" "$job" || fail "PULL_REQUEST_JOBS names $job, which CI does not need"
done

# selected <job> succeeds when the run selects the job.
selected() {
  if contains "$pull_request_jobs" "$1"; then
    [[ $event == pull_request ]]
    return
  fi
  return 0
}

problems=''
notices=''
while IFS=$'\t' read -r job result; do
  [[ -n $job ]] || continue
  case $result in
  success) ;;
  skipped)
    if selected "$job"; then
      problems+=", $job skipped, although a $event run selects it"
    else
      notices+="$job was not selected in a $event run"$'\n'
    fi
    ;;
  failure | cancelled) problems+=", $job $result" ;;
  *) fail "job $job has a result CI does not know" ;;
  esac
done <<<"$results"

# The results are printed with workflow commands stopped; the lines after them are commands.
token=$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')
echo "::stop-commands::$token"
printf '%s\n' "${results//$'\t'/ }"
echo "::$token::"
echo "ci-aggregate: $event run: $count job results"
while IFS= read -r line; do
  [[ -z $line ]] || echo "::notice title=CI::$line"
done <<<"$notices"
if [[ -n $problems ]]; then
  echo "::error title=CI::Jobs that did not succeed in this $event run: ${problems#, }"
  exit 1
fi
echo "ci-aggregate: every job that a $event run selects succeeded"
