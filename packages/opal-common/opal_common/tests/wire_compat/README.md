# wire_compat — the pydantic v1 wire contract, asserted forever

Every OPAL client in the field runs `opal-client` 0.9.6, which is **pydantic
v1** (`0.9.9-rc.2`, the newest tag, still pins `pydantic[email]>=1.9.1,<2`). A
pydantic-v2 server therefore publishes to, and is posted to by, v1 peers.

Ordinary unit tests cannot see a break there, because they exercise both sides
at the same version. This corpus pins the v1 wire form so the v2 tree is
asserted against a peer it can no longer import.

```
payloads.py          the corpus: inputs only, no pydantic import
canon.py             type-preserving rendering of a python-mode dump
generate_golden.py   run ONCE under pydantic v1 to capture golden/
golden/*.json        the contract - one file per case
wire_compat_test.py  what CI runs
```

## What each case asserts

| assertion | direction | catches |
|---|---|---|
| `test_serializes_as_pydantic_v1_did` | v2 → v1 peer | a v1 client can still read what a v2 server emits |
| `test_parses_what_pydantic_v1_emitted` | v1 peer → v2 | a v2 server still accepts what a v1 client sends |
| `test_python_mode_dump_matches_pydantic_v1` | internal | enum/Path/Url objects surviving a dump |
| `test_published_payload_is_json_serializable` | internal | `json.dumps` on a dump |

Equality is on the **parsed JSON document**, not the byte string — key order is
not part of any wire contract and no JSON parser can observe it.

### Why python mode is asserted separately

`model_dump_json()` unwraps enums, datetimes and `Path`s whatever the model
config says. A JSON-only corpus therefore **cannot see** the trap that broke
inline OPA startup and left non-serialisable publish payloads: under v2
`use_enum_values` fires at *validation* time and defaults are never validated,
so `model_dump()` in python mode hands back the enum **member**.

`canon.py` renders a python-mode dump into a JSON-safe structure that keeps the
type visible, so `'get'` vs `HttpMethods.GET` is an ordinary readable diff:

```
'get'             ->  "get"
HttpMethods.GET   ->  {"__enum__": "HttpMethods.GET", "value": "get"}
PosixPath('a/b')  ->  {"__path__": "a/b"}
```

## Regenerating the goldens

**Do not regenerate them from this tree.** They are the *pre-migration*
contract; capturing them under v2 would assert v2 against itself and prove
nothing. `generate_golden.py` refuses to run under v2 for that reason.

```bash
# from a checkout of a PRE-MIGRATION commit (pydantic v1)
git worktree add /tmp/opal-v1 <pre-migration-sha>
cd /tmp/opal-v1 && python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python <this-tree>/packages/opal-common/opal_common/tests/wire_compat/generate_golden.py \
    --out <this-tree>/packages/opal-common/opal_common/tests/wire_compat/golden
```

The generator imports `payloads.py` from **this** tree and `opal_common` from
the v1 checkout, so both sides see identical inputs.

## Adding a case

Add a `Case` to `payloads.py` whenever a model reaches the wire — published to
clients, served by a route, persisted to Redis, or posted back by a client —
then regenerate. `test_corpus_covers_every_golden` fails if a golden has no
case (it would silently stop being asserted) or a case has no golden.

Pin anything non-deterministic (uuids, timestamps) in the payload. A golden
that changes run to run cannot be compared.

## Accepted deltas

A difference we have decided to keep goes in `ACCEPTED_DELTAS` **with the
evidence that established it is safe** — not just a claim that it is. Nothing
is tolerated silently. The current entries are all python-mode-only; every
JSON-form assertion passes, so the wire itself is unchanged.

## What this does not cover

- **behaviour**, only serialisation. A field that serialises identically but is
  interpreted differently downstream passes here.
- **third-party fetch providers**, whose models live outside this repo.
- **the live fleet.** For that, point the OPAL staging bed (60 real
  `opal-client:0.9.6` PDPs — pydantic v1) at a v2 server and run its integrity
  checker, which reads data back out of each PDP's own OPA store.
