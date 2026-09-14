# OpenFGA language transformer fixtures

The `*.fga` / `*.json` pairs in this directory are the official
[OpenFGA language](https://github.com/openfga/language) dsl->json transformer
test cases (Apache-2.0), vendored so `openfga_dsl_test.py` can validate that
OPAL's DSL transpiler produces byte-for-byte semantically identical output to
the official transformer.

To refresh them, re-download
`tests/data/transformer/<case>/authorization-model.{fga,json}` from the
openfga/language repository and rename them to `<case>.fga` / `<case>.json`.
