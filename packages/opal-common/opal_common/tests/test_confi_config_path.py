"""Confi reads a .env or settings.ini file from the folder OPAL_CONFIG_FILE_DIR
names, or else from the working directory, and never from a folder above it."""

import os
import re
import subprocess
import sys
import textwrap

import pytest
from opal_common.confi.confi import build_config

# Unique key that is not present in the real environment, so decouple resolves
# it from the .env file we write rather than from os.environ.
_TEST_KEY = "OPAL_TEST_CONFI_ENV_FOLDER_KEY"
_FOLDER_SETTING = "OPAL_CONFIG_FILE_DIR"
_UNSET = "<not in any file>"


def _write_env_file(directory, value):
    (directory / ".env").write_text(f"{_TEST_KEY}={value}\n")


def _write_ini_file(directory, value):
    (directory / "settings.ini").write_text(f"[settings]\n{_TEST_KEY}={value}\n")


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch):
    monkeypatch.delenv(_FOLDER_SETTING, raising=False)
    monkeypatch.delenv(_TEST_KEY, raising=False)


def test_reads_env_file_from_the_named_folder(tmp_path, monkeypatch):
    _write_env_file(tmp_path, "from_named_folder")
    monkeypatch.setenv(_FOLDER_SETTING, str(tmp_path))

    assert build_config()(_TEST_KEY) == "from_named_folder"


def test_falls_back_to_current_working_directory(tmp_path, monkeypatch):
    _write_env_file(tmp_path, "from_cwd")
    monkeypatch.chdir(tmp_path)

    assert build_config()(_TEST_KEY) == "from_cwd"


def test_an_empty_setting_reads_the_working_directory(tmp_path, monkeypatch):
    _write_env_file(tmp_path, "from_cwd")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(_FOLDER_SETTING, "")

    assert build_config()(_TEST_KEY) == "from_cwd"


def test_the_named_folder_wins_over_the_working_directory(tmp_path, monkeypatch):
    named_dir = tmp_path / "config_dir"
    named_dir.mkdir()
    _write_env_file(named_dir, "from_named_folder")

    cwd_dir = tmp_path / "cwd_dir"
    cwd_dir.mkdir()
    _write_env_file(cwd_dir, "from_cwd")

    monkeypatch.setenv(_FOLDER_SETTING, str(named_dir))
    monkeypatch.chdir(cwd_dir)

    assert build_config()(_TEST_KEY) == "from_named_folder"


def test_a_relative_folder_is_read_from_the_working_directory(tmp_path, monkeypatch):
    (tmp_path / "conf").mkdir()
    _write_env_file(tmp_path / "conf", "from_relative")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(_FOLDER_SETTING, "conf")
    config = build_config()
    monkeypatch.chdir(tmp_path / "conf")

    assert config(_TEST_KEY) == "from_relative"


def test_a_file_above_the_working_directory_is_not_read(tmp_path, monkeypatch):
    _write_env_file(tmp_path, "from_parent")
    (tmp_path / "app").mkdir()
    monkeypatch.chdir(tmp_path / "app")

    assert build_config()(_TEST_KEY, default=_UNSET) == _UNSET


def test_a_file_above_the_named_folder_is_not_read(tmp_path, monkeypatch):
    _write_env_file(tmp_path, "from_parent")
    named = tmp_path / "conf"
    named.mkdir()
    (named / ".env").write_text("OPAL_SOME_OTHER_KEY=1\n")
    monkeypatch.setenv(_FOLDER_SETTING, str(named))

    assert build_config()(_TEST_KEY, default=_UNSET) == _UNSET


def test_settings_ini_is_read_instead_of_env_in_the_same_folder(tmp_path, monkeypatch):
    _write_env_file(tmp_path, "from_env")
    _write_ini_file(tmp_path, "from_ini")
    monkeypatch.setenv(_FOLDER_SETTING, str(tmp_path))

    assert build_config()(_TEST_KEY) == "from_ini"


def test_the_environment_wins_over_the_file(tmp_path, monkeypatch):
    _write_env_file(tmp_path, "from_file")
    monkeypatch.setenv(_FOLDER_SETTING, str(tmp_path))
    monkeypatch.setenv(_TEST_KEY, "from_environment")

    assert build_config()(_TEST_KEY) == "from_environment"


def test_a_named_folder_that_does_not_exist_fails(tmp_path, monkeypatch):
    missing = tmp_path / "missing"
    monkeypatch.setenv(_FOLDER_SETTING, str(missing))

    with pytest.raises(
        ValueError, match=f"{_FOLDER_SETTING}.*{re.escape(str(missing))}.*not a folder"
    ):
        build_config()


def test_a_named_file_instead_of_a_folder_fails(tmp_path, monkeypatch):
    _write_env_file(tmp_path, "from_file")
    monkeypatch.setenv(_FOLDER_SETTING, str(tmp_path / ".env"))

    with pytest.raises(ValueError, match=f"{_FOLDER_SETTING}.*not a folder"):
        build_config()


def test_a_named_folder_without_a_settings_file_fails(tmp_path, monkeypatch):
    monkeypatch.setenv(_FOLDER_SETTING, str(tmp_path))

    with pytest.raises(
        ValueError,
        match=f"{_FOLDER_SETTING}.*{re.escape(str(tmp_path))}.*no .env or settings.ini",
    ):
        build_config()


def test_the_description_names_the_file_read(tmp_path, monkeypatch):
    _write_env_file(tmp_path, "from_file")
    monkeypatch.setenv(_FOLDER_SETTING, str(tmp_path))

    assert build_config().describe() == (
        f"Read settings from {tmp_path / '.env'}; the environment overrides it"
    )


def test_the_description_names_settings_ini_when_both_files_are_there(
    tmp_path, monkeypatch
):
    _write_env_file(tmp_path, "from_env")
    _write_ini_file(tmp_path, "from_ini")
    monkeypatch.chdir(tmp_path)

    assert str(tmp_path / "settings.ini") in build_config().describe()


def test_the_description_says_when_no_file_is_read(tmp_path, monkeypatch):
    _write_env_file(tmp_path, "from_parent")
    (tmp_path / "app").mkdir()
    monkeypatch.chdir(tmp_path / "app")

    assert build_config().describe() == (
        f"No .env or settings.ini in {tmp_path / 'app'}: settings come from the "
        "environment and the defaults"
    )


def _run_python(script: str, cwd, folder_setting=None) -> subprocess.CompletedProcess:
    """Runs script in a new interpreter, as OPAL starts: the settings file is
    looked up when opal_common.confi is first imported."""
    env = {
        name: value
        for name, value in os.environ.items()
        if name not in (_FOLDER_SETTING, _TEST_KEY) and not name.startswith("OPAL_")
    }
    if folder_setting is not None:
        env[_FOLDER_SETTING] = str(folder_setting)
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


@pytest.mark.parametrize("where", ["named folder", "working directory"])
def test_a_confi_entry_reads_the_settings_file(tmp_path, where):
    """Every Confi entry is read through build_config's config, not through
    decouple's own, which looks next to the installed package and above."""
    folder = tmp_path / "conf"
    folder.mkdir()
    _write_env_file(folder, "from_file")
    script = """
        from opal_common.confi import Confi, confi

        class Settings(Confi):
            TEST_CONFI_ENV_FOLDER_KEY = confi.str(
                "TEST_CONFI_ENV_FOLDER_KEY", None, description="test"
            )

        print(Settings(prefix="OPAL_").TEST_CONFI_ENV_FOLDER_KEY)
    """
    if where == "named folder":
        result = _run_python(script, cwd=tmp_path, folder_setting=folder)
    else:
        result = _run_python(script, cwd=folder)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "from_file"


@pytest.mark.parametrize("with_file", [True, False], ids=["file", "no-file"])
def test_the_startup_log_says_which_settings_file_was_read(tmp_path, with_file):
    if with_file:
        (tmp_path / ".env").write_text("OPAL_LOG_COLORIZE=false\n")
        expected = f"Read settings from {tmp_path / '.env'}"
    else:
        expected = f"No .env or settings.ini in {tmp_path}"
    script = """
        from opal_common.logger import configure_logs

        configure_logs()
        configure_logs()
    """

    result = _run_python(script, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert result.stderr.count(expected) == 1, result.stderr
