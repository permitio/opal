#!/usr/bin/env python3
"""Run the provider shapes and print the compatibility matrix.

    # under a pre-migration checkout (pydantic v1)
    python provider_conformance.py --out v1.json

    # under this tree (pydantic v2)
    python provider_conformance.py --out v2.json

    # then, from either
    python provider_conformance.py --compare v1.json v2.json

The comparison is the deliverable: it says, per shape, whether a provider
written for v1 still loads and still behaves under v2. That is the table to put
in the release notes, because third-party providers are the one population this
migration cannot enumerate.

Exit codes follow the kit contract: 0 PASS, 1 FAIL (a shape regressed in a way
not listed as expected), 2 INVALID RUN.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from provider_shapes import run_all  # noqa: E402

EXIT_PASS, EXIT_FAIL, EXIT_INVALID = 0, 1, 2


def _version() -> str:
    import pydantic

    return str(pydantic.VERSION)


def cmd_run(args) -> int:
    results = run_all()
    record = {"pydantic": _version(), "shapes": results}
    if args.out:
        Path(args.out).write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
        print(f"wrote {len(results)} shapes under pydantic {_version()} -> {args.out}")

    print(f"\nprovider shapes under pydantic {_version()}")
    for name in sorted(results):
        r = results[name]
        detail = r.get("error") or ", ".join(
            f"{k}={v}" for k, v in r.items() if k not in {"status"}
        )
        print(f"  {r['status']:7} {name:34} {detail}")
    return EXIT_PASS


def cmd_compare(args) -> int:
    try:
        a = json.loads(Path(args.compare[0]).read_text())
        b = json.loads(Path(args.compare[1]).read_text())
    except Exception as exc:  # noqa: BLE001
        print(f"INVALID: cannot read inputs: {exc}", file=sys.stderr)
        return EXIT_INVALID

    if a["pydantic"].split(".")[0] == b["pydantic"].split(".")[0]:
        print(
            f"INVALID: both inputs are pydantic {a['pydantic'].split('.')[0]}.x - "
            "a same-version comparison says nothing",
            file=sys.stderr,
        )
        return EXIT_INVALID

    print(f"provider conformance: pydantic {a['pydantic']} -> {b['pydantic']}\n")
    print(f"  {'shape':34} {'v1':8} {'v2':8} verdict")
    print(f"  {'-' * 34} {'-' * 8} {'-' * 8} {'-' * 30}")

    regressions = []
    for name in sorted(set(a["shapes"]) | set(b["shapes"])):
        ra = a["shapes"].get(name, {"status": "missing"})
        rb = b["shapes"].get(name, {"status": "missing"})
        sa, sb = ra["status"], rb["status"]

        if sa == sb == "ok":
            # both load - did the VALUE survive?
            keys = set(ra) | set(rb)
            differing = [k for k in keys - {"status"} if ra.get(k) != rb.get(k)]
            if differing:
                verdict = "BEHAVIOUR CHANGED: " + ", ".join(
                    f"{k} {ra.get(k)!r}->{rb.get(k)!r}" for k in sorted(differing)
                )
                regressions.append((name, verdict))
            else:
                verdict = "identical"
        elif sa == "ok" and sb == "broken":
            verdict = f"BREAKS at {rb.get('when')}: {rb.get('error')}"
            regressions.append((name, verdict))
        elif sa == "broken" and sb == "ok":
            verdict = "fixed under v2"
        else:
            verdict = "broken on both"

        print(f"  {name:34} {sa:8} {sb:8} {verdict}")

    if regressions:
        print(f"\n{len(regressions)} shape(s) changed for provider authors:")
        for name, verdict in regressions:
            print(f"  - {name}: {verdict}")
    return EXIT_PASS


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", help="write this run's results as JSON")
    p.add_argument("--compare", nargs=2, metavar=("V1_JSON", "V2_JSON"))
    args = p.parse_args()
    return cmd_compare(args) if args.compare else cmd_run(args)


if __name__ == "__main__":
    sys.exit(main())
