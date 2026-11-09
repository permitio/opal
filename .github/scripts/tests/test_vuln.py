"""Tests of .github/scripts/vuln.sh: its scan and --prepare modes, its exit
codes, its failure paths, and that its output stays inside a stop-commands
block.

Each test runs the script in a throwaway copy of the repository where
fetch-tool.sh, trivy.sh and bin/uv are fakes that record how they were
run, so no test uses the network.
"""

import re
from pathlib import Path

import pytest

SCRIPT = ".github/scripts/vuln.sh"
REQUIREMENTS = [
    "packages/requires.txt",
    "packages/opal-common/requires.txt",
    "packages/opal-client/requires.txt",
    "packages/opal-server/requires.txt",
]

# Each fake appends a line to its log in FAKE_LOG: its arguments, and whether GH_TOKEN and
# GITHUB_TOKEN reached it.
FAKE_FETCH_TOOL = r"""set -euo pipefail
printf '%s %s %s\n' "$1" "${GH_TOKEN-unset}" "${GITHUB_TOKEN-unset}" >>"$FAKE_LOG/fetch-tool"
if [[ " ${FAKE_FETCH_FAILS:-} " == *" $1 "* ]]; then
  echo "fetch-tool: downloading $1 failed" >&2
  exit 2
fi
echo "$PWD/bin/$1"
"""

# The fake uv writes a tree of one pin to the -o file: the floor with --resolution lowest-direct,
# the ceiling without. FAKE_UV_FAILS names a tree it fails to resolve.
FAKE_UV = r"""set -euo pipefail
tree=ceiling
out=''
args=("$@")
for ((i = 0; i < $#; i++)); do
  case ${args[i]} in
  --resolution) [[ ${args[i + 1]} != lowest-direct ]] || tree=floor ;;
  -o) out=${args[i + 1]} ;;
  esac
done
printf '%s %s %s %s\n' "$tree" "${GH_TOKEN-unset}" "${GITHUB_TOKEN-unset}" "$*" >>"$FAKE_LOG/uv"
if [[ ${FAKE_UV_FAILS:-} == "$tree" ]]; then
  echo "error: no solution for the $tree" >&2
  exit 1
fi
printf 'pkg==1.0  # the %s\n' "$tree" >"$out"
"""

# The fake trivy.sh exits with FAKE_TRIVY_FLOOR or FAKE_TRIVY_CEILING (0 when not set), after it
# logs its policy, the tree it was given and the first line of that tree's file.
FAKE_TRIVY = r"""set -euo pipefail
tree=$(basename -- "$(dirname -- "$2")")
printf '%s %s %s %s [%s]\n' "$1" "$tree" "${GH_TOKEN-unset}" "${GITHUB_TOKEN-unset}" \
  "$(head -n 1 -- "$2")" >>"$FAKE_LOG/trivy"
echo "::error::trivy.sh output that must not be a workflow command"
case $tree in
floor) exit "${FAKE_TRIVY_FLOOR:-0}" ;;
ceiling) exit "${FAKE_TRIVY_CEILING:-0}" ;;
esac
exit 99
"""


class Vuln:
    """A throwaway repository with vuln.sh and fakes of what it runs."""

    def __init__(self, repo, tmp_path: Path) -> None:
        self.repo = repo
        self.log = tmp_path / "log"
        self.log.mkdir()
        repo.copy(SCRIPT)
        repo.write(
            ".github/scripts/fetch-tool.sh",
            "#!/usr/bin/env bash\n" + FAKE_FETCH_TOOL,
            True,
        )
        repo.write(
            ".github/scripts/trivy.sh", "#!/usr/bin/env bash\n" + FAKE_TRIVY, True
        )
        repo.write("bin/uv", "#!/usr/bin/env bash\n" + FAKE_UV, True)

    def run(self, *args: str, **env: str):
        return self.repo.run(SCRIPT, *args, env={"FAKE_LOG": str(self.log), **env})

    def logged(self, name: str) -> list[str]:
        """The lines a fake logged, or [] when it did not run."""
        path = self.log / name
        return path.read_text().splitlines() if path.exists() else []


@pytest.fixture
def vuln(throwaway_repo, tmp_path):
    return Vuln(throwaway_repo, tmp_path)


def verdict(stdout: str) -> str:
    """The last line before the line that resumes workflow commands."""
    return stdout.splitlines()[-2]


@pytest.mark.parametrize(
    ("floor", "ceiling", "code", "line"),
    [
        (0, 0, 0, "vuln: PASS"),
        (1, 0, 1, "vuln: FAIL"),
        (0, 1, 1, "vuln: FAIL"),
        (1, 1, 1, "vuln: FAIL"),
        (2, 0, 2, "vuln: DID NOT RUN"),
        (0, 2, 2, "vuln: DID NOT RUN"),
        (2, 1, 2, "vuln: DID NOT RUN"),
        (1, 2, 2, "vuln: DID NOT RUN"),
        (5, 0, 2, "vuln: DID NOT RUN"),
    ],
)
def test_scans_both_trees_and_reports_the_worst(vuln, floor, ceiling, code, line):
    result = vuln.run(FAKE_TRIVY_FLOOR=str(floor), FAKE_TRIVY_CEILING=str(ceiling))

    assert result.returncode == code, result.output
    assert verdict(result.stdout) == line
    assert [entry.split()[:2] for entry in vuln.logged("trivy")] == [
        ["block", "floor"],
        ["block", "ceiling"],
    ], "both trees are scanned with the block policy, whatever the first scan found"


def test_resolves_the_floor_and_the_ceiling_of_the_published_ranges(vuln):
    result = vuln.run()

    assert result.returncode == 0, result.output
    uv = vuln.logged("uv")
    assert [entry.split()[0] for entry in uv] == ["floor", "ceiling"]
    for entry in uv:
        assert all(f" {requirements} " in entry for requirements in REQUIREMENTS)
    trivy = vuln.logged("trivy")
    assert trivy[0].endswith("[pkg==1.0  # the floor]")
    assert trivy[1].endswith("[pkg==1.0  # the ceiling]")
    assert [entry.split()[0] for entry in vuln.logged("fetch-tool")] == ["uv", "trivy"]


def test_prepare_writes_the_trees_and_scans_nothing(vuln, tmp_path):
    trees = tmp_path / "trees"

    result = vuln.run("--prepare", str(trees))

    assert result.returncode == 0, result.output
    assert (
        trees / "floor" / "requirements.txt"
    ).read_text() == "pkg==1.0  # the floor\n"
    assert (
        trees / "ceiling" / "requirements.txt"
    ).read_text() == "pkg==1.0  # the ceiling\n"
    assert vuln.logged("trivy") == []
    assert f"vuln: prepared uv, Trivy and the trees in {trees}" in result.stdout


def test_prepare_into_a_directory_that_exists(vuln, tmp_path):
    trees = tmp_path / "trees"
    trees.mkdir()
    (trees / "keep.txt").write_text("keep\n")

    result = vuln.run("--prepare", str(trees))

    assert result.returncode == 2
    assert f"creating {trees} failed; it must not exist" in result.stdout
    assert verdict(result.stdout) == "vuln: DID NOT RUN"
    assert sorted(path.name for path in trees.iterdir()) == ["keep.txt"]
    assert vuln.logged("uv") == []


@pytest.mark.parametrize(
    "args",
    [
        pytest.param(("--prepare",), id="--prepare without a directory"),
        pytest.param(("--prepare", ""), id="--prepare with an empty directory"),
        pytest.param(("--prepare", "a", "b"), id="three arguments"),
        pytest.param(("--other", "a"), id="another option"),
        pytest.param(("scan",), id="one argument"),
    ],
)
def test_wrong_arguments(vuln, args):
    result = vuln.run(*args)

    assert result.returncode == 2
    assert "vuln: usage: vuln.sh [--prepare <directory>]" in result.stdout
    assert vuln.logged("fetch-tool") == []


@pytest.mark.parametrize(("tool", "message"), [("uv", "uv"), ("trivy", "Trivy")])
def test_a_tool_that_cannot_be_installed(vuln, tool, message):
    result = vuln.run(FAKE_FETCH_FAILS=tool)

    assert result.returncode == 2
    assert f"vuln: installing {message} failed" in result.stdout
    assert verdict(result.stdout) == "vuln: DID NOT RUN"
    assert vuln.logged("uv") == []
    assert vuln.logged("trivy") == []


@pytest.mark.parametrize("tree", ["floor", "ceiling"])
@pytest.mark.parametrize("prepare", [False, True])
def test_a_tree_that_cannot_be_resolved(vuln, tmp_path, tree, prepare):
    args = ("--prepare", str(tmp_path / "trees")) if prepare else ()

    result = vuln.run(*args, FAKE_UV_FAILS=tree)

    assert result.returncode == 2
    assert f"vuln: resolving the {tree} failed" in result.stdout
    assert verdict(result.stdout) == "vuln: DID NOT RUN"
    assert vuln.logged("trivy") == []


@pytest.mark.parametrize(
    ("args", "env"),
    [
        pytest.param((), {}, id="a passing scan"),
        pytest.param((), {"FAKE_TRIVY_FLOOR": "1"}, id="a failing scan"),
        pytest.param((), {"FAKE_FETCH_FAILS": "uv"}, id="a scan that did not run"),
        pytest.param(("--bad",), {}, id="wrong arguments"),
    ],
)
def test_prints_everything_with_workflow_commands_stopped(vuln, args, env):
    result = vuln.run(*args, **env)

    lines = result.stdout.splitlines()
    start = re.fullmatch(r"::stop-commands::([0-9a-f]{32})", lines[0])
    assert start, f"the first line does not stop workflow commands: {lines[0]!r}"
    assert lines[-1] == f"::{start.group(1)}::"
    assert result.stdout.count(start.group(1)) == 2


def test_the_tools_run_without_the_github_tokens(vuln):
    result = vuln.run(GH_TOKEN="gh-token", GITHUB_TOKEN="github-token")

    assert result.returncode == 0, result.output
    logged = vuln.logged("fetch-tool") + vuln.logged("uv") + vuln.logged("trivy")
    assert len(logged) == 6
    for entry in logged:
        assert "gh-token" not in entry
        assert "github-token" not in entry
