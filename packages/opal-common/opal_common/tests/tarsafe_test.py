"""TarSafe extracts with tarfile's ``data`` filter, which it passes itself
rather than leaving to the Python's default: a member's setuid bit and its
group and other write bits do not survive extraction."""

import io
import stat
import tarfile

from opal_common.security.tarsafe import TarSafe

POLICY = b"package policy\n"


def _archive(tmp_path):
    path = tmp_path / "bundle.tar.gz"
    with tarfile.open(path, "w:gz") as tar:
        info = tarfile.TarInfo("policy.rego")
        info.size = len(POLICY)
        info.mode = 0o4777
        tar.addfile(info, io.BytesIO(POLICY))
    return path


def _mode(path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_extractall_applies_the_data_filter(tmp_path):
    with TarSafe.open(_archive(tmp_path), mode="r:gz") as tar:
        tar.extractall(path=tmp_path / "out")

    assert (tmp_path / "out" / "policy.rego").read_bytes() == POLICY
    assert _mode(tmp_path / "out" / "policy.rego") == 0o755


def test_extract_applies_the_data_filter(tmp_path):
    with TarSafe.open(_archive(tmp_path), mode="r:gz") as tar:
        tar.extract("policy.rego", path=tmp_path / "out")

    assert _mode(tmp_path / "out" / "policy.rego") == 0o755
