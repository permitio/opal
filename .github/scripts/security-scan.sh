#!/usr/bin/env bash
# security-scan.sh --trufflehog run|skip runs the scheduled security scan, writes its report to
# the job summary and posts it to Slack. The security-scan job in .github/workflows/security.yml
# runs it twice a week and on a manual run; it runs the same way on any clone with the full
# history. It needs the network, jq, gh and curl, and reads these variables:
#
#   GITHUB_REPOSITORY               owner/name of the repository, which the report names and
#                                   whose Dependabot alerts it reads; required
#   DEPENDABOT_ALERTS_TOKEN         a GitHub App installation token that can read the
#                                   repository's Dependabot alerts, which the GITHUB_TOKEN
#                                   cannot (security.yml mints it from SECURITY_APP_CLIENT_ID and
#                                   SECURITY_APP_PRIVATE_KEY); without it that source is skipped,
#                                   and the report says so
#   GITLEAKS_HISTORY_ACCEPT_SHA256  the sha256 digests of the accepted history findings' gitleaks
#                                   fingerprints, one per line
#   SECURITY_SLACK_WEBHOOK_URL      the webhook that the report is posted to; without it the
#                                   report is not posted, and the job summary says so
#   GITHUB_STEP_SUMMARY, GITHUB_SERVER_URL and GITHUB_RUN_ID, which CI sets: the job summary and
#   the run's URL
#
# It reads each secret, unsets it, and passes it to the one command that needs it: the token to
# gh, the digests to its own comparison and the webhook to notify.sh. No scanner gets any of them.
#
# Each source below is one scan of the report, with a result of its own: 0 when it completed and
# found nothing, 1 when it completed with findings, 2 when it did not complete, and 3 when it was
# skipped because a secret it needs is not set.
#
#   floor              trivy.sh report on the lowest versions the published packages' ranges
#                      admit (vuln.sh --prepare resolves them)
#   ceiling            the same on the newest versions they admit
#   pypi-latest        the same on the latest opal-client and opal-server releases on PyPI, as
#                      pip resolves them for an application
#   image-opal-server  trivy.sh report on permitio/opal-server:latest, the latest GA image
#   image-opal-client  trivy.sh report on permitio/opal-client:latest
#   dependabot-alerts  the open Dependabot alerts, read with gh api and DEPENDABOT_ALERTS_TOKEN;
#                      the log prints their count only, and the Slack report lists them
#   history-secrets    gitleaks over the full history of a bare mirror of the repository
#   verified-secrets   with --trufflehog run only: TruffleHog --results=verified over the mirror
#
# The history scan gives gitleaks .gitleaks.toml by path and runs it from an empty directory with
# an empty ignore file, without any GITLEAKS_ variable or git configuration of the user or the
# system, with --redact and --text. Its log and the report print counts only: "history: N
# findings, M accepted, K new". A finding is accepted when the sha256 of its fingerprint is in
# GITLEAKS_HISTORY_ACCEPT_SHA256; the new ones are listed in the Slack report only, as private
# findings. Every accepted digest must match a finding: one that matches none makes the source
# exit 2, since the scan may have missed part of the history. Without the variable, every finding
# is new, and the source's state says so. TruffleHog's output and log are never printed: a
# verified secret is counted in the log and listed, redacted, in the Slack report only.
# TruffleHog's log must count a scan that read something and verified as many secrets as it
# printed, or the source exits 2. A value that a scanner or GitHub reports is cut to fit the
# report, so that no finding is lost.
#
# The report lists findings and passes; a source that did not complete fails, and so does a
# secret that TruffleHog verified. It goes to the job summary, where private findings are counted
# only, and in Slack's format to notify.sh, which posts it under the line
# "<repo> security-scan: <verdict>. <run URL>". Everything until the report is printed with
# workflow commands stopped. The work files stay in a temporary directory under RUNNER_TEMP (or
# TMPDIR), which the runner or the system clears.
#
# security-scan.sh --history-digests <file> runs only the history scan, on a local clone, and
# writes the sha256 digest of each finding's fingerprint to the file, one per line, for the
# maintainer who sets GITLEAKS_HISTORY_ACCEPT_SHA256; it prints each digest with its finding. It
# refuses to run in GitHub Actions, whose log is public, and to write the file inside the
# repository, where it could be committed.
#
# Exit codes: 0 when every source completed or was skipped and no secret was verified; 1 when
# TruffleHog verified a secret, or the report could not be posted; 2 when a source did not
# complete, the arguments are wrong, jq is missing, GITHUB_REPOSITORY is not owner/name, or the
# report cannot be written.
# shellcheck disable=SC2329 # run_source runs each source's function by name.
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
  echo "security-scan: $*"
  echo "security-scan: DID NOT RUN"
  exit 2
}

usage="usage: security-scan.sh --trufflehog run|skip | --history-digests <file>"
trufflehog=''
digests_file=''
if [[ $# -eq 2 && $1 == --trufflehog && ($2 == run || $2 == skip) ]]; then
  trufflehog=$2
elif [[ $# -eq 2 && $1 == --history-digests && -n $2 ]]; then
  [[ ${GITHUB_ACTIONS:-} != true ]] || fail "--history-digests prints where each finding is," \
    "and the log of GitHub Actions is public; run it on your own clone"
  digests_file=$2
  [[ $digests_file == /* ]] || digests_file=$PWD/$digests_file
else
  fail "$usage"
fi
for tool in jq gh curl; do
  command -v "$tool" >/dev/null 2>&1 || fail "$tool is not installed"
done
root=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
if [[ -n $digests_file ]]; then
  # The digests belong in the secret only: a file in the clone could be committed.
  digests_dir=$(CDPATH='' cd -- "$(dirname -- "$digests_file")" && pwd -P) ||
    fail "the directory of $digests_file does not exist"
  physical_root=$(cd -- "$root" && pwd -P) || fail "reading the path of $root failed"
  [[ $digests_dir != "$physical_root" && $digests_dir != "$physical_root"/* ]] ||
    fail "$digests_file is inside the repository; write the digests to a file outside the clone"
fi
cd -- "$root"

alerts_token=${DEPENDABOT_ALERTS_TOKEN:-}
webhook=${SECURITY_SLACK_WEBHOOK_URL:-}
accept_list=${GITLEAKS_HISTORY_ACCEPT_SHA256:-}
unset DEPENDABOT_ALERTS_TOKEN SECURITY_SLACK_WEBHOOK_URL SLACK_WEBHOOK_URL GH_TOKEN GITHUB_TOKEN
for var in $(compgen -e); do
  [[ $var != GITLEAKS_* && $var != TRUFFLEHOG_* ]] || unset "$var"
done
repo=${GITHUB_REPOSITORY:-}
repo_re='^[A-Za-z0-9-]+/[A-Za-z0-9_.-]+$'
if [[ -z $digests_file ]]; then
  [[ $repo =~ $repo_re ]] || fail "GITHUB_REPOSITORY \"$repo\" is not owner/name; set it to" \
    "the repository whose alerts to read, as CI does"
fi

work=$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/security-scan.XXXXXX") ||
  fail "creating a temporary directory failed"
results=$work/results
mkdir "$results" "$work/empty"

# lock_version <name> prints the version .github/binaries.lock pins for name, read the way
# fetch-tool.sh reads it.
lock_version() {
  awk -v entry="[$1]" '/^\[/ { found = ($0 == entry); next }
    found && /^version[[:space:]]*=/ {
      sub(/^version[[:space:]]*=[[:space:]]*/, ""); sub(/[[:space:]]+$/, ""); print; exit
    }' .github/binaries.lock
}

# install_tool <name> <version flag> <prefix> installs bin/<name> with fetch-tool.sh and checks
# that <name> <version flag> prints <prefix> and the version the lock pins.
install_tool() {
  local name=$1 want have
  want=$(lock_version "$name") || return 1
  if [[ -z $want ]]; then
    echo "security-scan: .github/binaries.lock has no version for $name"
    return 1
  fi
  .github/scripts/fetch-tool.sh "$name" >/dev/null || {
    echo "security-scan: installing $name with .github/scripts/fetch-tool.sh failed"
    return 1
  }
  have=$("bin/$name" "$2" 2>&1) || have=''
  if [[ $have != "$3$want" ]]; then
    echo "security-scan: bin/$name reports \"$have\", want version $want from" \
      ".github/binaries.lock"
    return 1
  fi
}

# run_source <name> <command>... runs a source's command, which prints its output and returns
# the source's exit code, and records both for the report. A function that run_source runs checks
# each command it runs, since errexit does not stop it.
run_source() {
  local name=$1 code=0
  shift
  echo "security-scan: $name"
  "$@" >"$results/$name.out" 2>&1 || code=$?
  cat -- "$results/$name.out"
  echo "$code" >"$results/$name.exit"
}

# not_prepared prints that vuln.sh --prepare failed, and returns 2.
not_prepared() {
  echo "security-scan: vuln.sh --prepare failed, so this tree was not scanned"
  return 2
}

# scan_target <name> <trivy.sh target> runs trivy.sh report on the target, writes its findings to
# the source's findings file, and returns 2 when the scan did not complete, otherwise 1 when it
# found something, and 0.
scan_target() {
  local name=$1 code=0
  .github/scripts/trivy.sh report "$2" "$results/$name.findings" || code=$?
  if [[ $code -ne 0 ]]; then
    return 2
  fi
  if [[ ! -f $results/$name.findings ]]; then
    echo "security-scan: trivy.sh wrote no findings file"
    return 2
  fi
  [[ ! -s $results/$name.findings ]] || return 1
}

# scan_tree <name> <requirements file> scans one resolved tree.
scan_tree() {
  local pins code=0
  pins=$(grep -cE '^[A-Za-z0-9].*==' "$2") || pins=0
  echo "$pins pinned packages" >"$results/$1.state"
  scan_target "$1" "$2" || code=$?
  return "$code"
}

# scan_pypi resolves the latest opal-client and opal-server releases as an application does, and
# scans the result.
scan_pypi() {
  local dir=$work/pypi versions code=0
  mkdir -- "$dir" || return 2
  printf 'opal-client\nopal-server\n' >"$dir/requirements.in" || return 2
  bin/uv pip compile --no-config --no-header --quiet --index-url https://pypi.org/simple \
    --python-version 3.12 --python-platform x86_64-manylinux_2_28 "$dir/requirements.in" \
    -o "$dir/requirements.txt" || {
    echo "security-scan: uv could not resolve opal-client and opal-server from PyPI"
    return 2
  }
  versions=$(grep -E '^opal-(client|server)==' "$dir/requirements.txt" | sort | paste -sd ' ' -) ||
    return 2
  echo "security-scan: PyPI resolves $versions"
  echo "$versions" >"$results/pypi-latest.state"
  scan_target pypi-latest "$dir/requirements.txt" || code=$?
  return "$code"
}

# scan_image <name> <image> scans a published image.
scan_image() {
  local code=0
  echo "$2" >"$results/$1.state"
  scan_target "$1" "image:$2" || code=$?
  return "$code"
}

# fit is the jq that keeps a value from outside within what the report shows, so that a long or
# odd value never breaks it, and a finding is never lost: clip($n) turns each control character
# into a space and cuts the value to at most $n bytes, the last three of them "..."; link drops a
# URL that is not a plain https link or is longer than 300 bytes.
# shellcheck disable=SC2016 # $n is a jq variable
fit='def clip($n): gsub("\\p{Cc}"; " ") | if utf8bytelength <= $n then .
    else .[0:$n] | until(utf8bytelength <= $n - 3; .[0:-1]) + "..." end;
  def link: if test("^https://[^\\s<>|()\\[\\]\"]+$") and utf8bytelength <= 300 then .
    else "" end;'

# scan_alerts reads the open Dependabot alerts, and returns the source's exit code. The alerts
# are private findings: the log prints their count only.
scan_alerts() {
  local name=dependabot-alerts count
  if [[ -z $alerts_token ]]; then
    echo "security-scan: no Dependabot alerts token (the security GitHub App's" \
      "SECURITY_APP_CLIENT_ID and SECURITY_APP_PRIVATE_KEY are not set), so the open" \
      "Dependabot alerts were not read; the GITHUB_TOKEN cannot read them"
    echo "no Dependabot alerts token: SECURITY_APP_CLIENT_ID and SECURITY_APP_PRIVATE_KEY are not set" >"$results/$name.state"
    return 3
  fi
  if ! GH_TOKEN=$alerts_token gh api --paginate \
    "repos/$repo/dependabot/alerts?state=open&per_page=100" >"$work/alerts.json"; then
    echo "security-scan: gh api could not read the open Dependabot alerts of $repo"
    return 2
  fi
  if ! jq -se 'all(.[]; type == "array" and all(.[]; type == "object")) and length > 0' \
    "$work/alerts.json" >/dev/null 2>&1; then
    echo "security-scan: gh api returned something other than lists of alerts"
    return 2
  fi
  jq -sc "$fit"'add | .[] | {id: .security_advisory.ghsa_id, package:
    (.security_vulnerability.package.name | clip(200)), version:
    (.security_vulnerability.vulnerable_version_range // "" | clip(200)),
    severity: (.security_advisory.severity // ""),
    fix: (.security_vulnerability.first_patched_version.identifier // "" | clip(200)),
    url: ("https://github.com/advisories/" + .security_advisory.ghsa_id | link)}' \
    "$work/alerts.json" >"$results/$name.findings" ||
    {
      echo "security-scan: the alerts do not have the fields of a Dependabot alert"
      return 2
    }
  count=$(wc -l <"$results/$name.findings" | tr -d ' ')
  echo "security-scan: $repo has $count open Dependabot alerts"
  echo "$count open alerts" >"$results/$name.state"
  [[ $count -eq 0 ]] || return 1
}

# sha256 prints the sha256 of its standard input in lowercase hex.
sha256() {
  local sum
  if command -v sha256sum >/dev/null 2>&1; then
    sum=$(sha256sum)
  else
    sum=$(shasum -a 256)
  fi
  echo "${sum%% *}"
}

# mirror makes a bare mirror of the repository's every ref in $work/mirror.git, once.
mirror() {
  local shallow
  [[ ! -d $work/mirror.git ]] || return 0
  shallow=$(git rev-parse --is-shallow-repository) || return 1
  if [[ $shallow != false ]]; then
    echo "security-scan: the repository is a shallow clone, which lacks part of the history;" \
      "clone the full history (fetch-depth: 0)"
    return 1
  fi
  GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 git clone --quiet --mirror --no-local \
    -- "$root" "$work/mirror.git" || return 1
}

# scan_history runs gitleaks over the mirror's full history. It leaves the findings in
# $work/history.json and the digest of each finding's fingerprint, in order, in
# $work/history.digests, prints counts only, and returns 0, or 2 when the scan did not complete.
scan_history() {
  local want code=0 commits findings esc plain
  install_tool gitleaks version '' || return 2
  mirror || return 2
  commits=$(git -C "$work/mirror.git" rev-list --all --count) || return 2
  if [[ $commits -eq 0 ]]; then
    echo "security-scan: the mirror holds no commit, so there is no history to scan"
    return 2
  fi
  : >"$work/ignore" || return 2
  want=$(lock_version gitleaks)
  (cd -- "$work/empty" && GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 \
    "$root/bin/gitleaks" git --no-banner --redact --exit-code 0 \
    --config "$root/.gitleaks.toml" --gitleaks-ignore-path "$work/ignore" \
    --ignore-gitleaks-allow --report-format json --report-path "$work/history.json" \
    "--log-opts=--full-history --all --text" "$work/mirror.git") >"$work/gitleaks.log" 2>&1 ||
    code=$?
  # The log without the colors gitleaks gives it, which the job summary would show as text.
  esc=$'\033'
  plain=$(sed "s/$esc\\[[0-9;]*m//g" "$work/gitleaks.log") || return 2
  if [[ -n $plain ]]; then
    printf '%s\n' "$plain"
  fi
  if [[ $code -ne 0 ]]; then
    echo "security-scan: gitleaks exited $code"
    return 2
  fi
  if grep -Eq '^[^ ]+ (ERR|FTL) ' <<<"$plain"; then
    echo "security-scan: gitleaks logged an error, so it may not have scanned every commit"
    return 2
  fi
  findings=$(jq -e 'if type == "array" and all(.[]; type == "object" and
    (.Fingerprint | type == "string" and . != "")) then length else error("not findings") end' \
    "$work/history.json" 2>/dev/null) || {
    echo "security-scan: gitleaks wrote no report, or one that is not a JSON list of findings"
    return 2
  }
  : >"$work/history.digests"
  jq -r '.[].Fingerprint' "$work/history.json" | while IFS= read -r fingerprint; do
    printf '%s' "$fingerprint" | sha256 >>"$work/history.digests"
  done
  if [[ $(wc -l <"$work/history.digests" | tr -d ' ') -ne $findings ]]; then
    echo "security-scan: the gitleaks report has a fingerprint that is not one line"
    return 2
  fi
  echo "security-scan: gitleaks $want scanned $commits commits of every ref"
}

# check_history compares the history's findings with the accepted digests, and returns the
# source's exit code.
check_history() {
  local name=history-secrets total accepted=0 unmatched new_list='' index=0 digest note='' state
  scan_history || return 2
  printf '%s\n' "$accept_list" | tr -d ' \t\r' | sed '/^$/d' >"$work/accepted" || return 2
  if grep -Evq '^[0-9a-f]{64}$' "$work/accepted"; then
    echo "security-scan: GITLEAKS_HISTORY_ACCEPT_SHA256 holds a line that is not a sha256" \
      "digest in lowercase hex"
    return 2
  fi
  if [[ -n $(sort "$work/accepted" | uniq -d) ]]; then
    echo "security-scan: GITLEAKS_HISTORY_ACCEPT_SHA256 lists a digest twice"
    return 2
  fi
  if [[ ! -s $work/accepted ]]; then
    note="; GITLEAKS_HISTORY_ACCEPT_SHA256 is not set, so every finding is new"
  fi
  : >"$work/matched"
  while IFS= read -r digest; do
    if grep -qxF "$digest" "$work/accepted"; then
      accepted=$((accepted + 1))
      echo "$digest" >>"$work/matched"
    else
      new_list+="${new_list:+,}$index"
    fi
    index=$((index + 1))
  done <"$work/history.digests"
  total=$index
  # grep exits 1 when every accepted digest matched a finding.
  unmatched=$(grep -cvxFf "$work/matched" "$work/accepted") || [[ $? -eq 1 ]] || {
    echo "security-scan: grep could not compare the accepted digests with the findings"
    return 2
  }
  if [[ ! -s $work/matched ]]; then
    unmatched=$(wc -l <"$work/accepted" | tr -d ' ')
  fi
  state="history: $total findings, $accepted accepted, $((total - accepted)) new$note"
  echo "$state"
  echo "$state" >"$results/$name.state"
  if [[ $unmatched -gt 0 ]]; then
    echo "security-scan: $unmatched accepted digests in GITLEAKS_HISTORY_ACCEPT_SHA256 match" \
      "no finding: the scan may have missed part of the history, or the list is out of date"
    return 2
  fi
  jq -c --argjson new "[$new_list]" "$fit"'. as $all | $new[] | $all[.] | {id: .RuleID,
    package: ("\(.File):\(.StartLine)" | clip(200)), version: (.Commit // "" | .[0:12]),
    fix: "revoke the secret, then add the sha256 of its fingerprint to the accepted digests"}' \
    "$work/history.json" >"$results/$name.findings" || return 2
  [[ $total -eq $accepted ]] || return 1
}

# check_verified runs TruffleHog over the mirror with --results=verified, and returns the
# source's exit code. Its output and its log may hold the secrets it found, so neither is
# printed. The log ends with the count of what it scanned, which must show that it read
# something and verified as many secrets as it printed.
check_verified() {
  local name=verified-secrets code=0 verified scanned
  install_tool trufflehog --version 'trufflehog ' || return 2
  mirror || return 2
  (cd -- "$work/empty" && GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 \
    "$root/bin/trufflehog" git "file://$work/mirror.git" --results=verified --json \
    --no-update --no-ignore-tag --fail-on-scan-errors) >"$work/trufflehog.json" \
    2>"$work/trufflehog.log" || code=$?
  if [[ $code -ne 0 ]]; then
    echo "security-scan: trufflehog exited $code; its log may hold secrets, so run it on your" \
      "own clone to see why"
    return 2
  fi
  verified=$(jq -se 'if all(.[]; type == "object") then map(select(.Verified == true)) | length
    else error("not results") end' "$work/trufflehog.json" 2>/dev/null) || {
    echo "security-scan: TruffleHog's output is not JSON results"
    return 2
  }
  scanned=$(jq -nR --argjson verified "$verified" '[inputs | fromjson? | objects
    | select(.msg == "finished scanning")] | last
    | (.chunks | type) == "number" and .chunks > 0 and .verified_secrets == $verified' \
    "$work/trufflehog.log" 2>/dev/null) || scanned=false
  if [[ $scanned != true ]]; then
    echo "security-scan: TruffleHog's log does not count a scan that read something and" \
      "verified the $verified secrets it printed, so it may not have scanned the history"
    return 2
  fi
  jq -sc "$fit"'.[] | select(.Verified == true) | .SourceMetadata.Data.Git as $git | {
    id: (.DetectorName // "unknown"),
    package: ("\($git.file // ""):\($git.line // 0)" | clip(200)),
    version: ($git.commit // "" | .[0:12]), severity: "critical",
    fix: ("revoke it now: TruffleHog verified that it works ("
      + (.Redacted // "" | clip(80)) + ")")}' \
    "$work/trufflehog.json" >"$results/$name.findings" || return 2
  echo "security-scan: TruffleHog verified secrets: $verified"
  echo "TruffleHog verified secrets: $verified" >"$results/$name.state"
  [[ $verified -eq 0 ]] || return 1
}

if [[ -n $digests_file ]]; then
  code=0
  scan_history || code=$?
  [[ $code -eq 0 ]] || fail "the history scan did not complete"
  cp -- "$work/history.digests" "$digests_file" || fail "writing $digests_file failed"
  jq -r '.[] | "\(.RuleID) \(.File):\(.StartLine) commit \(.Commit // "" | .[0:12])"' \
    "$work/history.json" | paste -d ' ' "$work/history.digests" -
  echo "security-scan: wrote the digests of $(wc -l <"$digests_file" | tr -d ' ') findings to" \
    "$digests_file"
  exit 0
fi

echo "security-scan: preparing uv, Trivy and the trees with vuln.sh"
if .github/scripts/vuln.sh --prepare "$work/trees"; then
  run_source floor scan_tree floor "$work/trees/floor/requirements.txt"
  run_source ceiling scan_tree ceiling "$work/trees/ceiling/requirements.txt"
  run_source pypi-latest scan_pypi
  run_source image-opal-server scan_image image-opal-server permitio/opal-server:latest
  run_source image-opal-client scan_image image-opal-client permitio/opal-client:latest
else
  for name in floor ceiling pypi-latest image-opal-server image-opal-client; do
    run_source "$name" not_prepared
  done
fi
run_source dependabot-alerts scan_alerts
run_source history-secrets check_history
names=(floor ceiling pypi-latest image-opal-server image-opal-client dependabot-alerts
  history-secrets)
private=(dependabot-alerts history-secrets)
if [[ $trufflehog == run ]]; then
  run_source verified-secrets check_verified
  names+=(verified-secrets)
  private+=(verified-secrets)
fi

# The report. Each source's line says its result; the findings follow, the most severe first and
# those with a fix first within a severity, at most 20 per source. Private findings are counted
# in the job summary and listed in Slack only.
# shellcheck disable=SC2016 # jq variables
order='def rank: {"critical": 0, "high": 1, "medium": 2, "low": 3}[.severity // ""] // 4;
  def counts: group_by(.severity // "") | map("\(length) \(.[0].severity // "" |
    if . == "" then "unknown" else . end)") | join(", ");
  sort_by([rank, (if (.fix // "") == "" then 1 else 0 end), .id])'
summary=$work/summary.md
slack=$work/report.slack
incomplete=0
verified_fail=false
with_findings=0
{
  echo "| Source | Result | Detail |"
  echo "|---|---|---|"
} >"$work/table.md"
: >"$work/details.md"
: >"$slack"
for name in "${names[@]}"; do
  code=$(cat -- "$results/$name.exit")
  state=''
  if [[ -f $results/$name.state ]]; then
    state=$(head -n 1 "$results/$name.state")
  fi
  findings=$results/$name.findings
  count=0
  if [[ -f $findings ]]; then
    count=$(wc -l <"$findings" | tr -d ' ')
  fi
  is_private=false
  for each in "${private[@]}"; do
    [[ $each != "$name" ]] || is_private=true
  done
  case $code in
  0) result="clean" ;;
  1)
    result="$count findings"
    with_findings=$((with_findings + 1))
    [[ $name != verified-secrets ]] || verified_fail=true
    ;;
  3) result="skipped" ;;
  *)
    result="did not complete"
    incomplete=$((incomplete + 1))
    ;;
  esac
  detail=$state
  # The severities of the findings that have one: the vulnerabilities and the alerts.
  if [[ $count -gt 0 ]] && jq -se 'any(.[]; (.severity // "") != "")' "$findings" >/dev/null; then
    detail+="${detail:+; }$(jq -rs "$order"' | counts' "$findings")"
  fi
  if [[ $code -eq 2 ]]; then
    detail+="${detail:+; }see the job log"
  fi
  printf '| %s | %s | %s |\n' "$name" "$result" "$(sed 's/|/\\|/g; s/</\&lt;/g' <<<"$detail")" \
    >>"$work/table.md"
  printf '*%s*: %s%s\n' "$name" "$result" "$(sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g' \
    <<<"${detail:+ ($detail)}")" >>"$slack"
  [[ $count -gt 0 ]] || continue
  jq -rs "$fit$order"' | def esc: gsub("&"; "&amp;") | gsub("<"; "&lt;") | gsub(">"; "&gt;");
    (.[0:20][] | "• " + (if (.url // "") != "" then "<\(.url)|\(.id | esc)>" else (.id | esc) end)
      + " \(.package | esc) \(.version // "" | esc)"
      + (if (.severity // "") != "" then ": \(.severity)" else "" end)
      + (if (.fix // "") != "" then ", \(.fix | esc | if test("^[0-9]") then "fixed in " + .
         else . end)" else "" end)),
    (if length > 20 then "• and \(length - 20) more" else empty end)' "$findings" >>"$slack" ||
    fail "writing the Slack report failed"
  [[ $is_private == false ]] || continue
  {
    printf '\n### %s\n\n' "$name"
    jq -rs "$order"' | def md: gsub("[|`]"; "") | gsub("<"; "&lt;");
      (.[0:20][] | "- `\(.id | md)` \(.package | md) \(.version // "" | md)"
        + (if (.severity // "") != "" then ": \(.severity)" else "" end)
        + (if (.fix // "") != "" then ", fixed in \(.fix | md)" else "" end)),
      (if length > 20 then "- and \(length - 20) more" else empty end)' "$findings"
  } >>"$work/details.md" || fail "writing the job summary failed"
done

if [[ $incomplete -gt 0 ]]; then
  verdict="DID NOT RUN: $incomplete sources did not complete"
  code=2
elif [[ $verified_fail == true ]]; then
  verdict="FAIL: TruffleHog verified a secret that works"
  code=1
else
  verdict="PASS: every source completed or was skipped; $with_findings with findings"
  code=0
fi
{
  printf '## Security scan\n\n%s\n\n' "$verdict"
  cat -- "$work/table.md"
  echo
  echo "Private findings (Dependabot alerts, secrets) are counted here and listed in Slack only."
  cat -- "$work/details.md"
} >"$summary" || fail "writing the job summary failed"

resume
cat -- "$summary"
if [[ -n ${GITHUB_STEP_SUMMARY:-} ]]; then
  cat -- "$summary" >>"$GITHUB_STEP_SUMMARY" || fail "writing the job summary failed"
fi
posted=0
SECURITY_SLACK_WEBHOOK_URL=$webhook .github/scripts/notify.sh security-scan "$verdict" "$slack" ||
  posted=$?
echo "security-scan: $verdict"
exit $((code > posted ? code : posted))
