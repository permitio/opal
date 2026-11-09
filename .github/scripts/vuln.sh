#!/usr/bin/env bash
# vuln.sh [--prepare <directory>] scans the published packages' dependency ranges for known
# vulnerabilities with Trivy. .github/scripts/security-scan.sh runs it with --prepare; without
# it, vuln.sh scans and decides on its own, and runs the same way on any clone. It needs the
# network: it downloads uv, Trivy, the package metadata and the vulnerability database.
#
# opal-common, opal-client and opal-server read their install_requires from
# packages/requires.txt and packages/<pkg>/requires.txt, and those ranges are what every
# downstream install resolves. uv pip compile resolves the four files together for CPython 3.12
# on manylinux x86_64, from wheels only, into two trees of exact pins:
#
#   floor    every direct requirement at the lowest version its range admits (lowest-direct)
#   ceiling  every requirement at the newest version its range admits
#
# With --prepare, it only installs uv and Trivy with fetch-tool.sh and writes the trees as
# <directory>/floor/requirements.txt and <directory>/ceiling/requirements.txt; the directory must
# not exist. Without it, it writes them to a temporary directory and runs trivy.sh block on both,
# which fails on a vulnerability of HIGH or CRITICAL severity that has a fixed version.
#
# Everything it prints is inside a stop-commands block, so that no tool output can issue a
# workflow command. uv and Trivy run without GH_TOKEN and GITHUB_TOKEN.
#
# Exit codes: 0 when both scans passed, or the trees were prepared; 1 when a scan found such a
# vulnerability and both scans ran; 2 when a scan did not run, the arguments are wrong, or the
# tools could not be installed or the trees resolved.
set -euo pipefail

token=$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')
echo "::stop-commands::$token"
trap 'echo "::$token::"' EXIT

fail() {
  echo "vuln: $*"
  echo "vuln: DID NOT RUN"
  exit 2
}

prepare=''
if [[ $# -eq 2 && $1 == --prepare && -n $2 ]]; then
  prepare=$2
elif [[ $# -ne 0 ]]; then
  fail "usage: vuln.sh [--prepare <directory>]"
fi
root=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
cd -- "$root"
unset GH_TOKEN GITHUB_TOKEN

echo "vuln: installing uv and Trivy with fetch-tool.sh"
.github/scripts/fetch-tool.sh uv >/dev/null || fail "installing uv failed"
.github/scripts/fetch-tool.sh trivy >/dev/null || fail "installing Trivy failed"

if [[ -n $prepare ]]; then
  trees=$prepare
  mkdir -- "$trees" || fail "creating $trees failed; it must not exist"
else
  trees=$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/vuln.XXXXXX") ||
    fail "creating a temporary directory failed"
fi
mkdir -- "$trees/floor" "$trees/ceiling" || fail "creating the tree directories failed"

files=(packages/requires.txt packages/opal-common/requires.txt packages/opal-client/requires.txt
  packages/opal-server/requires.txt)
compile=(bin/uv pip compile --no-config --no-header --quiet --no-build
  --index-url https://pypi.org/simple --python-version 3.12 --python-platform x86_64-manylinux_2_28)
echo "vuln: resolving the floor and the ceiling of ${files[*]}"
"${compile[@]}" --resolution lowest-direct "${files[@]}" -o "$trees/floor/requirements.txt" ||
  fail "resolving the floor failed"
"${compile[@]}" "${files[@]}" -o "$trees/ceiling/requirements.txt" ||
  fail "resolving the ceiling failed"
if [[ -n $prepare ]]; then
  echo "vuln: prepared uv, Trivy and the trees in $trees"
  exit 0
fi

worst=0
for tree in floor ceiling; do
  echo "vuln: $tree"
  code=0
  .github/scripts/trivy.sh block "$trees/$tree/requirements.txt" || code=$?
  case $code in
  0) ;;
  1) [[ $worst -eq 2 ]] || worst=1 ;;
  *) worst=2 ;;
  esac
done
case $worst in
0) echo "vuln: PASS" ;;
1) echo "vuln: FAIL" ;;
*) echo "vuln: DID NOT RUN" ;;
esac
exit "$worst"
