#!/usr/bin/env python3
"""Capture the pydantic v1 wire form of every corpus case.

Run this ONCE, under a pydantic v1 interpreter with a PRE-MIGRATION opal
checkout importable, to produce the golden files the v2 suite asserts against.
It is not part of the test run and never executes in CI.

    # from a checkout of master (pydantic v1)
    python -m pip install -r requirements.txt
    python generate_golden.py --out <this-branch>/.../wire_compat/golden

The goldens are the *contract with the installed fleet*: every PDP in the field
runs opal-client 0.9.6, which is pydantic v1. Regenerating them against a v2
tree would assert v2 against itself and prove nothing, so this script refuses
to run under v2.

Exit codes follow the OPAL kit contract: 0 PASS, 1 FAIL, 2 INVALID RUN.
"""

import argparse
import json
import sys
from importlib import import_module
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from canon import canonical  # noqa: E402
from payloads import CASES  # noqa: E402

EXIT_PASS, EXIT_FAIL, EXIT_INVALID = 0, 1, 2


def resolve(dotted: str):
    module_path, _, class_name = dotted.partition(":")
    return getattr(import_module(module_path), class_name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="directory to write goldens into")
    parser.add_argument(
        "--allow-v2",
        action="store_true",
        help="escape hatch for refreshing a case deliberately; normally wrong",
    )
    args = parser.parse_args()

    try:
        import pydantic
    except ImportError:
        print("INVALID: pydantic is not importable", file=sys.stderr)
        return EXIT_INVALID

    version = getattr(pydantic, "VERSION", "?")
    if not str(version).startswith("1.") and not args.allow_v2:
        print(
            f"INVALID: pydantic {version} is not v1. These goldens are the v1 wire\n"
            "contract; generating them under v2 would assert v2 against itself.\n"
            "Run this from a pre-migration checkout, or pass --allow-v2 knowingly.",
            file=sys.stderr,
        )
        return EXIT_INVALID

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    written, failures = 0, []
    for case in CASES:
        try:
            model = resolve(case.model)
            if case.builder:
                from payload_builders import BUILDERS

                instance = BUILDERS[case.builder]()
            else:
                instance = model.parse_obj(case.payload)
            record = {
                "case": case.name,
                "model": case.model,
                "note": case.note,
                "pydantic": str(version),
                "payload": case.payload,
                "builder": case.builder,
                # Stored parsed, not as a string: the contract is the JSON
                # document, not the byte order pydantic happened to emit.
                "json": json.loads(instance.json()),
                "json_by_alias": json.loads(instance.json(by_alias=True)),
                # The python-mode dump, type-preserved. JSON mode unwraps enums
                # whatever the config says, so without this the corpus cannot
                # see the use_enum_values trap - see canon.py.
                "dict": canonical(instance.dict()),
                "dict_by_alias": canonical(instance.dict(by_alias=True)),
                # What v1 produces when it PARSES its own wire document and
                # re-serializes. Not always equal to `json_by_alias`: parsing a
                # dict yields the field's DECLARED type, so a document carrying
                # a subclass field comes back without it - on v1 too. Recording
                # v1's own answer keeps the reverse assertion meaningful for
                # those cases instead of demanding something that was never true.
                "json_reparsed": json.loads(
                    model.parse_obj(json.loads(instance.json(by_alias=True))).json(
                        by_alias=True
                    )
                ),
            }
        except Exception as exc:  # noqa: BLE001 - report, do not abort the sweep
            failures.append(f"{case.name}: {type(exc).__name__}: {exc}")
            continue

        (out_dir / f"{case.name}.json").write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n"
        )
        written += 1

    print(f"wrote {written}/{len(CASES)} goldens to {out_dir}")
    if failures:
        print("\nFAILED to capture:", file=sys.stderr)
        for line in failures:
            print(f"  {line}", file=sys.stderr)
        return EXIT_FAIL
    return EXIT_PASS


if __name__ == "__main__":
    sys.exit(main())
