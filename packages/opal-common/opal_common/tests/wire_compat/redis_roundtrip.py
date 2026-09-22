#!/usr/bin/env python3
"""Scope records written by one pydantic version must read under the other.

`Scope` is the only OPAL model that is PERSISTED rather than sent - it lives in
Redis under `permit.io/Scope:*`, written by whichever server happens to handle
the PUT and read by every server afterwards. During a rolling upgrade both
versions read the same keyspace, so this has to work in both directions:

    v1 writes -> v2 reads    an upgraded server reading existing records
    v2 writes -> v1 reads    a not-yet-upgraded server reading new ones
                             (also what a rollback has to survive)

Unlike the golden corpus, this exercises the real `ScopeRepository` and the
real `RedisDB._serialize`, so it covers the persistence path rather than just
the model.

This is a driver, not a pytest: it needs Redis and two interpreters. Run each
half under a different one against the same Redis.

    # under a PRE-MIGRATION checkout (pydantic v1)
    python redis_roundtrip.py write  --redis-url redis://localhost:6379 --tag v1

    # under this tree (pydantic v2)
    python redis_roundtrip.py verify --redis-url redis://localhost:6379 --tag v1
    python redis_roundtrip.py write  --redis-url redis://localhost:6379 --tag v2

    # back under the pre-migration checkout
    python redis_roundtrip.py verify --redis-url redis://localhost:6379 --tag v2

Exit codes follow the OPAL kit contract: 0 PASS, 1 FAIL, 2 INVALID RUN.
An unreachable Redis is INVALID, never FAIL - it is not evidence either way.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from payloads import CASES  # noqa: E402

EXIT_PASS, EXIT_FAIL, EXIT_INVALID = 0, 1, 2

SCOPE_CASES = [c for c in CASES if c.model.endswith(":Scope")]


def _pydantic_version() -> str:
    import pydantic

    return str(getattr(pydantic, "VERSION", "?"))


def _is_v1() -> bool:
    return _pydantic_version().startswith("1.")


def _load(scope_cls, payload):
    return (
        scope_cls.parse_obj(payload) if _is_v1() else scope_cls.model_validate(payload)
    )


def _dump_json(instance) -> str:
    return instance.json() if _is_v1() else instance.model_dump_json()


async def _repo(redis_url: str):
    from opal_server.redis_utils import RedisDB
    from opal_server.scopes.scope_repository import ScopeRepository

    db = RedisDB(redis_url)
    try:
        await db.redis_connection.ping()
    except Exception as exc:  # noqa: BLE001
        print(f"INVALID: cannot reach Redis at {redis_url}: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_INVALID)
    return ScopeRepository(db)


def _scope_id(case_name: str, tag: str) -> str:
    return f"wirecompat-{tag}-{case_name}"


async def cmd_write(args) -> int:
    from opal_common.schemas.scopes import Scope

    repo = await _repo(args.redis_url)
    written = {}

    for case in SCOPE_CASES:
        payload = dict(case.payload)
        payload["scope_id"] = _scope_id(case.name, args.tag)
        scope = _load(Scope, payload)
        await repo.put(scope)
        # what this writer believes it stored, for the reader to compare against
        written[payload["scope_id"]] = json.loads(_dump_json(scope))

    if not written:
        print("INVALID: no Scope cases in the corpus to write", file=sys.stderr)
        return EXIT_INVALID

    Path(args.state).write_text(
        json.dumps(
            {"pydantic": _pydantic_version(), "tag": args.tag, "scopes": written},
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    print(
        f"wrote {len(written)} scopes under pydantic {_pydantic_version()} -> {args.state}"
    )
    return EXIT_PASS


async def cmd_verify(args) -> int:
    repo = await _repo(args.redis_url)

    state_path = Path(args.state)
    if not state_path.exists():
        print(f"INVALID: {state_path} not found - run `write` first", file=sys.stderr)
        return EXIT_INVALID
    state = json.loads(state_path.read_text())

    writer_version = state["pydantic"]
    reader_version = _pydantic_version()
    if writer_version.split(".")[0] == reader_version.split(".")[0]:
        print(
            f"INVALID: writer and reader are both pydantic {writer_version.split('.')[0]}.x "
            "- this asserts nothing about cross-version persistence",
            file=sys.stderr,
        )
        return EXIT_INVALID

    failures = []
    for scope_id, expected in state["scopes"].items():
        try:
            scope = await repo.get(scope_id)
        except Exception as exc:  # noqa: BLE001
            failures.append(
                f"{scope_id}: pydantic {reader_version} cannot READ a record written "
                f"by pydantic {writer_version}: {type(exc).__name__}: {exc}"
            )
            continue

        produced = json.loads(_dump_json(scope))
        if produced != expected:
            failures.append(
                f"{scope_id}: read back but re-serialized differently\n"
                f"      writer ({writer_version}): {json.dumps(expected, sort_keys=True)[:200]}\n"
                f"      reader ({reader_version}): {json.dumps(produced, sort_keys=True)[:200]}"
            )

    # the repository's own scan path, not just per-key gets
    try:
        scanned = {s.scope_id for s in await repo.all()}
    except Exception as exc:  # noqa: BLE001
        failures.append(f"ScopeRepository.all() raised: {type(exc).__name__}: {exc}")
        scanned = set()

    missing = set(state["scopes"]) - scanned
    if missing:
        failures.append(f"not returned by ScopeRepository.all(): {sorted(missing)}")

    print(
        f"verified {len(state['scopes'])} scopes: written under pydantic "
        f"{writer_version}, read under {reader_version}"
    )
    if failures:
        print("\nFAIL:", file=sys.stderr)
        for line in failures:
            print(f"  {line}", file=sys.stderr)
        return EXIT_FAIL
    return EXIT_PASS


async def cmd_clean(args) -> int:
    repo = await _repo(args.redis_url)
    for case in SCOPE_CASES:
        for tag in ("v1", "v2"):
            try:
                await repo.delete(_scope_id(case.name, tag))
            except Exception:  # noqa: BLE001 - absent is fine
                pass
    print("cleaned")
    return EXIT_PASS


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("write", "verify", "clean"))
    parser.add_argument("--redis-url", default="redis://localhost:6379")
    parser.add_argument("--tag", default="v1", help="label for this writer's records")
    parser.add_argument("--state", default="redis_roundtrip_state.json")
    args = parser.parse_args()

    handler = {"write": cmd_write, "verify": cmd_verify, "clean": cmd_clean}[
        args.command
    ]
    return asyncio.run(handler(args))


if __name__ == "__main__":
    sys.exit(main())
