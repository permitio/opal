#!/usr/bin/env bash
# digest.sh writes the weekly security digest and posts it to Slack. The digest job in
# .github/workflows/security.yml runs it every week, and the digest is sent even when nothing
# needs attention. It runs the same way on any clone. It needs the network, gh, curl and jq, and
# reads:
#
#   GITHUB_REPOSITORY           owner/name of the repository; required
#   GH_TOKEN                    the token gh reads the pull requests, the runs and the releases
#                               with
#   SECURITY_SLACK_WEBHOOK_URL  the webhook that the digest is posted to; without it the digest
#                               is not posted, and the job summary says so
#   GITHUB_SERVER_URL and GITHUB_RUN_ID, which CI sets: the run's URL
#   DIGEST_NOW                  the time of the digest, in seconds since 1970-01-01 UTC, instead
#                               of the clock's, for tests
#
# It reads each secret, unsets it, and passes it to the one command that needs it: the token to
# gh and the webhook to notify.sh. The digest has three sections, in Slack's text format, with
# every value from outside the repository escaped once:
#
#   Dependabot pull requests  every open pull request of dependabot[bot] with its age; one open
#                             14 days or more needs attention
#   Last security scan        the result of the newest security-scan job of security.yml on
#                             master, among the 30 newest scheduled runs and the 30 newest manual
#                             runs; one that did not succeed, or none, needs attention
#   Release binaries          for each entry of .github/binaries.lock, the newest stable release
#                             of its GitHub project; a newer one published at least 7 days (168
#                             hours) ago needs attention
#
# A section that cannot be read says so in the digest. notify.sh posts the digest under the line
# "<repo> security digest: <result>. <run URL>", where the result counts what needs attention, or
# says that the digest did not complete. Everything until notify.sh runs is printed with workflow
# commands stopped. The work files stay in a temporary directory under RUNNER_TEMP (or TMPDIR),
# which the runner or the system clears.
#
# Exit codes: 0 when every section was read and the digest posted, or the webhook is not set; 1
# when the digest could not be posted; 2 when a section could not be read (the digest is posted
# all the same), or the digest did not run: the arguments are wrong, jq, gh or curl is missing,
# GITHUB_REPOSITORY is not owner/name, or DIGEST_NOW is not a number.
# shellcheck disable=SC2329 # section runs each section's function by name.
set -euo pipefail

token=$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')
echo "::stop-commands::$token"
stopped=true
# resume prints the line that resumes workflow commands, once; it runs on exit too.
resume() {
  if [[ $stopped == true ]]; then
    echo "::$token::"
    stopped=false
  fi
}
trap resume EXIT

fail() {
  echo "digest: $*"
  echo "digest: DID NOT RUN"
  exit 2
}

[[ $# -eq 0 ]] || fail "usage: digest.sh (it takes no arguments)"
for tool in jq gh curl; do
  command -v "$tool" >/dev/null 2>&1 || fail "$tool is not installed"
done
root=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
cd -- "$root"

gh_token=${GH_TOKEN:-}
webhook=${SECURITY_SLACK_WEBHOOK_URL:-}
unset GH_TOKEN GITHUB_TOKEN SECURITY_SLACK_WEBHOOK_URL SLACK_WEBHOOK_URL
repo=${GITHUB_REPOSITORY:-}
repo_re='^[A-Za-z0-9-]+/[A-Za-z0-9_.-]+$'
[[ $repo =~ $repo_re ]] || fail "GITHUB_REPOSITORY \"$repo\" is not owner/name; set it to the" \
  "repository to report on, as CI does"
now=${DIGEST_NOW:-$(date -u +%s)}
[[ $now =~ ^[0-9]+$ ]] || fail "DIGEST_NOW \"$now\" is not a number of seconds"

work=$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/digest.XXXXXX") ||
  fail "creating a temporary directory failed"
digest=$work/digest
: >"$digest"
problems=0
attention=0
# esc escapes a value for Slack's text format; days is the number of whole days from a time, in
# seconds, to now; ver is a version's numbers, for comparing versions.
# shellcheck disable=SC2016 # $now is a jq variable, which jq --argjson sets
defs='def esc: gsub("&"; "&amp;") | gsub("<"; "&lt;") | gsub(">"; "&gt;");
  def days: ($now - .) / 86400 | floor;
  def ver: ltrimstr("v") | split(".") | map(try tonumber catch -1);'

# api runs gh api with the token.
api() {
  GH_TOKEN=$gh_token gh api "$@"
}

# section <title> <function> writes a section of the digest. The function prints its lines and
# returns 0, or 2 when it could not read what it reports, and writes any line for the run's log to
# file descriptor 3. It runs with errexit off, so it checks each command it runs.
section() {
  local code=0
  printf '*%s*\n' "$1" >>"$digest"
  "$2" 3>&1 >>"$digest" 2>"$work/error" || code=$?
  if [[ $code -ne 0 ]]; then
    problems=$((problems + 1))
    echo "• Could not be read; the run's log says why." >>"$digest"
    echo "digest: $1 could not be read:"
    cat -- "$work/error"
  fi
}

# need <count> adds the count of items that need attention.
need() {
  attention=$((attention + $1))
}

dependabot_pulls() {
  local flagged
  api --paginate "repos/$repo/pulls?state=open&per_page=100" >"$work/pulls.json" || return 2
  jq -se 'all(.[]; type == "array") and length > 0' "$work/pulls.json" >/dev/null || {
    echo "digest: gh returned something other than lists of pull requests" >&2
    return 2
  }
  jq -s --argjson now "$now" "$defs"'[add[] | select(.user.login == "dependabot[bot]")
    | {number, title, url: .html_url, days: (.created_at | fromdateiso8601 | days)}]
    | sort_by(-.days, .number)' "$work/pulls.json" >"$work/dependabot.json" || return 2
  flagged=$(jq '[.[] | select(.days >= 14)] | length' "$work/dependabot.json") || return 2
  jq -r "$defs"'if length == 0 then "• None open." else .[]
    | "• <\(.url)|#\(.number)> \(.title | esc): open \(.days) days"
      + (if .days >= 14 then ", *14 days or more*" else "" end) end' \
    "$work/dependabot.json" || return 2
  need "$flagged"
}

last_scan() {
  local ids id line event
  # Each event is read on its own, so that one kind of run does not crowd the other out.
  for event in schedule workflow_dispatch; do
    api "repos/$repo/actions/workflows/security.yml/runs?branch=master&event=$event&per_page=30" \
      >"$work/runs-$event.json" || return 2
  done
  ids=$(jq -rs '[.[].workflow_runs[] | select(.event == "schedule"
      or .event == "workflow_dispatch")] | sort_by(.created_at) | reverse | .[]
    | .id | tostring | select(test("^[0-9]+$"))' "$work/runs-schedule.json" \
    "$work/runs-workflow_dispatch.json") || return 2
  for id in $ids; do
    api "repos/$repo/actions/runs/$id/jobs?per_page=100" >"$work/jobs.json" || return 2
    line=$(jq -r "$defs"'[.jobs[] | select(.name == "security-scan" and .conclusion != null
      and .conclusion != "skipped")][0] // empty
      | "\(.conclusion) • <\(.html_url)|\(.conclusion | esc)> on \(.completed_at[0:10])"' \
      "$work/jobs.json") || return 2
    if [[ -n $line ]]; then
      echo "${line#* }"
      [[ ${line%% *} == success ]] || need 1
      return 0
    fi
  done
  echo "• No security-scan job in the 30 newest scheduled runs or the 30 newest manual runs of" \
    "security.yml on master."
  need 1
}

release_binaries() {
  local name version url project path
  awk '/^\[/ { if (name != "") print name, version, url; name = substr($0, 2, length($0) - 2)
      version = ""; url = ""; next }
    /^version[[:space:]]*=/ { sub(/^version[[:space:]]*=[[:space:]]*/, ""); version = $0 }
    /^url[[:space:]]*=/ { sub(/^url[[:space:]]*=[[:space:]]*/, ""); url = $0 }
    END { if (name != "") print name, version, url }' .github/binaries.lock >"$work/lock" ||
    return 2
  [[ -s $work/lock ]] || {
    echo "digest: .github/binaries.lock has no entries" >&2
    return 2
  }
  while read -r name version url; do
    project_re='^https://github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/releases/download/'
    if [[ ! $url =~ $project_re ]]; then
      echo "• $name $version: its url is not a GitHub release, so check it by hand."
      need 1
      continue
    fi
    project=${BASH_REMATCH[1]}
    path="repos/$project/releases?per_page=30"
    api "$path" >"$work/releases.json" || return 2
    jq -r --argjson now "$now" --arg name "$name" --arg version "$version" "$defs"'
      if type != "array" then error("GitHub returned something other than a list of releases")
      else . end
      | [.[] | select(.draft == false and .prerelease == false and .published_at != null)
        | {version: (.tag_name | ltrimstr("v")), date: .published_at,
          ready: ((.published_at | fromdateiso8601) + 7 * 86400)}
        | select(.version | ver > ($version | ver))] | sort_by(.version | ver)
      | (map(select(.ready <= $now)) | last) as $adopt
      | (map(select(.ready > $now)) | last) as $later
      | if length == 0 then "• \($name) \($version) is the newest release."
        else (if $adopt == null then empty
          else "need • \($name) \($version): \($adopt.version | esc), published "
            + "\($adopt.date[0:10]), can be adopted." end),
          (if $later == null then empty
          else "• \($name) \($version): \($later.version | esc), published "
            + "\($later.date[0:10]), can be adopted from \($later.ready | strftime("%Y-%m-%d"))."
          end) end' "$work/releases.json" >"$work/release.txt" || return 2
    if grep -q '^need ' "$work/release.txt"; then
      need 1
    fi
    sed 's/^need //' "$work/release.txt"
  done <"$work/lock"
}

section "Dependabot pull requests" dependabot_pulls
section "Last security scan" last_scan
section "Release binaries" release_binaries
cat -- "$digest"

result="nothing needs attention"
if [[ $problems -gt 0 ]]; then
  result="did not complete: $problems sections could not be read"
elif [[ $attention -gt 0 ]]; then
  result="$attention items need attention"
fi
resume
if [[ -n ${GITHUB_STEP_SUMMARY:-} ]]; then
  fence='~~~'
  printf '## Security digest\n\n%s\n\n%s\n%s\n%s\n' "$result" "$fence" "$(cat -- "$digest")" \
    "$fence" >>"$GITHUB_STEP_SUMMARY" || fail "writing the job summary failed"
fi
posted=0
SECURITY_SLACK_WEBHOOK_URL=$webhook .github/scripts/notify.sh "security digest" "$result" \
  "$digest" || posted=$?
if [[ $problems -gt 0 ]]; then
  echo "digest: DID NOT COMPLETE: $problems sections could not be read"
  exit 2
fi
exit "$posted"
