"""Fixtures shared by the tests of the scripts in .github/scripts.

A test copies the script it runs, and whatever else the script reads, into a throwaway copy of the
repository (``throwaway_repo``). The scripts find the repository root from their own path, so the
copy is all they see. Commands that reach the network or the GitHub API are replaced by fake
commands (``ThrowawayRepo.stub``) that come first on PATH, and each script runs with only PATH,
HOME, TMPDIR and the variables the test sets, so nothing from the CI runner's environment (such as
GITHUB_STEP_SUMMARY or a token) leaks into a test.
"""

import dataclasses
import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_TIMEOUT_SECONDS = 60


@dataclasses.dataclass(frozen=True)
class ScriptRun:
    """The result of one script run.

    Attributes:
        returncode: The script's exit code.
        stdout: What it printed on stdout.
        stderr: What it printed on stderr.
    """

    returncode: int
    stdout: str
    stderr: str

    @property
    def output(self) -> str:
        """Stdout followed by stderr, for checks of either."""
        return self.stdout + self.stderr


class ThrowawayRepo:
    """A temporary directory laid out like the repository, for one test.

    Attributes:
        root: The copy's root. A script copied to .github/scripts/ takes it as the repository root.
        stubs: A directory that ``run`` puts first on PATH; ``stub`` writes fake commands there.
        home: HOME for the scripts.
        tmp: TMPDIR for the scripts, so their temporary files stay in the test's directory.
    """

    def __init__(self, base: Path) -> None:
        self.root = base / "repo"
        self.stubs = base / "stubs"
        self.home = base / "home"
        self.tmp = base / "tmp"
        self._base = base
        for directory in (self.root, self.stubs, self.home, self.tmp):
            directory.mkdir()

    def copy(self, *paths: str) -> None:
        """Copy files from the real repository into the copy, at the same
        relative paths.

        Args:
            *paths: Paths relative to the repository root, such as ".github/scripts/trivy.sh".
                The file mode is copied too, so a script stays executable.
        """
        for relative in paths:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(REPO_ROOT / relative, target)

    def write(self, relative: str, text: str, executable: bool = False) -> Path:
        """Write a file into the copy.

        Args:
            relative: The path relative to the copy's root.
            text: The file's content.
            executable: Whether to make the file executable.

        Returns:
            The file's absolute path.
        """
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        if executable:
            path.chmod(0o755)
        return path

    def stub(self, name: str, body: str) -> Path:
        """Write a fake command, a bash script, that ``run`` finds first on
        PATH.

        Args:
            name: The command's name, such as "curl" or "gh".
            body: The script after its shebang line.

        Returns:
            The fake command's path.
        """
        path = self.stubs / name
        path.write_text("#!/usr/bin/env bash\n" + body)
        path.chmod(0o755)
        return path

    def path_with_only(self, *tools: str) -> str:
        """Build a PATH that holds the fake commands and only the named real
        commands.

        It is for checking what a script does when a command it needs is missing: the named
        commands are linked from the real PATH into a directory of their own.

        Args:
            *tools: The real commands to keep, such as "bash" and "jq".

        Returns:
            The PATH value, the fake commands' directory first.

        Raises:
            FileNotFoundError: When a named command is not on the real PATH.
        """
        key = hashlib.sha256(" ".join(sorted(tools)).encode()).hexdigest()[:12]
        directory = self._base / f"path-{key}"
        if not directory.exists():
            directory.mkdir()
            for tool in tools:
                found = shutil.which(tool)
                if found is None:
                    raise FileNotFoundError(f"{tool} is not on PATH; the tests need it")
                (directory / tool).symlink_to(found)
        return f"{self.stubs}{os.pathsep}{directory}"

    def run(
        self,
        script: str,
        *args: str,
        env: dict[str, str] | None = None,
        path: str | None = None,
    ) -> ScriptRun:
        """Run a script of the copy with a clean environment.

        Args:
            script: The script's path relative to the copy's root.
            *args: The script's arguments.
            env: Variables to set besides PATH, HOME and TMPDIR.
            path: PATH to use instead of the fake commands' directory followed by the real PATH.

        Returns:
            The exit code and the output.
        """
        full_env = {
            "PATH": path or f"{self.stubs}{os.pathsep}{os.environ['PATH']}",
            "HOME": str(self.home),
            "TMPDIR": str(self.tmp),
        }
        full_env.update(env or {})
        completed = subprocess.run(
            [str(self.root / script), *args],
            cwd=self.root,
            env=full_env,
            capture_output=True,
            text=True,
            timeout=SCRIPT_TIMEOUT_SECONDS,
            check=False,
        )
        return ScriptRun(completed.returncode, completed.stdout, completed.stderr)


@pytest.fixture
def throwaway_repo(tmp_path: Path) -> ThrowawayRepo:
    """An empty throwaway repository; the test copies files in."""
    return ThrowawayRepo(tmp_path)
