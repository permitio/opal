#!/usr/bin/env python3
"""Mutation testing of the Python code under packages/: on a pull request, the
lines it changes; weekly, every line.

``mutation_gate.py --base <rev> [--summary FILE]`` takes the lines that the diff from the merge
base of <rev> and HEAD adds or changes in the packages' source (files under packages/<package>/,
not their tests, conftest.py or setup.py), makes the mutants of those lines, runs the tests that
cover each mutant's line, and fails when too few mutants are killed. ``--full`` does the same
for every source line, with a larger budget, and reports only.

A mutant changes one token of one line: a comparison (== and !=, < and <=, > and >=, is to is
not), a boolean operator (and and or), a boolean constant, a binary + or -, an integer (n to
n + 1), or drops a ``not`` (so ``is not`` becomes ``is`` and ``not in`` becomes ``in``). A
mutant that does not compile is dropped.

The tests that cover a line come from one run of each changed package's suite under pytest-cov
with per-test contexts, which must pass first. That run uses coverage's C tracer
(COVERAGE_CORE=ctrace): the sys.monitoring core, the default on Python 3.14, records each line
only for the first test that runs it. A line that runs only at import (a module constant, a
default argument, a decorator) has no test of its own; it is covered by the tests that run any
of its module's code, or, when none does, by the package's whole suite. Each mutant then runs
only its tests (pytest -x, in a process group of its own), and ends as one of:

    killed       a test failed (pytest exit 1); a test module no longer imports (pytest exit
                 2 or 4 with a collection error, on tests that collected and passed in the
                 coverage run); or the tests timed out: the timeout is
                 MUTANT_TIMEOUT_SECONDS, or TIMEOUT_MARGIN times what the same tests took in
                 the coverage run when that is longer, so a timeout means the mutant made
                 them at least that much slower
    survived     every covering test passed
    not covered  no test runs the line (code that runs only in a child process counts here too)
    not run      the budget ran out first, or what is left of it is shorter than the tests
                 took unmutated
    error        pytest ended otherwise (exit 2 to 5 without a collection error): the gate
                 did not run

At most MAX_MUTANTS mutants run per change: a sample seeded by HEAD, so a rerun picks the same
ones, run in an order that takes the packages in turn, so that a budget cut is spread across
them. The budget is BUDGET_SECONDS after the coverage runs. The verdict is on the mutants that
ran: the gate passes when the mutation score, killed / (killed + survived), is at least
MIN_SCORE; the report says how many were not run when the budget was reached. A run with
mutants of which none ran against a covering test did not run. Every mutated file is restored,
byte for byte and with its mtime, after its mutant and when the run is stopped (SIGTERM).

Exit codes: 0 when the gate passes (for --full, whenever it ran); 1 when the score is below
MIN_SCORE; 2 when it did not run: wrong arguments, git or a coverage run failed, a suite failed
before any mutant, a mutant ended in an error, or no mutant ran against a covering test.
"""

import argparse
import dataclasses
import io
import keyword
import os
import random
import re
import signal
import subprocess
import sys
import tempfile
import time
import tokenize
import traceback
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAX_MUTANTS = 300
BUDGET_SECONDS = 45 * 60
FULL_BUDGET_SECONDS = 5 * 60 * 60
MIN_SCORE = 0.8
MUTANT_TIMEOUT_SECONDS = 180
# A mutant's timeout is at least this many times what its tests took unmutated.
TIMEOUT_MARGIN = 4
SUITE_TIMEOUT_SECONDS = 40 * 60
MAX_LISTED = 50
# Above this many covering tests, a mutant runs their files instead of their node ids.
MAX_NODE_IDS = 500

SWAPS = {
    "==": "!=",
    "!=": "==",
    "<": "<=",
    "<=": "<",
    ">": ">=",
    ">=": ">",
    "and": "or",
    "or": "and",
    "True": "False",
    "False": "True",
}
# A token after which a + or - is binary: the end of an operand.
_OPERAND_ENDS = {")", "]", "}"}
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
# What pytest prints for a test module that fails to import.
COLLECTION_ERROR = "ERROR collecting "
_DURATION = re.compile(r"^\s*([\d.]+)s (?:setup|call|teardown)\s+(\S.*)$")


class NotRun(Exception):
    """The gate did not run, for the reason in the message."""


@dataclasses.dataclass(frozen=True, order=True)
class Mutant:
    """One token of one line, replaced.

    Attributes:
        path: The source file, relative to the repository root.
        line: The 1-based line.
        col: The token's 0-based column.
        old: The token.
        new: What replaces it ("" drops it).
    """

    path: str
    line: int
    col: int
    old: str
    new: str

    def label(self) -> str:
        new = self.new or "(dropped)"
        return f"{self.path}:{self.line}: {self.old} -> {new}"


def is_source(path: str) -> bool:
    """Whether a path is package source that the gate mutates: a file under
    packages/<package>/, not a test."""
    parts = path.split("/")
    name = parts[-1]
    return (
        len(parts) >= 3
        and parts[0] == "packages"
        and name.endswith(".py")
        and "tests" not in parts
        and not name.startswith("test_")
        and not name.endswith("_test.py")
        and name not in ("conftest.py", "setup.py")
    )


def git(*args: str) -> str:
    """A git command's output in the repository root.

    Raises:
        NotRun: git fails.
    """
    done = subprocess.run(
        ["git", "-c", "core.quotePath=false", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        raise NotRun(f"git {' '.join(args)} failed: {done.stderr.strip()[:300]}")
    return done.stdout


def parse_diff(diff: str) -> dict[str, set[int]]:
    """The lines a unified diff with no context adds or changes, per new
    path."""
    lines: dict[str, set[int]] = {}
    path = None
    for text in diff.splitlines():
        if text.startswith("+++ "):
            # git ends the name with a tab when it holds a space.
            name = text[4:].split("\t", 1)[0]
            path = name[2:] if name.startswith("b/") else None
        elif path and (hunk := _HUNK.match(text)):
            start, count = int(hunk[1]), int(hunk[2] or 1)
            lines.setdefault(path, set()).update(range(start, start + count))
    return {path: found for path, found in lines.items() if found and is_source(path)}


def changed_lines(base: str) -> dict[str, set[int]]:
    """The source lines the change from the merge base of base and HEAD
    adds."""
    merge_base = git("merge-base", base, "HEAD").strip()
    diff = git(
        "diff",
        "--unified=0",
        "--no-color",
        "--no-ext-diff",
        "--src-prefix=a/",
        "--dst-prefix=b/",
        merge_base,
        "HEAD",
        "--",
        "packages",
    )
    return parse_diff(diff)


def read_source(path: str) -> str:
    """A source file as text, its line endings as they are."""
    return (ROOT / path).read_bytes().decode("utf-8")


def source_lines(source: str) -> list[str]:
    """The lines of a source as tokenize counts them: split after each \\n
    only."""
    return io.StringIO(source, newline="").readlines()


def every_line() -> dict[str, set[int]]:
    """Every line of every source file under packages/<package>/."""
    found = {}
    for path in git("ls-files", "--", "packages").splitlines():
        if is_source(path):
            count = len(source_lines(read_source(path)))
            found[path] = set(range(1, count + 1))
    return found


def is_binary_operator(previous: tokenize.TokenInfo | None) -> bool:
    """Whether a + or - after this token is binary: it ends an operand."""
    if previous is None:
        return False
    if previous.type == tokenize.NAME:
        return not keyword.iskeyword(previous.string) or previous.string in (
            "True",
            "False",
            "None",
        )
    if previous.type in (tokenize.NUMBER, tokenize.STRING):
        return True
    if previous.type == getattr(tokenize, "FSTRING_END", None):
        return True
    return previous.type == tokenize.OP and previous.string in _OPERAND_ENDS


def mutants_of(path: str, source: str, lines: set[int]) -> list[Mutant]:
    """The mutants of the given lines of one file that still compile."""
    try:
        tokens = list(
            tokenize.generate_tokens(io.StringIO(source, newline="").readline)
        )
    except (tokenize.TokenError, SyntaxError):
        return []
    found = []
    previous = None
    for index, token in enumerate(tokens):
        line, col = token.start
        following = tokens[index + 1].string if index + 1 < len(tokens) else ""
        if line in lines and token.type in (
            tokenize.OP,
            tokenize.NAME,
            tokenize.NUMBER,
        ):
            new = None
            if token.string in SWAPS:
                new = SWAPS[token.string]
            elif token.string == "is":
                new = "is" if following == "not" else "is not"
            elif token.string == "not":
                new = ""
            elif token.string in ("+", "-") and is_binary_operator(previous):
                new = "-" if token.string == "+" else "+"
            elif token.type == tokenize.NUMBER and token.string.isdigit():
                new = str(int(token.string) + 1)
            if new is not None and new != token.string:
                found.append(Mutant(path, line, col, token.string, new))
        if token.type == tokenize.NEWLINE:
            previous = None
        elif token.type not in (
            tokenize.NL,
            tokenize.COMMENT,
            tokenize.INDENT,
            tokenize.DEDENT,
        ):
            previous = token
    return [mutant for mutant in found if compiles(apply(source, mutant))]


def apply(source: str, mutant: Mutant) -> str:
    """The source with the mutant's token replaced.

    Raises:
        NotRun: The mutant's token is not where it says.
    """
    lines = source_lines(source)
    text = lines[mutant.line - 1] if mutant.line <= len(lines) else ""
    if text[mutant.col : mutant.col + len(mutant.old)] != mutant.old:
        raise NotRun(f"{mutant.label()} does not match the source")
    lines[mutant.line - 1] = (
        text[: mutant.col] + mutant.new + text[mutant.col + len(mutant.old) :]
    )
    return "".join(lines)


def compiles(source: str) -> bool:
    with warnings.catch_warnings():
        # A mutant such as `x is not 1` compiles with a SyntaxWarning; it is still a mutant.
        warnings.simplefilter("ignore", SyntaxWarning)
        try:
            compile(source, "<mutant>", "exec")
        except (SyntaxError, ValueError):
            return False
    return True


def sample(mutants: list[Mutant], cap: int | None, seed: str) -> list[Mutant]:
    """At most cap mutants, the same ones for the same seed, in file order."""
    if cap is None or len(mutants) <= cap:
        return sorted(mutants)
    return sorted(random.Random(seed).sample(sorted(mutants), cap))


def package_of(path: str) -> str:
    """The package directory of a source path, such as packages/opal-server."""
    return "/".join(path.split("/")[:2])


def run_order(mutants: list[Mutant], seed: str) -> list[Mutant]:
    """The order to run the mutants in: each package's mutants shuffled with
    the seed, and the packages taken in turn, so a budget cut leaves some of
    every package unrun rather than all of the last one."""
    rng = random.Random(seed)
    queues = []
    for package in sorted({package_of(mutant.path) for mutant in mutants}):
        queue = sorted(
            mutant for mutant in mutants if package_of(mutant.path) == package
        )
        rng.shuffle(queue)
        queues.append(queue)
    order = []
    while any(queues):
        for queue in queues:
            if queue:
                order.append(queue.pop(0))
    return order


def coverage_run(package: str, data_file: Path) -> dict[str, float]:
    """Run a package's suite once with per-test coverage contexts.

    Returns:
        How long each test took, by node id (setup, call and teardown together).

    Raises:
        NotRun: The suite fails or does not finish.
    """
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        f"--cov={package}",
        "--cov-context=test",
        "--cov-report=",
        "--durations=0",
        "--durations-min=0",
        package,
    ]
    # The C tracer: the sys.monitoring core (3.14's default) records each line under the first
    # test only, and pytest-cov's per-test contexts do not make it record the line again.
    env = {**os.environ, "COVERAGE_FILE": str(data_file), "COVERAGE_CORE": "ctrace"}
    try:
        done = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=SUITE_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise NotRun(f"the suite of {package} did not finish under coverage") from e
    if done.returncode != 0:
        tail = "\n".join(done.stdout.splitlines()[-5:])
        raise NotRun(f"the suite of {package} fails before any mutant:\n{tail}")
    durations: dict[str, float] = {}
    for line in done.stdout.splitlines():
        if found := _DURATION.match(line):
            node_id = found[2].strip()
            durations[node_id] = durations.get(node_id, 0.0) + float(found[1])
    return durations


def node_id_of(context: str) -> str:
    """The pytest node id of a pytest-cov context, "<node id>|<when>"."""
    return context.rsplit("|", 1)[0]


class Coverage:
    """The per-test contexts of the coverage runs, read once per file."""

    def __init__(self) -> None:
        self._lines: dict[str, dict[int, list[str]]] = {}

    def tests(self, data_file: Path, path: str, line: int) -> list[str]:
        """The pytest node ids or test paths that cover the line; empty when
        none does.

        A line that ran only at import (under the empty context) is
        covered by the tests that run any line of its module, or by the
        package's whole suite when none does. More than MAX_NODE_IDS
        node ids become their test files.
        """
        from coverage import CoverageData  # pytest-cov's dependency

        if path not in self._lines:
            data = CoverageData(basename=str(data_file))
            data.read()
            self._lines[path] = data.contexts_by_lineno(str(ROOT / path)) or {}
        by_line = self._lines[path]
        if line not in by_line:
            return []
        node_ids = {node_id_of(context) for context in by_line[line] if context}
        if not node_ids:
            node_ids = {
                node_id_of(context)
                for contexts in by_line.values()
                for context in contexts
                if context
            }
            if not node_ids:
                return [package_of(path)]
        if len(node_ids) > MAX_NODE_IDS:
            return sorted({node_id.split("::", 1)[0] for node_id in node_ids})
        return sorted(node_ids)


def unmutated_seconds(tests: list[str], durations: dict[str, float]) -> float:
    """How long the tests took in the coverage run: a node id's own time, or
    the time of every test under a path."""
    total = 0.0
    for test in tests:
        if "::" in test:
            total += durations.get(test, 0.0)
            continue
        prefixes = (test + "::", test.rstrip("/") + "/")
        for node_id, seconds in durations.items():
            if node_id.startswith(prefixes):
                total += seconds
    return total


def mutant_timeout(unmutated: float) -> float:
    """The timeout of a mutant whose tests took this long unmutated."""
    return max(MUTANT_TIMEOUT_SECONDS, TIMEOUT_MARGIN * unmutated)


def run_mutant(mutant: Mutant, tests: list[str], unmutated: float) -> tuple[str, str]:
    """Apply the mutant, run its tests, restore the file. A timeout is a
    kill: it is at least TIMEOUT_MARGIN times what the tests took unmutated.

    Python reuses a cached .pyc when the source's mtime (in seconds) and
    size match it, and a mutant often keeps the size. So the mutated
    file gets an mtime no .pyc was made for, the tests write no .pyc,
    and the restored file gets its bytes and its mtime back, so no run
    can load another mutant's bytecode, nor the original's for a mutant.

    Returns:
        The outcome, and for an error its reason.
    """
    target = ROOT / mutant.path
    original = target.read_bytes()
    times = target.stat()
    process = None
    try:
        target.write_bytes(apply(original.decode("utf-8"), mutant).encode("utf-8"))
        os.utime(target, ns=(times.st_atime_ns, times.st_mtime_ns + 2_000_000_000))
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "pytest",
                "-x",
                "-q",
                "-p",
                "no:cacheprovider",
                "--no-cov",
                *tests,
            ],
            cwd=ROOT,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        try:
            output, _ = process.communicate(timeout=mutant_timeout(unmutated))
        except subprocess.TimeoutExpired:
            # The tests' whole process group: servers they forked must not outlive them.
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            return "killed", ""
    finally:
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
        target.write_bytes(original)
        os.utime(target, ns=(times.st_atime_ns, times.st_mtime_ns))
    if process.returncode == 0:
        return "survived", ""
    if process.returncode == 1:
        return "killed", ""
    # A test module that no longer imports: pytest exits 2 (a collection error) on paths and 4
    # (no collectors) on node ids. The coverage run collected and passed the same tests on the
    # unmutated source, so the mutant broke the import.
    if process.returncode in (2, 4) and COLLECTION_ERROR in output:
        return "killed", ""
    last = (output.strip().splitlines() or ["no output"])[-1]
    return "error", f"pytest exited {process.returncode}: {last[:200]}"


OUTCOMES = ("killed", "survived", "not covered", "not run", "error")


def render(outcomes: dict[Mutant, str], score: float | None, mode: str) -> str:
    """The Markdown report."""
    counts = {
        name: sum(1 for outcome in outcomes.values() if outcome == name)
        for name in OUTCOMES
    }
    shown = "n/a" if score is None else f"{score:.0%}"
    lines = [
        f"## Mutation testing ({mode})",
        "",
        f"Score {shown} (gate {MIN_SCORE:.0%}): "
        + ", ".join(f"{count} {name}" for name, count in counts.items()),
        "",
    ]
    if counts["not run"]:
        lines += [
            f"Budget reached: {counts['not run']} of {len(outcomes)} mutants were not run; "
            "the score is on the ones that ran.",
            "",
        ]
    survivors = sorted(
        mutant for mutant, outcome in outcomes.items() if outcome == "survived"
    )
    if survivors:
        lines += ["Survived (no test failed with this change):", ""]
        lines += [f"- `{mutant.label()}`" for mutant in survivors[:MAX_LISTED]]
        if len(survivors) > MAX_LISTED:
            lines.append(f"- and {len(survivors) - MAX_LISTED} more")
        lines.append("")
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mutation testing of the package source."
    )
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--base", help="mutate the lines changed since this revision")
    which.add_argument(
        "--full", action="store_true", help="mutate every line, report only"
    )
    parser.add_argument("--summary", type=Path, help="a file to append the report to")
    return parser.parse_args(argv)


@dataclasses.dataclass
class Run:
    """What a run did: each chosen mutant's outcome, the errors, and the score."""

    outcomes: dict[Mutant, str]
    errors: list[str]
    score: float | None


def gate(args: argparse.Namespace, work: Path) -> Run:
    """Make, sample and run the mutants."""
    lines = every_line() if args.full else changed_lines(args.base)
    mutants = []
    for path, found in sorted(lines.items()):
        mutants += mutants_of(path, read_source(path), found)
    seed = git("rev-parse", "HEAD").strip()
    chosen = sample(mutants, None if args.full else MAX_MUTANTS, seed)
    print(
        f"mutation: {len(mutants)} mutants in {len(lines)} files; running {len(chosen)}"
    )
    data_files = {}
    durations: dict[str, dict[str, float]] = {}
    for package in sorted({package_of(mutant.path) for mutant in chosen}):
        data_files[package] = work / f"coverage-{package.split('/')[-1]}"
        print(f"mutation: the suite of {package} under coverage")
        durations[package] = coverage_run(package, data_files[package])
    budget = FULL_BUDGET_SECONDS if args.full else BUDGET_SECONDS
    deadline = time.monotonic() + budget
    coverage = Coverage()
    outcomes: dict[Mutant, str] = {}
    errors = []
    for mutant in run_order(chosen, seed):
        if time.monotonic() >= deadline:
            outcomes[mutant] = "not run"
            continue
        package = package_of(mutant.path)
        tests = coverage.tests(data_files[package], mutant.path, mutant.line)
        if not tests:
            outcomes[mutant] = "not covered"
        elif (unmutated := unmutated_seconds(tests, durations[package])) > (
            deadline - time.monotonic()
        ):
            outcomes[mutant] = "not run"
        else:
            outcomes[mutant], reason = run_mutant(mutant, tests, unmutated)
            if reason:
                errors.append(f"{mutant.label()}: {reason}")
        print(f"mutation: {outcomes[mutant]}: {mutant.label()}")
    killed = sum(1 for outcome in outcomes.values() if outcome == "killed")
    survived = sum(1 for outcome in outcomes.values() if outcome == "survived")
    score = killed / (killed + survived) if killed + survived else None
    return Run(outcomes, errors, score)


def verdict(run: Run, full: bool) -> tuple[int, str]:
    """The exit code and the line that says it."""
    if run.errors:
        return 2, (
            f"mutation: DID NOT RUN: {len(run.errors)} mutants ended in an error: "
            + "; ".join(run.errors[:5])
        )
    if run.outcomes and run.score is None:
        return 2, (
            f"mutation: DID NOT RUN: none of the {len(run.outcomes)} mutants ran against a "
            "covering test"
        )
    if full or run.score is None or run.score >= MIN_SCORE:
        not_run = sum(1 for outcome in run.outcomes.values() if outcome == "not run")
        partial = f" (budget reached: {not_run} not run)" if not_run else ""
        return 0, f"mutation: PASS{partial}"
    return 1, f"mutation: FAIL: the score {run.score:.0%} is below {MIN_SCORE:.0%}"


def _stop(signum: int, frame: object) -> None:
    """On SIGTERM, unwind, so that the mutated file is restored."""
    raise SystemExit(128 + signum)


def main(argv: list[str] | None = None) -> int:
    # One line per mutant as it finishes, also when the log is a pipe, as in CI.
    sys.stdout.reconfigure(line_buffering=True)
    signal.signal(signal.SIGTERM, _stop)
    try:
        args = parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    mode = "every line" if args.full else f"lines changed since {args.base}"
    with tempfile.TemporaryDirectory(prefix="mutation.") as work:
        try:
            run = gate(args, Path(work))
        except NotRun as e:
            code, line = 2, f"mutation: DID NOT RUN: {e}"
            report = f"## Mutation testing ({mode})\n\n"
        except (OSError, UnicodeDecodeError, ValueError) as e:
            traceback.print_exc()
            code, line = 2, f"mutation: DID NOT RUN: {type(e).__name__}: {e}"
            report = f"## Mutation testing ({mode})\n\n"
        else:
            code, line = verdict(run, args.full)
            report = render(run.outcomes, run.score, mode)
    print(report, end="")
    print(line)
    if args.summary is not None:
        with args.summary.open("a") as handle:
            handle.write(report + line.removeprefix("mutation: ") + "\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
