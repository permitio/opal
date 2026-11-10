#!/usr/bin/env bash
# trivy.sh <block|report> <target> [<findings file>] scans a target with the Trivy release that
# .github/binaries.lock pins, which .github/scripts/fetch-tool.sh trivy installs as bin/trivy, and
# prints the vulnerabilities of HIGH or CRITICAL severity that have a fixed version, then the count
# of every vulnerability by severity. With block, such a vulnerability fails the scan; with
# report, none does. The target is one of:
#
#   <file>         a requirements file of exact pins (name==version), such as vuln.sh writes with
#                  uv pip compile. The scan counts only when Trivy lists exactly as many packages
#                  as the file has pins.
#   image:<ref>    a published image, such as image:permitio/opal-server:latest, pulled from its
#                  registry for linux/amd64. The scan counts only when Trivy lists a package.
#
# With a findings file, it also writes each vulnerability there as a JSON line: its ID, package,
# installed and fixed versions, severity in lowercase (empty for UNKNOWN), title, CVSS base score
# (null when Trivy has none), the GHSA and CVE IDs its vendors give it, and Trivy's https link for
# it, each value cut to fit the report of security-scan.sh. The file is written only when the
# scan counts. Trivy runs in an empty directory with every setting on its command line, so no
# trivy.yaml, .trivyignore or TRIVY_ environment variable can change the scan. The work files stay
# in a temporary directory under RUNNER_TEMP (or TMPDIR), which the runner or the system clears.
#
# Exit codes: 0 when nothing fails the scan; 1 when block finds a HIGH or CRITICAL vulnerability
# with a fixed version; 2 when the scan did not run: the arguments are wrong, the file has no pin,
# jq is missing, bin/trivy is missing or is not the version the lock pins, Trivy failed, its
# output is not a JSON report, its package count does not match, or the findings file cannot be
# written.
set -euo pipefail

fail() {
  echo "trivy: $*"
  echo "trivy: DID NOT RUN"
  exit 2
}

[[ $# -eq 2 || $# -eq 3 ]] || fail "usage: trivy.sh <block|report> <target> [<findings file>]"
policy=$1
target=$2
findings=${3:-}
[[ $policy == block || $policy == report ]] || fail "the policy \"$policy\" is not block or report"
command -v jq >/dev/null 2>&1 || fail "jq is not installed, so Trivy's report cannot be read"
root=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)

# The version line is read the way fetch-tool.sh reads it: spaces around = are optional.
want=$(awk '/^\[/ { entry = ($0 == "[trivy]"); next }
  entry && /^version[[:space:]]*=/ {
    sub(/^version[[:space:]]*=[[:space:]]*/, ""); sub(/[[:space:]]+$/, ""); print; exit
  }' "$root/.github/binaries.lock") || fail "reading .github/binaries.lock failed"
[[ -n $want ]] || fail ".github/binaries.lock has no version for trivy"
bin=$root/bin/trivy
[[ -x $bin ]] || fail "bin/trivy is missing; install it with .github/scripts/fetch-tool.sh trivy"
have=$("$bin" --version 2>/dev/null) || fail "bin/trivy --version failed"
have=${have%%$'\n'*}
[[ $have == "Version: $want" ]] || fail "bin/trivy reports \"$have\", want version $want from" \
  ".github/binaries.lock; install it with .github/scripts/fetch-tool.sh trivy"

pin_re='^[A-Za-z0-9][A-Za-z0-9._-]*(\[[^]]*\])?==[^[:space:]]+'
if [[ $target == image:* ]]; then
  image=${target#image:}
  [[ -n $image ]] || fail "the target \"$target\" names no image"
  scan=(image --image-src remote --platform linux/amd64 "$image")
  expected=''
else
  [[ -f $target ]] || fail "$target is not a file"
  file=$(CDPATH='' cd -- "$(dirname -- "$target")" && pwd)/$(basename -- "$target")
  expected=$(grep -cE "$pin_re" "$file") || fail "$target has no name==version pin"
  scan=(fs "$file")
fi

work=$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/trivy.XXXXXX") ||
  fail "creating a temporary directory failed"
mkdir "$work/empty"
for var in $(compgen -e); do
  [[ $var != TRIVY_* ]] || unset "$var"
done
code=0
(cd "$work/empty" && "$bin" "${scan[0]}" --scanners vuln --list-all-pkgs --format json \
  --exit-code 0 --config '' --ignorefile '' --skip-version-check --disable-telemetry \
  --no-progress "${scan[@]:1}") >"$work/report.json" 2>"$work/log" || code=$?
if [[ $code -ne 0 ]]; then
  cat -- "$work/log"
  fail "Trivy exited $code"
fi
jq -e '.SchemaVersion == 2 and has("ArtifactType")' "$work/report.json" >/dev/null 2>&1 ||
  fail "Trivy's output is not a JSON report"

packages=$(jq '[.Results // [] | .[].Packages // [] | .[] | select(.Relationship != "root")]
  | length' "$work/report.json" 2>/dev/null) || fail "Trivy's report has no list of packages"
if [[ -n $expected ]]; then
  [[ $packages -eq $expected ]] ||
    fail "Trivy listed $packages packages for $target, which has $expected pins"
  what="$target: $packages packages, $expected pins"
else
  [[ $packages -gt 0 ]] || fail "Trivy listed no package in $image"
  what="$image: $packages packages"
fi

vulns='def fixable: (.Severity == "HIGH" or .Severity == "CRITICAL") and .FixedVersion != "";
  [.Results // [] | .[].Vulnerabilities // [] | .[] | .FixedVersion //= ""]'
jq -r "$vulns"'
  | def ids: .VulnerabilityID + (.VendorIDs // [] | if . == [] then "" else
      " (" + join(", ") + ")" end);
    map(select(fixable)) | sort_by(.Severity != "CRITICAL", .VulnerabilityID, .PkgName) | .[]
  | ids + "  " + .Severity + ", fixed in " + .FixedVersion + ": " + .PkgName + " "
    + .InstalledVersion' "$work/report.json" 2>/dev/null ||
  fail "Trivy's report has no list of vulnerabilities"
fixable=$(jq "$vulns"' | map(select(fixable)) | length' "$work/report.json") ||
  fail "counting the vulnerabilities in Trivy's report failed"
counts=$(jq -r "$vulns"' | group_by(.Severity) | map("\(length) \(.[0].Severity)")
  | join(", ") | if . == "" then "none" else . end' "$work/report.json") ||
  fail "counting the vulnerabilities in Trivy's report failed"
if [[ -n $findings ]]; then
  # clip($n) turns each control character into a space and cuts a value to at most $n bytes, the
  # last three of them "..."; link drops a URL that is not a plain https link or is longer than
  # 300 bytes. So a long or odd value never breaks the report.
  # shellcheck disable=SC2016 # $n is a jq variable
  fit='def clip($n): gsub("\\p{Cc}"; " ") | if utf8bytelength <= $n then .
      else .[0:$n] | until(utf8bytelength <= $n - 3; .[0:-1]) + "..." end;
    def link: if test("^https://[^\\s<>|()\\[\\]\"]+$") and utf8bytelength <= 300 then .
      else "" end;'
  # score is the CVSS v3 (or v4) base score of the source Trivy took the severity from, else of
  # NVD, GHSA or any other source.
  jq -c "$fit$vulns"' | .[] | {id: (.VulnerabilityID | clip(80)), package: (.PkgName | clip(200)),
    version: (.InstalledVersion // "" | clip(200)), fix: (.FixedVersion | clip(200)),
    severity: (.Severity // "" | ascii_downcase | if . == "unknown" then "" else . end),
    title: (.Title // "" | clip(200)),
    score: ((.CVSS // {}) as $cvss | [.SeveritySource, "nvd", "ghsa", ($cvss | keys[])]
      | map(select(type == "string") | $cvss[.] // empty | objects | .V3Score // .V40Score
        | select(type == "number" and . > 0)) | .[0]),
    aliases: [.VendorIDs // [] | .[] | strings | select(test("^(GHSA|CVE)-")) | clip(80)],
    url: (.PrimaryURL // "" | link)}' \
    "$work/report.json" >"$findings" || fail "writing the findings to $findings failed"
fi

echo "trivy: $what; Trivy $want"
echo "trivy: vulnerabilities: $counts; HIGH or CRITICAL with a fixed version: $fixable ($policy)"
if [[ $policy == block && $fixable -gt 0 ]]; then
  echo "trivy: FAIL"
  exit 1
fi
echo "trivy: PASS"
