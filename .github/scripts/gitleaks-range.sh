#!/usr/bin/env bash
# gitleaks-range.sh [--if-empty error|notice] <base> <head> scans the commits in base..head, the
# ones head has and base does not, for secrets with the gitleaks release that
# .github/binaries.lock pins, which .github/scripts/fetch-tool.sh gitleaks installs as
# bin/gitleaks. base and head name commits of the repository the script is in: SHAs, or revisions
# such as origin/master and HEAD. The secrets job in .github/workflows/tests.yml runs it on the
# full history (fetch-depth: 0).
#
# Nothing in the scanned commits but .gitleaks.toml changes how they are scanned, and a change to
# .gitleaks.toml shows in their diff:
#
#   - gitleaks gets the repository's .gitleaks.toml by path; every GITLEAKS_ variable is unset.
#   - gitleaks scans the repository's git directory, from an empty directory and with an empty
#     ignore file, so no .gitleaksignore can drop a finding, and no .gitattributes can mark a
#     file binary. gitleaks skips the changes of a binary file, so git log gets --text: a file
#     that git takes for binary because it holds a NUL byte is scanned as text.
#   - --ignore-gitleaks-allow reports a secret on a line with a gitleaks:allow comment, and
#     --diff-merges=first-parent scans what a merge commit changes, so a secret added while
#     resolving a merge is found.
#   - gitleaks reads the output of git log, which runs with GIT_CONFIG_GLOBAL=/dev/null and
#     GIT_CONFIG_NOSYSTEM=1, so no user or system git configuration, such as a format.pretty
#     that changes how git log prints a commit, keeps it from reading a finding's commit.
#
# The work to do is the number of commits in the range, from git rev-list --count; gitleaks' own
# count cannot be relied on, as it can log 0 commits scanned for a range of commits it scanned.
# A range without a commit did not run, unless --if-empty notice is given: then the script prints
# a notice and passes. CI gives it on a push and a manual run, whose ranges may hold no commit,
# and not on a pull request.
#
# Each finding is printed with its file, line, rule and commit, never its secret: gitleaks runs
# with --redact. Everything is printed with workflow commands stopped, except the annotation that
# reports a finding or an empty range at the end. The work files stay in a temporary directory
# under RUNNER_TEMP (or TMPDIR), which the runner or the system clears.
#
# Exit codes: 0 when no secret is found, or the range holds no commit and --if-empty notice is
# given; 1 when gitleaks finds a secret; 2 when the scan did not run: the arguments are wrong, jq
# is missing, .github/binaries.lock has no version for gitleaks, bin/gitleaks is missing or is
# another version, .gitleaks.toml is missing, the repository is a shallow clone, base or head is
# not a commit (such as the zero SHA), the range holds no commit, or gitleaks failed: it exited
# with another code than 0 or its code for a finding, logged an error, or wrote a report that is
# missing, is not a JSON list of findings, or disagrees with its exit code.
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
  echo "gitleaks-range: $*"
  echo "gitleaks-range: DID NOT RUN"
  exit 2
}

usage="usage: gitleaks-range.sh [--if-empty error|notice] <base> <head>"
if_empty=error
if [[ $# -ge 2 && $1 == --if-empty ]]; then
  if_empty=$2
  shift 2
fi
[[ $if_empty == error || $if_empty == notice ]] ||
  fail "--if-empty takes error or notice, not \"$if_empty\""
[[ $# -eq 2 ]] || fail "$usage"
base=$1
head=$2
command -v jq >/dev/null 2>&1 || fail "jq is not installed, so the gitleaks report cannot be read"
root=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
for var in $(compgen -e); do
  [[ $var != GITLEAKS_* ]] || unset "$var"
done
config=$root/.gitleaks.toml
[[ -f $config ]] || fail ".gitleaks.toml is missing at the repository root"

# The version line is read the way fetch-tool.sh reads it: spaces around = are optional.
want=$(awk '/^\[/ { entry = ($0 == "[gitleaks]"); next }
  entry && /^version[[:space:]]*=/ {
    sub(/^version[[:space:]]*=[[:space:]]*/, ""); sub(/[[:space:]]+$/, ""); print; exit
  }' "$root/.github/binaries.lock") || fail "reading .github/binaries.lock failed"
[[ -n $want ]] || fail ".github/binaries.lock has no version for gitleaks"
bin=$root/bin/gitleaks
[[ -x $bin ]] ||
  fail "bin/gitleaks is missing; install it with .github/scripts/fetch-tool.sh gitleaks"
have=$("$bin" version 2>/dev/null) || fail "bin/gitleaks version failed"
[[ $have == "$want" ]] || fail "bin/gitleaks reports version \"$have\", want $want from" \
  ".github/binaries.lock; install it with .github/scripts/fetch-tool.sh gitleaks"

shallow=$(git -C "$root" rev-parse --is-shallow-repository) ||
  fail "git cannot read the repository the script is in"
[[ $shallow == false ]] || fail "the repository is a shallow clone, which may lack the commits" \
  "of the range; clone the full history (fetch-depth: 0)"
git_dir=$(git -C "$root" rev-parse --absolute-git-dir) ||
  fail "git cannot find the repository's git directory"
zero_re='^0{40}$'
for rev in "$base" "$head"; do
  [[ ! $rev =~ $zero_re ]] || fail "\"$rev\" is the zero SHA, which a push sends for a branch" \
    "it creates or deletes, so there is no range of commits to scan"
done
head_sha=$(git -C "$root" rev-parse --verify --quiet --end-of-options "$head^{commit}" \
  2>/dev/null) || fail "the head \"$head\" is not a commit in the repository; clone the full" \
  "history (fetch-depth: 0)"
base_sha=$(git -C "$root" rev-parse --verify --quiet --end-of-options "$base^{commit}" \
  2>/dev/null) || fail "the base \"$base\" is not a commit in the repository; clone the full" \
  "history (fetch-depth: 0)"
range=$base_sha..$head_sha
short=${base_sha:0:12}..${head_sha:0:12}
count=$(git -C "$root" rev-list --count "$range") || fail "git rev-list --count $short failed"
if [[ $count -eq 0 ]]; then
  [[ $if_empty == notice ]] || fail "$short holds no commit, so there is nothing to scan"
  echo "gitleaks-range: $short holds no commit; nothing to scan"
  echo "gitleaks-range: PASS"
  resume
  echo "::notice title=Secret scan::$short holds no commit, so no commit was scanned for secrets"
  exit 0
fi

work=$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/gitleaks-range.XXXXXX") ||
  fail "creating a temporary directory failed"
mkdir "$work/empty" || fail "creating a temporary directory failed"
: >"$work/ignore" || fail "creating an empty ignore file failed"

# gitleaks exits 1 on a fatal error too, so a finding gets an exit code of its own.
leak_exit=10
code=0
(cd -- "$work/empty" && GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 \
  "$bin" git --no-banner --redact --exit-code "$leak_exit" \
  --config "$config" --gitleaks-ignore-path "$work/ignore" --ignore-gitleaks-allow \
  --report-format json --report-path "$work/report.json" \
  "--log-opts=--text --diff-merges=first-parent $range" "$git_dir") >"$work/log" 2>&1 || code=$?
cat -- "$work/log"
case $code in
0 | "$leak_exit") ;;
*) fail "gitleaks exited $code" ;;
esac
# gitleaks logs a git error, such as a missing object, and exits 0 with the commits it read.
esc=$'\033'
plain_log=$(sed "s/$esc\\[[0-9;]*m//g" "$work/log") || fail "reading the gitleaks log failed"
if grep -Eq '^[^ ]+ (ERR|FTL) ' <<<"$plain_log"; then
  fail "gitleaks logged an error, so it may not have scanned every commit"
fi
findings=$(jq -se 'if length == 1 and (.[0] | type == "array" and all(.[]; type == "object"))
  then .[0] | length else error("not a list of findings") end' "$work/report.json" 2>/dev/null) ||
  fail "gitleaks wrote no report, or one that is not a JSON list of findings"
if [[ $code -eq 0 && $findings -gt 0 ]]; then
  fail "gitleaks exited 0, but its report lists findings: $findings"
fi
if [[ $code -eq $leak_exit && $findings -eq 0 ]]; then
  fail "gitleaks exited $leak_exit, its code for a finding, but its report lists none"
fi
jq -r '.[] | "\(.File):\(.StartLine): \(.RuleID) (\(.Description)), commit \(.Commit // ""
  | .[0:12])"' "$work/report.json" || fail "reading the findings in the gitleaks report failed"

echo "gitleaks-range: $short: gitleaks $want; commits scanned: $count, findings: $findings"
if [[ $findings -gt 0 ]]; then
  echo "gitleaks-range: FAIL"
  resume
  echo "::error title=Secret scan::gitleaks found secrets in the commits $short (findings:" \
    "$findings); see the job log. Revoke each one, remove it from the branch's history, and use" \
    "fake keys that start with permit_key_FAKE in tests and docs."
  exit 1
fi
echo "gitleaks-range: PASS"
