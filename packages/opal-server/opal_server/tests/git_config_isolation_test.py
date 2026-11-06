"""The test session reads no git config of the machine running it (see the root
conftest.py): not through git, not through libgit2, and not through the gits
that serve the git_http and sshd fixtures' repositories."""

import os
import shutil
import subprocess
from pathlib import Path

import pygit2
import pytest

_LEVELS = (
    pygit2.enums.ConfigLevel.GLOBAL,
    pygit2.enums.ConfigLevel.XDG,
    pygit2.enums.ConfigLevel.SYSTEM,
)


def test_git_is_given_an_empty_global_config_and_no_system_one():
    """The guard itself, as its outcome below is the same without it on a
    machine that has no git config."""
    assert os.environ["GIT_CONFIG_NOSYSTEM"] == "1"
    assert "GIT_CONFIG_SYSTEM" not in os.environ
    global_config = Path(os.environ["GIT_CONFIG_GLOBAL"])
    assert global_config.is_file(), global_config
    assert global_config.stat().st_size == 0, global_config.read_text()


@pytest.mark.parametrize("level", _LEVELS, ids=lambda level: level.name)
def test_libgit2_searches_an_empty_directory_for_config(level):
    """libgit2 reads neither variable: each level's search path is an empty
    directory outside the user's home, instead of libgit2's own (the home,
    its ~/.config/git, /etc)."""
    path = Path(pygit2.settings.search_path[level])
    assert path.is_dir(), path
    assert list(path.iterdir()) == [], path
    assert not path.is_relative_to(Path.home()), path


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_git_reads_no_system_or_global_config(tmp_path):
    listed = subprocess.run(
        ["git", "config", "--list", "--show-origin"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert listed.stdout == "", listed.stdout


def test_libgit2_reads_no_global_xdg_or_system_config(tmp_path):
    repo = pygit2.init_repository(str(tmp_path / "repo"))
    try:
        # Only what init wrote into the repository's own config.
        assert {entry.level for entry in repo.config} == {
            pygit2.enums.ConfigLevel.LOCAL
        }
        assert repo.head_is_unborn
        assert repo.references["HEAD"].target == "refs/heads/master"
    finally:
        repo.free()


def _plant_configs(tmp_path: Path) -> dict:
    """A global and a system git config that each hide a branch from
    upload-pack: ``dev`` and ``feature/x``. Returns the env of a git that
    reads both, as git reads ``~/.gitconfig`` and ``/etc/gitconfig``."""
    home = tmp_path / "home"
    home.mkdir()
    (home / ".gitconfig").write_text("[uploadpack]\n\thideRefs = refs/heads/dev\n")
    system = tmp_path / "system.gitconfig"
    system.write_text("[uploadpack]\n\thideRefs = refs/heads/feature/x\n")
    return {
        "PATH": os.environ["PATH"],
        "HOME": str(home),
        "GIT_CONFIG_GLOBAL": str(home / ".gitconfig"),
        "GIT_CONFIG_SYSTEM": str(system),
    }


def _ls_remote(url: str, env: dict, cwd: Path) -> str:
    """The refs ``url`` lists, to a git run with ``env`` outside any repository
    (``cwd``)."""
    listed = subprocess.run(
        ["git", "ls-remote", url],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert listed.returncode == 0, listed.stderr
    return listed.stdout


def _hidden(listed: str) -> set:
    return {"refs/heads/dev", "refs/heads/feature/x"} - set(listed.split())


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_the_git_http_fixture_s_git_reads_no_config_of_the_machine(
    git_http, make_origin, tmp_path, monkeypatch
):
    """The fixture runs git http-backend with an env of its own, not the
    session's, so it reads the global config of the HOME it is given, and the
    system config, unless that env says not to."""
    origin = make_origin(git_http.root / "repo.git")
    planted = _plant_configs(tmp_path)
    assert _hidden(_ls_remote(origin.url, planted, tmp_path)) == {
        "refs/heads/dev",
        "refs/heads/feature/x",
    }
    monkeypatch.setenv("HOME", planted["HOME"])
    # The system config reaches http-backend the way /etc/gitconfig would:
    # through a git first on PATH, as http-backend's env has no other way in.
    shims = tmp_path / "bin"
    shims.mkdir()
    (shims / "git").write_text(
        "#!/bin/sh\n"
        f"GIT_CONFIG_SYSTEM='{planted['GIT_CONFIG_SYSTEM']}' "
        f"exec '{shutil.which('git')}' \"$@\"\n"
    )
    (shims / "git").chmod(0o755)
    monkeypatch.setenv("PATH", f"{shims}{os.pathsep}{os.environ['PATH']}")

    listed = _ls_remote(git_http.url("repo.git"), dict(os.environ), tmp_path)

    assert _hidden(listed) == set()


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_the_sshd_fixture_s_git_reads_no_config_of_the_machine(
    make_sshd, make_origin, tmp_path
):
    """The fixture's sshd gives git-shell an env of its own (from the user
    database, and from SetEnv here), so git-shell and upload-pack read the
    user's global config, and the system config, unless the ForceCommand script
    says not to."""
    origin = make_origin(tmp_path / "served" / "repo.git")
    planted = _plant_configs(tmp_path)
    server = make_sshd(
        config=f"SetEnv GIT_CONFIG_GLOBAL={planted['GIT_CONFIG_GLOBAL']} "
        f"GIT_CONFIG_SYSTEM={planted['GIT_CONFIG_SYSTEM']}\n"
    )
    ssh = (
        f"ssh -i '{server.base / 'client_key'}' -o IdentitiesOnly=yes "
        "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "
        "-o BatchMode=yes"
    )

    listed = _ls_remote(
        server.url(origin.path), {**os.environ, "GIT_SSH_COMMAND": ssh}, tmp_path
    )

    assert _hidden(listed) == set()
