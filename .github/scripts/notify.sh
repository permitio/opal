#!/usr/bin/env bash
# notify.sh <check> <result> [<body file>] posts a notice to the security Slack channel through
# its incoming webhook, SECURITY_SLACK_WEBHOOK_URL: the line
# "<repo> <check>: <result>. <run URL>", and under it the body, a file of Slack text that the
# caller wrote with every outside value escaped. digest.sh runs it this way. It reads
# GITHUB_REPOSITORY, and GITHUB_SERVER_URL and GITHUB_RUN_ID for the run's URL, which CI sets.
#
# notify.sh --message <file> posts the file as the whole notice, as it is: a complete Slack message
# whose every outside value the caller escaped, with its own headline and run link.
# security-scan.sh runs it this way, with the message format_security_report.py renders.
#
# When SECURITY_SLACK_WEBHOOK_URL is empty or not set, it prints a ::warning:: that says the
# notice was not posted, writes the same line to the job summary, and exits 0. It never prints
# the webhook. Slack cuts a message after 40,000 characters, so the body is cut after a line to
# keep the text within 39,000 bytes, with a note that says so.
#
# Exit codes: 0 when the webhook answered with a 2xx status, or the webhook is not set; 1 when the
# notice was not delivered; 2 when notify did not run: the arguments are wrong, jq or curl is
# missing, the body file cannot be read, or the webhook is not an https URL.
set -euo pipefail

fail() {
  echo "notify: DID NOT RUN: $*"
  exit 2
}

usage="usage: notify.sh <check> <result> [<body file>] | notify.sh --message <file>"
message_file=''
if [[ $# -eq 2 && $1 == --message ]]; then
  message_file=$2
  [[ -n $message_file ]] || fail "$usage"
elif [[ $# -eq 2 || $# -eq 3 ]]; then
  check=$1
  result=$2
  body_file=${3:-}
else
  fail "$usage"
fi
for tool in jq curl; do
  command -v "$tool" >/dev/null 2>&1 || fail "$tool is not installed"
done
webhook=${SECURITY_SLACK_WEBHOOK_URL:-}
unset SECURITY_SLACK_WEBHOOK_URL
repo=${GITHUB_REPOSITORY:-}
run_url=''
if [[ -n ${GITHUB_SERVER_URL:-} && -n $repo && -n ${GITHUB_RUN_ID:-} ]]; then
  run_url=$GITHUB_SERVER_URL/$repo/actions/runs/$GITHUB_RUN_ID
fi

# esc escapes the characters that Slack's text format gives a meaning; line is one line of text.
# Each replacement is quoted: from bash 5.2 an unquoted & in it stands for the matched text.
esc() {
  local value=${1//&/"&amp;"}
  value=${value//</"&lt;"}
  value=${value//>/"&gt;"}
  printf '%s' "${value//$'\n'/ }"
}
if [[ -n $message_file ]]; then
  [[ -r $message_file ]] || fail "the message file $message_file cannot be read"
  # The message's first line is its headline, which the log and the warning show.
  line=$(head -n 1 -- "$message_file") || fail "reading the message file $message_file failed"
  check=security-scan
  result=$line
  body_file=$(mktemp "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/notify.XXXXXX") ||
    fail "creating a temporary file failed"
  tail -n +2 -- "$message_file" >"$body_file" || fail "reading the message file failed"
else
  line="$(esc "$repo") $(esc "$check"): $(esc "$result")."
  if [[ -n $run_url ]]; then
    line+=" <$run_url|Run>"
  fi
fi

text=$line
if [[ -n $body_file ]]; then
  [[ -r $body_file ]] || fail "the body file $body_file cannot be read"
  limit=39000
  note='• The report is cut here; the run'"'"'s job summary has the rest.'
  # LC_ALL=C: awk counts bytes.
  text=$(LC_ALL=C awk -v line="$line" -v limit="$limit" -v note="$note" '
    BEGIN { out = line; size = length(line) }
    { if (size + 1 + length($0) > limit - length(note) - 1) { cut = 1; exit }
      out = out "\n" $0; size += 1 + length($0) }
    END { if (cut) out = out "\n" note; printf "%s", out }' "$body_file") ||
    fail "reading the body file $body_file failed"
fi

if [[ -z $webhook ]]; then
  echo "::warning title=Slack::SECURITY_SLACK_WEBHOOK_URL is not set, so this notice was not" \
    "posted: $(esc "$check"): $(esc "$result")"
  if [[ -n ${GITHUB_STEP_SUMMARY:-} ]]; then
    printf '\nSlack: not posted, because SECURITY_SLACK_WEBHOOK_URL is not set.\n' \
      >>"$GITHUB_STEP_SUMMARY"
  fi
  exit 0
fi
[[ $webhook == https://* ]] || fail "SECURITY_SLACK_WEBHOOK_URL is not an https URL"

payload=$(jq -n --arg text "$text" '{text: $text}') || fail "building the message failed"
status=0
reply=$(printf '%s' "$payload" | curl --disable --silent --proto '=https' --max-time 60 \
  --retry 2 --output /dev/null --write-out '%{http_code}' \
  --header 'Content-Type: application/json' --data-binary @- -- "$webhook") || status=$?
if [[ $status -ne 0 || ! $reply =~ ^2[0-9][0-9]$ ]]; then
  echo "notify: FAIL: posting to the security channel failed (curl exit $status," \
    "HTTP ${reply:-none})"
  exit 1
fi
echo "notify: posted to the security channel (HTTP $reply): $line"
