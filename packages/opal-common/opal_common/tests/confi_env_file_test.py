import pytest
from opal_common.confi import Confi, WorkingDirectoryAutoConfig, confi


@pytest.fixture
def isolated_auto_config(monkeypatch):
    monkeypatch.setattr("opal_common.confi.confi.config", WorkingDirectoryAutoConfig())


def test_env_file_is_loaded_from_working_directory(
    tmp_path, monkeypatch, isolated_auto_config
):
    (tmp_path / ".env").write_text("OPAL_TEST_CLIENT_TOKEN=token-from-env-file\n")
    monkeypatch.chdir(tmp_path)

    class ConfigWithEnvFile(Confi):
        TEST_CLIENT_TOKEN = confi.str("TEST_CLIENT_TOKEN", "default-token")

    assert ConfigWithEnvFile(prefix="OPAL_").TEST_CLIENT_TOKEN == "token-from-env-file"


def test_environment_variables_take_precedence_over_env_file(
    tmp_path, monkeypatch, isolated_auto_config
):
    (tmp_path / ".env").write_text("OPAL_TEST_CLIENT_TOKEN=token-from-env-file\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPAL_TEST_CLIENT_TOKEN", "token-from-environment")

    class ConfigWithEnvFile(Confi):
        TEST_CLIENT_TOKEN = confi.str("TEST_CLIENT_TOKEN", "default-token")

    assert (
        ConfigWithEnvFile(prefix="OPAL_").TEST_CLIENT_TOKEN == "token-from-environment"
    )
