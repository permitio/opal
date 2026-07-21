from opal_common.confi.confi import build_config

# Unique key that is not present in the real environment, so decouple resolves
# it from the .env file we write rather than from os.environ.
_TEST_KEY = "OPAL_TEST_CONFI_ENV_FOLDER_KEY"


def _write_env_file(directory, value):
    (directory / ".env").write_text(f"{_TEST_KEY}={value}\n")


def test_reads_env_file_from_confi_path(tmp_path, monkeypatch):
    _write_env_file(tmp_path, "from_confi_path")
    monkeypatch.setenv("CONFI_PATH", str(tmp_path))

    assert build_config()(_TEST_KEY) == "from_confi_path"


def test_falls_back_to_current_working_directory(tmp_path, monkeypatch):
    _write_env_file(tmp_path, "from_cwd")
    monkeypatch.delenv("CONFI_PATH", raising=False)
    monkeypatch.chdir(tmp_path)

    assert build_config()(_TEST_KEY) == "from_cwd"


def test_confi_path_takes_precedence_over_cwd(tmp_path, monkeypatch):
    confi_path_dir = tmp_path / "config_dir"
    confi_path_dir.mkdir()
    _write_env_file(confi_path_dir, "from_confi_path")

    cwd_dir = tmp_path / "cwd_dir"
    cwd_dir.mkdir()
    _write_env_file(cwd_dir, "from_cwd")

    monkeypatch.setenv("CONFI_PATH", str(confi_path_dir))
    monkeypatch.chdir(cwd_dir)

    assert build_config()(_TEST_KEY) == "from_confi_path"
