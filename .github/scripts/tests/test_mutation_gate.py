"""Tests of .github/scripts/mutation_gate.py: which lines it mutates and how,
the sample and the report, and whole runs on a throwaway repository with a
small package whose tests do or do not kill its mutants.

The whole runs use real git, pytest and pytest-cov (from the pinned
requirements of these tests) on the throwaway copy only.
"""

import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPT = ".github/scripts/mutation_gate.py"
SPEC = importlib.util.spec_from_file_location(
    "mutation_gate", Path(__file__).resolve().parents[1] / "mutation_gate.py"
)
assert SPEC is not None and SPEC.loader is not None
gate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gate
SPEC.loader.exec_module(gate)


def labels(source: str, lines: set[int]) -> list[str]:
    return [mutant.label() for mutant in gate.mutants_of("p.py", source, lines)]


@pytest.mark.parametrize(
    ("path", "source"),
    [
        ("packages/opal-server/opal_server/git_fetcher.py", True),
        ("packages/opal-common/opal_common/tests/thing.py", False),
        ("packages/opal-server/opal_server/x_test.py", False),
        ("packages/opal-server/opal_server/test_x.py", False),
        ("packages/opal-server/conftest.py", False),
        ("packages/opal-server/setup.py", False),
        ("packages/opal-server/README.md", False),
        ("packages/__packaging__.py", False),
        ("packages/opal-server/opal_server/tests/fixtures/repo.py", False),
        ("scripts/check_trust_store.py", False),
    ],
)
def test_mutates_package_source_only(path, source):
    assert gate.is_source(path) is source


def test_reads_the_added_lines_of_a_diff():
    diff = "\n".join(
        [
            "diff --git a/packages/a/a/x.py b/packages/a/a/x.py",
            "--- a/packages/a/a/x.py",
            "+++ b/packages/a/a/x.py",
            "@@ -3 +3,2 @@ def f():",
            "@@ -10,4 +11,0 @@",
            "@@ -20 +20 @@",
            "--- a/packages/a/a/gone.py",
            "+++ /dev/null",
            "@@ -1,2 +0,0 @@",
            "--- a/packages/a/a/tests/x_test.py",
            "+++ b/packages/a/a/tests/x_test.py",
            "@@ -1 +1,5 @@",
        ]
    )

    assert gate.parse_diff(diff) == {"packages/a/a/x.py": {3, 4, 20}}


def test_mutates_each_operator_on_the_given_lines_only():
    source = (
        "def f(a, b):\n"
        "    if a == b and not a:\n"
        "        return a + b > 10 or True\n"
        "    return a != b or a <= b and a is None\n"
    )

    assert labels(source, {2, 3}) == [
        "p.py:2: == -> !=",
        "p.py:2: and -> or",
        "p.py:2: not -> (dropped)",
        "p.py:3: + -> -",
        "p.py:3: > -> >=",
        "p.py:3: 10 -> 11",
        "p.py:3: or -> and",
        "p.py:3: True -> False",
    ]
    assert labels(source, {4}) == [
        "p.py:4: != -> ==",
        "p.py:4: or -> and",
        "p.py:4: <= -> <",
        "p.py:4: and -> or",
        "p.py:4: is -> is not",
    ]


def test_is_not_and_not_in_lose_their_not():
    source = "x = a is not None and b not in c\n"

    assert labels(source, {1}) == [
        "p.py:1: not -> (dropped)",
        "p.py:1: and -> or",
        "p.py:1: not -> (dropped)",
    ]


@pytest.mark.parametrize(
    "source",
    [
        "x = -1\n",
        "f(-a, +b)\n",
        "x = [1, -2][0]\n",
        "def g():\n    return -a\n",
    ],
)
def test_a_sign_is_not_a_binary_operator(source):
    assert all(
        "-> +" not in label and "-> -" not in label for label in labels(source, {1, 2})
    )


def test_strings_and_comments_are_not_mutated():
    source = 'x = "a == b and 1"  # c == d or True\n'

    assert labels(source, {1}) == []


def test_a_file_that_does_not_tokenize_has_no_mutants():
    assert labels('x = """never closed\n', {1}) == []


def test_a_mutant_must_compile():
    assert gate.compiles("x = a is not 1\n")
    assert not gate.compiles("x = (\n")


def test_applying_a_mutant_that_does_not_match_the_source_fails():
    mutant = gate.Mutant("p.py", 1, 4, "==", "!=")

    with pytest.raises(gate.NotRun, match="does not match"):
        gate.apply("x = a != b\n", mutant)


def test_the_sample_is_capped_seeded_and_in_file_order():
    mutants = [gate.Mutant("p.py", line, 0, "1", "2") for line in range(1, 1001)]

    first = gate.sample(mutants, 300, "abc")
    again = gate.sample(list(reversed(mutants)), 300, "abc")
    other = gate.sample(mutants, 300, "def")

    assert len(first) == 300
    assert first == again == sorted(first)
    assert first != other
    assert gate.sample(mutants[:5], 300, "abc") == mutants[:5]
    assert gate.sample(mutants, None, "abc") == mutants


def test_the_report_lists_survivors_up_to_a_limit():
    outcomes = {
        gate.Mutant("p.py", line, 0, "1", "2"): "survived" for line in range(1, 61)
    }
    outcomes[gate.Mutant("p.py", 99, 0, "1", "2")] = "killed"

    report = gate.render(outcomes, 1 / 61, "lines changed since main")

    assert (
        "Score 2% (gate 80%): 1 killed, 60 survived, 0 not covered, 0 not run, 0 error"
        in report
    )
    assert "- `p.py:50: 1 -> 2`" in report
    assert "- `p.py:51: 1 -> 2`" not in report
    assert "- and 10 more" in report


CALC_BASE = "def double(x):\n    return x * 2\n"
CALC_HEAD = CALC_BASE + "\n\ndef is_big(n):\n    return n > 10\n"
STRONG_TESTS = (
    "from demo.calc import double, is_big\n\n\n"
    "def test_double():\n    assert double(2) == 4\n\n\n"
    "def test_is_big():\n"
    "    assert is_big(12)\n"
    "    assert is_big(11)\n"
    "    assert not is_big(10)\n"
)
WEAK_TESTS = (
    "from demo.calc import double, is_big\n\n\n"
    "def test_double():\n    assert double(2) == 4\n\n\n"
    "def test_is_big():\n    assert is_big(100)\n"
)


class Repository:
    """A throwaway git repository with the script, a package demo, and a commit
    to diff against."""

    def __init__(self, repo) -> None:
        self.repo = repo
        repo.copy(SCRIPT)
        repo.write(
            "run-gate.sh",
            f'#!/usr/bin/env bash\nexec {sys.executable} {SCRIPT} "$@"\n',
            executable=True,
        )
        repo.write("pytest.ini", "[pytest]\n")
        repo.write("packages/demo/demo/__init__.py", "")
        repo.write("packages/demo/demo/tests/__init__.py", "")
        repo.write("packages/demo/demo/calc.py", CALC_BASE)
        repo.write(
            "packages/demo/demo/tests/calc_test.py",
            "from demo.calc import double\n\n\ndef test_double():\n"
            "    assert double(2) == 4\n",
        )
        self.git("init", "-q", "-b", "main")
        self.commit("base")

    def git(self, *args: str) -> str:
        env = {
            "PATH": os.environ["PATH"],
            "HOME": str(self.repo.home),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.invalid",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.invalid",
        }
        return subprocess.run(
            ["git", *args],
            cwd=self.repo.root,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        ).stdout

    def commit(self, message: str) -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    def change(self, calc: str, tests: str) -> None:
        self.repo.write("packages/demo/demo/calc.py", calc)
        self.repo.write("packages/demo/demo/tests/calc_test.py", tests)
        self.commit("change")

    def run(self, *args: str, **env: str):
        return self.repo.run("run-gate.sh", *args, env=env)


@pytest.fixture
def repository(throwaway_repo):
    return Repository(throwaway_repo)


def test_a_change_whose_tests_kill_its_mutants_passes(repository):
    repository.change(CALC_HEAD, STRONG_TESTS)

    result = repository.run("--base", "main~1")

    assert result.returncode == 0, result.output
    assert "mutation: 2 mutants in 1 files; running 2" in result.stdout
    assert "Score 100% (gate 80%): 2 killed, 0 survived" in result.stdout
    assert result.stdout.splitlines()[-1] == "mutation: PASS"


def test_a_change_whose_tests_miss_its_mutants_fails_and_names_them(
    repository, tmp_path
):
    repository.change(CALC_HEAD, WEAK_TESTS)
    summary = tmp_path / "summary.md"

    result = repository.run("--base", "main~1", "--summary", str(summary))

    assert result.returncode == 1, result.output
    assert "Score 0% (gate 80%): 0 killed, 2 survived" in result.stdout
    assert "- `packages/demo/demo/calc.py:6: > -> >=`" in summary.read_text()
    assert "- `packages/demo/demo/calc.py:6: 10 -> 11`" in summary.read_text()
    assert result.stdout.splitlines()[-1] == "mutation: FAIL: the score 0% is below 80%"


def test_every_mutated_file_is_restored(repository):
    repository.change(CALC_HEAD, WEAK_TESTS)
    calc = repository.repo.root / "packages/demo/demo/calc.py"
    mtime = calc.stat().st_mtime_ns

    repository.run("--base", "main~1")

    assert repository.git("status", "--porcelain", "--untracked-files=no") == ""
    assert calc.stat().st_mtime_ns == mtime


def test_a_run_whose_mutants_no_test_covers_did_not_run(repository, tmp_path):
    repository.change(CALC_HEAD, "def test_nothing():\n    pass\n")
    summary = tmp_path / "summary.md"

    result = repository.run("--base", "main~1", "--summary", str(summary))

    assert result.returncode == 2, result.output
    assert "0 killed, 0 survived, 2 not covered" in result.stdout
    assert (
        "DID NOT RUN: none of the 2 mutants ran against a covering test"
        in result.stdout
    )
    assert "DID NOT RUN: none of the 2 mutants" in summary.read_text()


def test_a_change_to_tests_only_has_no_mutants(repository):
    repository.change(
        CALC_BASE,
        STRONG_TESTS.replace(", is_big", "").split("\n\n\ndef test_is_big")[0],
    )

    result = repository.run("--base", "main~1")

    assert result.returncode == 0, result.output
    assert "mutation: 0 mutants in 0 files; running 0" in result.stdout


def test_a_suite_that_fails_before_any_mutant_did_not_run(repository):
    repository.change(
        CALC_HEAD, WEAK_TESTS + "\n\ndef test_broken():\n    assert False\n"
    )

    result = repository.run("--base", "main~1")

    assert result.returncode == 2
    assert (
        "DID NOT RUN: the suite of packages/demo fails before any mutant"
        in result.stdout
    )


@pytest.mark.parametrize(
    "args",
    [
        pytest.param((), id="neither --base nor --full"),
        pytest.param(("--base", "main", "--full"), id="both"),
    ],
)
def test_wrong_arguments(repository, args):
    assert repository.run(*args).returncode == 2


def test_an_unknown_base_did_not_run(repository):
    result = repository.run("--base", "no-such-branch")

    assert result.returncode == 2
    assert "DID NOT RUN: git merge-base" in result.stdout


def test_mutants_past_the_budget_are_not_run(repository, monkeypatch, tmp_path):
    repository.change(CALC_HEAD, WEAK_TESTS)
    monkeypatch.setattr(gate, "ROOT", repository.repo.root)
    monkeypatch.setattr(gate, "BUDGET_SECONDS", 0)
    monkeypatch.chdir(repository.repo.root)

    run = gate.gate(gate.parse_args(["--base", "main~1"]), tmp_path)

    assert set(run.outcomes.values()) == {"not run"}
    assert run.score is None
    assert gate.verdict(run, full=False)[0] == 2


def test_no_more_mutants_than_the_cap_run(repository, monkeypatch, tmp_path):
    repository.change(CALC_HEAD, STRONG_TESTS)
    monkeypatch.setattr(gate, "ROOT", repository.repo.root)
    monkeypatch.setattr(gate, "MAX_MUTANTS", 1)
    monkeypatch.chdir(repository.repo.root)

    run = gate.gate(gate.parse_args(["--base", "main~1"]), tmp_path)

    assert list(run.outcomes.values()) == ["killed"]
    assert run.score == 1


def test_the_report_says_when_the_budget_was_reached():
    outcomes = {gate.Mutant("p.py", 1, 0, "1", "2"): "killed"}
    outcomes[gate.Mutant("p.py", 2, 0, "1", "2")] = "not run"
    outcomes[gate.Mutant("p.py", 3, 0, "1", "2")] = "not run"

    report = gate.render(outcomes, 1.0, "lines changed since main")

    assert "Budget reached: 2 of 3 mutants were not run" in report
    assert gate.verdict(gate.Run(outcomes, [], 1.0), full=False) == (
        0,
        "mutation: PASS (budget reached: 2 not run)",
    )


@pytest.mark.parametrize(
    ("run", "full", "code"),
    [
        pytest.param(gate.Run({}, [], None), False, 0, id="no mutants"),
        pytest.param(
            gate.Run({gate.Mutant("p", 1, 0, "1", "2"): "survived"}, [], 0.0),
            True,
            0,
            id="full below the gate",
        ),
        pytest.param(
            gate.Run({gate.Mutant("p", 1, 0, "1", "2"): "survived"}, [], 0.0),
            False,
            1,
            id="a change below the gate",
        ),
        pytest.param(
            gate.Run(
                {gate.Mutant("p", 1, 0, "1", "2"): "error"},
                ["x: pytest exited 4"],
                None,
            ),
            True,
            2,
            id="an error in full",
        ),
    ],
)
def test_the_verdict(run, full, code):
    assert gate.verdict(run, full)[0] == code


def test_the_run_order_takes_the_packages_in_turn_and_is_seeded():
    mutants = [
        gate.Mutant(f"packages/{package}/m/x.py", line, 0, "1", "2")
        for package in ("a", "b", "c")
        for line in range(1, 5)
    ]

    order = gate.run_order(mutants, "seed")
    again = gate.run_order(list(reversed(mutants)), "seed")

    assert order == again
    assert sorted(order) == sorted(mutants)
    assert [gate.package_of(m.path) for m in order[:6]] == [
        "packages/a",
        "packages/b",
        "packages/c",
        "packages/a",
        "packages/b",
        "packages/c",
    ]
    assert order != gate.run_order(mutants, "other seed")


def test_a_diff_path_with_a_space_keeps_its_name():
    diff = "+++ b/packages/a/a/my file.py\t\n@@ -1 +1 @@\n"

    assert gate.parse_diff(diff) == {"packages/a/a/my file.py": {1}}


def test_a_crlf_file_with_a_form_feed_and_a_line_separator_mutates_in_place():
    source = 'x = "\x0c\u2028"\r\ny = a == b\r\n'

    (mutant,) = gate.mutants_of("p.py", source, {2})

    assert gate.apply(source, mutant) == 'x = "\x0c\u2028"\r\ny = a != b\r\n'


@pytest.mark.parametrize(
    "source",
    [
        "x = 1 if a else -1\n",
        "x = a in -b\n",
        "x += -1\n",
        "x = (y := -1)\n",
        "y = a\n-x\n",
    ],
)
def test_more_signs_are_not_binary_operators(source):
    assert all("-> +" not in label for label in labels(source, {1, 2}))


def test_the_node_id_of_a_context_keeps_a_pipe_in_its_parameters():
    assert gate.node_id_of("t_test.py::test_x[a|b]|run") == "t_test.py::test_x[a|b]"


CALC_TWO_TESTS = (
    "from demo.calc import double, is_big\n\n\n"
    "def test_double():\n    assert double(2) == 4\n\n\n"
    "def test_is_big_first():\n    is_big(100)\n\n\n"
    "def test_is_big_second():\n"
    "    assert is_big(11)\n"
    "    assert not is_big(10)\n"
)


def test_a_mutant_runs_every_test_on_its_line_even_under_the_monitoring_core(
    repository,
):
    """The first test only runs the line; only the second kills its mutants.

    COVERAGE_CORE=sysmon is the default on Python 3.14, and it records a
    line for its first test only; the gate forces the C tracer.
    """
    repository.change(CALC_HEAD, CALC_TWO_TESTS)

    result = repository.run("--base", "main~1", COVERAGE_CORE="sysmon")

    assert result.returncode == 0, result.output
    assert "2 killed, 0 survived" in result.stdout


def test_a_line_that_runs_at_import_is_tested_by_its_modules_tests(repository):
    calc = "LIMIT = 10\n\n\ndef is_big(n):\n    return n > LIMIT\n"
    tests = (
        "from demo.calc import LIMIT, is_big\n\n\n"
        "def test_limit():\n    assert LIMIT == 10\n\n\n"
        "def test_is_big():\n    assert is_big(11)\n    assert not is_big(10)\n"
    )
    repository.change(calc, tests)

    result = repository.run("--base", "main~1")

    assert result.returncode == 0, result.output
    assert "killed: packages/demo/demo/calc.py:1: 10 -> 11" in result.stdout
    assert "0 not covered" in result.stdout


def test_the_full_run_skips_a_module_outside_a_package_and_reports_only(repository):
    repository.repo.write("packages/__packaging__.py", "VERSION = (0, 0, 1)\n")
    repository.change(CALC_HEAD, WEAK_TESTS)

    result = repository.run("--full")

    assert result.returncode == 0, result.output
    assert "mutation: 3 mutants in 2 files; running 3" in result.stdout
    assert "__packaging__" not in result.stdout
    assert "Score 33% (gate 80%): 1 killed, 2 survived" in result.stdout
    assert result.stdout.splitlines()[-1] == "mutation: PASS"


def test_a_mutant_whose_tests_cannot_run_is_an_error(repository, monkeypatch):
    repository.change(CALC_HEAD, WEAK_TESTS)
    monkeypatch.setattr(gate, "ROOT", repository.repo.root)
    monkeypatch.chdir(repository.repo.root)
    mutant = gate.Mutant("packages/demo/demo/calc.py", 6, 13, ">", ">=")

    outcome, reason = gate.run_mutant(
        mutant, ["packages/demo/demo/tests/calc_test.py::test_missing"], 0.1
    )

    assert outcome == "error"
    assert reason.startswith("pytest exited 4")


HANGS_WHEN_MUTATED = (
    "def countdown(n):\n    while n > 0:\n        n = n - 1\n    return n\n"
)


@pytest.mark.parametrize("unmutated", [0.1, 0.75])
def test_a_mutant_that_hangs_its_tests_is_killed_after_the_scaled_timeout(
    repository, monkeypatch, unmutated
):
    repository.change(
        HANGS_WHEN_MUTATED,
        "from demo.calc import countdown\n\n\ndef test_countdown():\n"
        "    assert countdown(3) == 0\n",
    )
    monkeypatch.setattr(gate, "ROOT", repository.repo.root)
    monkeypatch.setattr(gate, "MUTANT_TIMEOUT_SECONDS", 2)
    monkeypatch.chdir(repository.repo.root)
    calc = repository.repo.root / "packages/demo/demo/calc.py"
    before = calc.read_bytes()
    mutant = gate.Mutant("packages/demo/demo/calc.py", 3, 14, "-", "+")

    started = time.monotonic()
    result = gate.run_mutant(
        mutant, ["packages/demo/demo/tests/calc_test.py::test_countdown"], unmutated
    )

    assert result == ("killed", "")
    assert time.monotonic() - started >= gate.mutant_timeout(unmutated)
    assert calc.read_bytes() == before


def test_the_timeout_scales_with_the_unmutated_tests():
    assert gate.mutant_timeout(1.0) == gate.MUTANT_TIMEOUT_SECONDS
    assert gate.mutant_timeout(300.0) == 1200.0


def test_a_mutant_whose_tests_outlast_the_rest_of_the_budget_is_not_run(
    repository, monkeypatch, tmp_path
):
    repository.change(
        CALC_HEAD,
        "import time\n\nfrom demo.calc import is_big\n\n\ndef test_slow():\n"
        "    time.sleep(2)\n    assert is_big(11)\n",
    )
    monkeypatch.setattr(gate, "ROOT", repository.repo.root)
    monkeypatch.setattr(gate, "BUDGET_SECONDS", 1)
    monkeypatch.chdir(repository.repo.root)

    run = gate.gate(gate.parse_args(["--base", "main~1"]), tmp_path)

    assert set(run.outcomes.values()) == {"not run"}


IMPORT_TIME_CALC = 'CHOICES = ["a", "b"]\nDEFAULT = CHOICES[1]\n'


def test_a_mutant_that_breaks_its_modules_import_is_killed_on_node_ids(repository):
    """Pytest exits 4 (no collectors) on node ids of a module that no longer
    imports."""
    repository.change(
        IMPORT_TIME_CALC + "\n\ndef default():\n    return DEFAULT\n",
        "from demo.calc import default\n\n\ndef test_default():\n"
        "    assert default() == 'b'\n",
    )

    result = repository.run("--base", "main~1")

    assert result.returncode == 0, result.output
    assert "killed: packages/demo/demo/calc.py:2: 1 -> 2" in result.stdout
    assert "0 error" in result.stdout


def test_a_mutant_that_breaks_its_modules_import_is_killed_on_the_package_suite(
    repository,
):
    """A module whose every line runs at import is tested by the package's
    whole suite, and pytest exits 2 (a collection error) when the mutant breaks
    it."""
    repository.change(
        IMPORT_TIME_CALC,
        "from demo.calc import DEFAULT\n\n\ndef test_default():\n"
        "    assert DEFAULT == 'b'\n",
    )

    result = repository.run("--base", "main~1")

    assert result.returncode == 0, result.output
    assert "killed: packages/demo/demo/calc.py:2: 1 -> 2" in result.stdout


def test_more_tests_than_the_limit_run_as_their_files(
    repository, monkeypatch, tmp_path
):
    repository.change(CALC_HEAD, CALC_TWO_TESTS)
    monkeypatch.setattr(gate, "ROOT", repository.repo.root)
    monkeypatch.setattr(gate, "MAX_NODE_IDS", 1)
    monkeypatch.chdir(repository.repo.root)
    data_file = tmp_path / "coverage"

    gate.coverage_run("packages/demo", data_file)
    tests = gate.Coverage().tests(data_file, "packages/demo/demo/calc.py", 6)

    assert tests == ["packages/demo/demo/tests/calc_test.py"]


def test_sigterm_restores_the_mutated_file(repository):
    repository.change(
        CALC_HEAD,
        "import time\n\nfrom demo.calc import is_big\n\n\ndef test_slow():\n"
        "    time.sleep(3)\n    assert is_big(11)\n",
    )
    calc = repository.repo.root / "packages/demo/demo/calc.py"
    original = calc.read_bytes()
    mtime = calc.stat().st_mtime_ns
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(repository.repo.home),
        "TMPDIR": str(repository.repo.tmp),
    }
    process = subprocess.Popen(
        [str(repository.repo.root / "run-gate.sh"), "--base", "main~1"],
        cwd=repository.repo.root,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 60
        while calc.read_bytes() == original and time.monotonic() < deadline:
            time.sleep(0.1)
        assert calc.read_bytes() != original, "no mutant was applied within 60 s"
        process.terminate()
        assert process.wait(timeout=30) == 128 + 15
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()

    assert calc.read_bytes() == original
    assert calc.stat().st_mtime_ns == mtime
