"""The sshd fixture skips a test where no sshd can run, and fails it instead
where TESTS_REQUIRE_SSHD=1 says one must."""

import os
import shutil
import stat

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("ssh-keygen") is None, reason="needs ssh-keygen"
)


@pytest.fixture
def no_sshd(monkeypatch):
    """No sshd on PATH nor at /usr/sbin/sshd."""
    which, exists = shutil.which, os.path.exists
    monkeypatch.setattr(
        shutil,
        "which",
        lambda name, *args, **kwargs: (
            None if name == "sshd" else which(name, *args, **kwargs)
        ),
    )
    monkeypatch.setattr(
        os.path, "exists", lambda path: path != "/usr/sbin/sshd" and exists(path)
    )


@pytest.fixture
def broken_sshd(monkeypatch, tmp_path):
    """An sshd on PATH that exits at once with an error."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    sshd = bin_dir / "sshd"
    sshd.write_text("#!/bin/sh\necho 'cannot bind' >&2\nexit 1\n")
    sshd.chmod(sshd.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")


def outcome(make_sshd) -> tuple[type, str]:
    """How ``make_sshd()`` ended the test: skipped or failed, and why."""
    try:
        make_sshd()
    except (pytest.skip.Exception, pytest.fail.Exception) as ending:
        return type(ending), str(ending)
    pytest.fail("make_sshd() started an sshd")


def test_no_sshd_skips(make_sshd, no_sshd, monkeypatch):
    monkeypatch.delenv("TESTS_REQUIRE_SSHD", raising=False)

    assert outcome(make_sshd) == (pytest.skip.Exception, "no sshd on this machine")


def test_no_sshd_fails_where_one_is_required(make_sshd, no_sshd, monkeypatch):
    monkeypatch.setenv("TESTS_REQUIRE_SSHD", "1")

    assert outcome(make_sshd) == (
        pytest.fail.Exception,
        "TESTS_REQUIRE_SSHD=1 and no sshd on this machine",
    )


def test_an_sshd_that_does_not_start_skips(make_sshd, broken_sshd, monkeypatch):
    monkeypatch.delenv("TESTS_REQUIRE_SSHD", raising=False)

    assert outcome(make_sshd) == (
        pytest.skip.Exception,
        "sshd did not start: cannot bind",
    )


def test_an_sshd_that_does_not_start_fails_where_one_is_required(
    make_sshd, broken_sshd, monkeypatch
):
    monkeypatch.setenv("TESTS_REQUIRE_SSHD", "1")

    assert outcome(make_sshd) == (
        pytest.fail.Exception,
        "TESTS_REQUIRE_SSHD=1 and sshd did not start: cannot bind",
    )


@pytest.mark.parametrize("value", ["", "0", "true"])
def test_only_1_requires_sshd(make_sshd, no_sshd, monkeypatch, value):
    monkeypatch.setenv("TESTS_REQUIRE_SSHD", value)

    assert outcome(make_sshd)[0] is pytest.skip.Exception
