#!/usr/bin/env bash
# Cross-version Scope persistence, both directions, in one command.
#
#   ./run_redis_roundtrip.sh <pre-migration-python> [<this-tree-python>]
#
# The first argument is a python whose interpreter has a PRE-MIGRATION opal
# checkout importable (pydantic v1). The second defaults to whatever python is
# on PATH, which must have this tree importable (pydantic v2).
#
# Brings up its own Redis on a port nothing else uses, runs v1->v2 and v2->v1,
# and tears down. Exit codes follow the kit contract:
#   0 PASS   1 FAIL   2 INVALID RUN (precondition unmet - not evidence either way)
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRIVER="$HERE/redis_roundtrip.py"
EXIT_PASS=0; EXIT_FAIL=1; EXIT_INVALID=2

V1_PYTHON="${1:-}"
V2_PYTHON="${2:-python3}"
REDIS_PORT="${REDIS_PORT:-16379}"
CONTAINER="opal-wirecompat-redis-$$"
STATE_DIR="$(mktemp -d)"

die_invalid() { echo "INVALID RUN: $*" >&2; exit $EXIT_INVALID; }

[ -n "$V1_PYTHON" ] || die_invalid \
  "no pre-migration python given. usage: $0 <v1-python> [v2-python]"
command -v "$V1_PYTHON" >/dev/null 2>&1 || [ -x "$V1_PYTHON" ] || die_invalid \
  "pre-migration python not executable: $V1_PYTHON"
command -v docker >/dev/null 2>&1 || die_invalid "docker is required to run Redis"

"$V1_PYTHON" -c 'import pydantic,sys; sys.exit(0 if pydantic.VERSION.startswith("1.") else 1)' \
  2>/dev/null || die_invalid "$V1_PYTHON is not a pydantic v1 environment"
"$V2_PYTHON" -c 'import pydantic,sys; sys.exit(0 if pydantic.VERSION.startswith("2.") else 1)' \
  2>/dev/null || die_invalid "$V2_PYTHON is not a pydantic v2 environment"

cleanup() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1
  rm -rf "$STATE_DIR"
}
trap cleanup EXIT INT TERM

docker run -d --rm --name "$CONTAINER" -p "$REDIS_PORT:6379" redis:7-alpine >/dev/null \
  || die_invalid "could not start Redis"

for _ in $(seq 1 30); do
  docker exec "$CONTAINER" redis-cli ping 2>/dev/null | grep -q PONG && break
  sleep 0.5
done
docker exec "$CONTAINER" redis-cli ping 2>/dev/null | grep -q PONG \
  || die_invalid "Redis did not become ready"

URL="redis://localhost:$REDIS_PORT"
rc=$EXIT_PASS

# Run one leg and record its verdict.
#
# The driver's status is captured DIRECTLY, not through ${PIPESTATUS[0]} after a
# command substitution. `out=$(cmd | grep)` is a simple command in the parent
# shell, so PIPESTATUS there describes that assignment - i.e. grep's status, not
# the driver's. Measured on bash 3.2.57 and 5.2: the previous form reported 0
# for a driver exiting 1 AND for one exiting 2, so this orchestrator could never
# report FAIL or INVALID at all.
step() {
  local label="$1" py="$2"; shift 2
  local raw code
  raw="$STATE_DIR/$(printf '%s' "$label" | tr -c 'A-Za-z0-9' '_').out"

  "$py" "$DRIVER" "$@" --redis-url "$URL" > "$raw" 2>&1
  code=$?

  # loguru's default line is `2026-09-17 15:37:27.398 | DEBUG | ...` - two
  # whitespace-separated tokens before the pipe, which `^\S+ \| DEBUG` never
  # matched. Drop the level anywhere on the line instead.
  local out
  out=$(grep -viE '\| *DEBUG *\|' "$raw" || true)

  printf '  %-26s %s\n' "$label" "$(printf '%s' "$out" | tail -1)"
  case $code in
    0) ;;
    # On a non-zero code print the WHOLE filtered output, not tail -1: the last
    # line is the success-looking "verified N scopes" summary, so tail -1 hid
    # every FAIL reason the driver had just printed.
    2) printf '%s\n' "$out" | sed 's/^/      /' >&2; rc=$EXIT_INVALID ;;
    *) printf '%s\n' "$out" | sed 's/^/      /' >&2
       [ "$rc" -ne "$EXIT_INVALID" ] && rc=$EXIT_FAIL ;;
  esac
}

echo "Scope persistence across pydantic versions"
step "v1 writes"        "$V1_PYTHON" write  --tag v1 --state "$STATE_DIR/v1.json"
step "  -> v2 reads"    "$V2_PYTHON" verify --tag v1 --state "$STATE_DIR/v1.json"
step "v2 writes"        "$V2_PYTHON" write  --tag v2 --state "$STATE_DIR/v2.json"
step "  -> v1 reads"    "$V1_PYTHON" verify --tag v2 --state "$STATE_DIR/v2.json"

case $rc in
  0) echo "PASS - Scope records survive in both directions" ;;
  1) echo "FAIL - see above" >&2 ;;
  2) echo "INVALID RUN - a precondition was unmet; this is not evidence" >&2 ;;
esac
exit $rc
