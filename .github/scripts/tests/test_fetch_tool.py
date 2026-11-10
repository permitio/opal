"""Tests of .github/scripts/fetch-tool.sh: what it installs, its exit codes and
its failure paths.

Each test runs the script in a throwaway copy of the repository with a
.github/binaries.lock of its own. A fake curl serves an archive the test
builds, and a fake uname names the platform, so no test uses the network
and every platform's entry is checked on any machine.
"""

import hashlib
import io
import tarfile
from pathlib import Path

import pytest

SCRIPT = ".github/scripts/fetch-tool.sh"
LOCK = ".github/binaries.lock"
URL = "https://downloads.example.invalid/fake/v{version}/fake_{version}_{os}_{arch}.tar.gz"
BINARY = "fake_{os}_{arch}/fake"
PLATFORMS = ("darwin/arm64", "darwin/amd64", "linux/amd64", "linux/arm64")
WRONG_SHA = "f" * 64
LINUX_AMD64 = ("Linux", "x86_64")
LINUX_AMD64_BINARY = "fake_linux_x86_64/fake"

FAKE_UNAME = r"""set -euo pipefail
case $1 in
-s) echo "$FAKE_UNAME_S" ;;
-m) echo "$FAKE_UNAME_M" ;;
*)
  echo "fake uname: unexpected argument $1" >&2
  exit 1
  ;;
esac
"""

# The fake curl logs the URL it was given (its last argument), then fails when FAKE_CURL_FAIL is
# set, or copies FAKE_CURL_FILE to the --output path.
FAKE_CURL = r"""set -euo pipefail
printf '%s\n' "${@: -1}" >>"$FAKE_CURL_LOG"
if [[ -n ${FAKE_CURL_FAIL:-} ]]; then
  echo "curl: (22) The requested URL returned error: 404" >&2
  exit 22
fi
while [[ $# -gt 1 ]]; do
  if [[ $1 == --output ]]; then
    cp -- "$FAKE_CURL_FILE" "$2"
  fi
  shift
done
"""


def entry(
    name: str = "fake", shas: dict[str, str] | None = None, **changes: str | None
) -> str:
    """Build a [name] entry of the lock.

    Args:
        name: The entry's name.
        shas: The sha256 for some platforms, such as {"linux/amd64": "..."}; the others get
            WRONG_SHA.
        **changes: Keys to change, with "_" for "." and "__" for "/" in the key (os_darwin for
            os.darwin, sha256_linux__arm64 for sha256.linux/arm64); None drops the key.

    Returns:
        The entry's lines.
    """
    keys: dict[str, str | None] = {
        "version": "1.2.3",
        "url": URL,
        "archive": "tar.gz",
        "binary": BINARY,
        "os.darwin": "macOS",
        "arch.amd64": "x86_64",
    }
    for platform in PLATFORMS:
        keys[f"sha256.{platform}"] = (shas or {}).get(platform, WRONG_SHA)
    for key, value in changes.items():
        keys[key.replace("__", "/").replace("_", ".")] = value
    lines = [f"[{name}]"] + [
        f"{key} = {value}" for key, value in keys.items() if value is not None
    ]
    return "\n".join(lines) + "\n"


class Fetch:
    """A throwaway repository with fetch-tool.sh, fake curl and fake uname."""

    def __init__(self, repo, tmp_path: Path) -> None:
        self.repo = repo
        self.download = tmp_path / "download.tar.gz"
        self.curl_log = tmp_path / "curl.log"
        self.marker = tmp_path / "the-binary-ran"
        self.binary_text = f'#!/bin/sh\necho ran >>"{self.marker}"\n'
        repo.copy(SCRIPT)
        repo.stub("curl", FAKE_CURL)
        repo.stub("uname", FAKE_UNAME)

    def archive(self, members: dict[str, str | None]) -> str:
        """Write the archive that the fake curl serves.

        Args:
            members: Each member's path and its text, or None for a directory.

        Returns:
            The archive's sha256.
        """
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            for member_path, text in members.items():
                info = tarfile.TarInfo(member_path)
                if text is None:
                    info.type = tarfile.DIRTYPE
                    info.mode = 0o755
                    archive.addfile(info)
                    continue
                data = text.encode()
                info.size = len(data)
                info.mode = 0o644
                archive.addfile(info, io.BytesIO(data))
        self.download.write_bytes(buffer.getvalue())
        return hashlib.sha256(buffer.getvalue()).hexdigest()

    def lock(self, text: str) -> None:
        self.repo.write(LOCK, text)

    def run(self, *args: str, uname=LINUX_AMD64, curl_fails: bool = False, env=None):
        full_env = {
            "FAKE_UNAME_S": uname[0],
            "FAKE_UNAME_M": uname[1],
            "FAKE_CURL_LOG": str(self.curl_log),
            "FAKE_CURL_FILE": str(self.download),
        }
        if curl_fails:
            full_env["FAKE_CURL_FAIL"] = "1"
        full_env.update(env or {})
        return self.repo.run(SCRIPT, *args, env=full_env)

    @property
    def urls(self) -> list[str]:
        """The URLs the fake curl was asked for."""
        if not self.curl_log.exists():
            return []
        return self.curl_log.read_text().splitlines()

    @property
    def installed(self) -> Path:
        return self.repo.root / "bin" / "fake"


@pytest.fixture
def fetch(throwaway_repo, tmp_path):
    return Fetch(throwaway_repo, tmp_path)


@pytest.mark.parametrize(
    ("uname", "platform", "url_os", "url_arch"),
    [
        (("Linux", "x86_64"), "linux/amd64", "linux", "x86_64"),
        (("Linux", "amd64"), "linux/amd64", "linux", "x86_64"),
        (("Linux", "aarch64"), "linux/arm64", "linux", "arm64"),
        (("Darwin", "arm64"), "darwin/arm64", "macOS", "arm64"),
        (("Darwin", "x86_64"), "darwin/amd64", "macOS", "x86_64"),
    ],
)
def test_installs_the_binary_for_the_platform(fetch, uname, platform, url_os, url_arch):
    binary = BINARY.format(os=url_os, arch=url_arch)
    sha = fetch.archive({binary: fetch.binary_text, "README": "not installed\n"})
    fetch.lock(entry(shas={platform: sha}))

    result = fetch.run("fake", uname=uname)

    assert result.returncode == 0, result.output
    assert Path(result.stdout.strip()).resolve() == fetch.installed.resolve()
    assert result.stdout.count("\n") == 1, "stdout holds only the installed path"
    assert f"installed fake 1.2.3 for {platform} as bin/fake" in result.stderr
    assert fetch.urls == [URL.format(version="1.2.3", os=url_os, arch=url_arch)]
    assert fetch.installed.read_text() == fetch.binary_text
    assert fetch.installed.stat().st_mode & 0o777 == 0o755
    assert sorted(path.name for path in fetch.installed.parent.iterdir()) == ["fake"]
    assert not fetch.marker.exists(), "fetch-tool.sh ran the binary it downloaded"


def test_reads_comments_blank_lines_other_entries_and_keys_without_spaces(fetch):
    sha = fetch.archive({LINUX_AMD64_BINARY: fetch.binary_text})
    lock = (
        "# a comment\n\n"
        + entry("other", url="https://other.example.invalid/{version}.tar.gz")
        + "\n   # an indented comment\n"
        + entry(shas={"linux/amd64": sha}).replace(" = ", "=")
    )
    fetch.lock(lock)

    result = fetch.run("fake")

    assert result.returncode == 0, result.output
    assert fetch.installed.read_text() == fetch.binary_text


def test_replaces_an_installed_binary(fetch):
    sha = fetch.archive({LINUX_AMD64_BINARY: fetch.binary_text})
    fetch.lock(entry(shas={"linux/amd64": sha}))
    fetch.installed.parent.mkdir()
    fetch.installed.write_text("the old version\n")

    result = fetch.run("fake")

    assert result.returncode == 0, result.output
    assert fetch.installed.read_text() == fetch.binary_text


def test_keeps_the_download_out_of_the_repository(fetch, tmp_path):
    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir()
    sha = fetch.archive({LINUX_AMD64_BINARY: fetch.binary_text})
    fetch.lock(entry(shas={"linux/amd64": sha}))

    result = fetch.run("fake", env={"RUNNER_TEMP": str(runner_temp)})

    assert result.returncode == 0, result.output
    assert sorted(path.name for path in fetch.repo.root.iterdir()) == [".github", "bin"]
    assert [path.name.split(".")[0] for path in runner_temp.iterdir()] == ["fetch-tool"]


@pytest.mark.parametrize("installed_before", [None, "the old version\n"])
def test_a_sha256_mismatch_installs_nothing(fetch, installed_before):
    fetch.archive({LINUX_AMD64_BINARY: fetch.binary_text})
    fetch.lock(entry())
    if installed_before is not None:
        fetch.installed.parent.mkdir()
        fetch.installed.write_text(installed_before)

    result = fetch.run("fake")

    assert result.returncode == 2
    assert "sha256 mismatch" in result.stderr
    assert f"want {WRONG_SHA}" in result.stderr
    assert "nothing was installed" in result.stderr
    if installed_before is None:
        assert not fetch.installed.parent.exists()
    else:
        assert fetch.installed.read_text() == installed_before
        assert sorted(path.name for path in fetch.installed.parent.iterdir()) == [
            "fake"
        ]


def test_takes_the_sha256_of_the_platform_it_runs_on(fetch):
    sha = fetch.archive({LINUX_AMD64_BINARY: fetch.binary_text})
    fetch.lock(
        entry(shas={"linux/arm64": sha, "darwin/amd64": sha, "darwin/arm64": sha})
    )

    result = fetch.run("fake", uname=LINUX_AMD64)

    assert result.returncode == 2
    assert "sha256 mismatch" in result.stderr
    assert not fetch.installed.exists()


def test_a_failed_download_installs_nothing(fetch):
    fetch.lock(entry())

    result = fetch.run("fake", curl_fails=True)

    url = URL.format(version="1.2.3", os="linux", arch="x86_64")
    assert result.returncode == 2
    assert f"downloading {url} failed" in result.stderr
    assert not fetch.installed.parent.exists()


def test_a_temporary_directory_that_cannot_be_made(fetch, tmp_path):
    fetch.lock(entry())

    result = fetch.run("fake", env={"RUNNER_TEMP": str(tmp_path / "missing")})

    assert result.returncode == 2
    assert "creating a temporary directory failed" in result.stderr
    assert fetch.urls == []
    assert not fetch.installed.parent.exists()


def test_a_missing_lock(fetch):
    result = fetch.run("fake")

    assert result.returncode == 2
    assert ".github/binaries.lock is missing or not readable" in result.stderr
    assert fetch.urls == []


def test_no_entry_for_the_name(fetch):
    fetch.lock(entry("other"))

    result = fetch.run("fake")

    assert result.returncode == 2
    assert ".github/binaries.lock has no [fake] entry" in result.stderr
    assert fetch.urls == []


@pytest.mark.parametrize(
    ("lock", "message"),
    [
        pytest.param(entry(version=None), "[fake] has no version", id="no version"),
        pytest.param(entry(url=None), "[fake] has no url", id="no url"),
        pytest.param(entry(archive=None), "[fake] has no archive", id="no archive"),
        pytest.param(entry(binary=None), "[fake] has no binary", id="no binary"),
        pytest.param(
            entry(sha256_linux__amd64=None),
            "[fake] has no sha256.linux/amd64",
            id="no sha256 for the platform it runs on",
        ),
        pytest.param(
            entry(sha256_darwin__arm64=None),
            "[fake] has no sha256.darwin/arm64",
            id="no sha256 for another platform",
        ),
        pytest.param(
            entry(sha256_linux__amd64="A" * 64),
            "is not 64 lowercase hex digits",
            id="an uppercase sha256",
        ),
        pytest.param(
            entry(sha256_linux__amd64="a" * 63),
            "is not 64 lowercase hex digits",
            id="short sha256",
        ),
        pytest.param(
            entry(archive="zip"), "archive zip is not supported", id="a zip archive"
        ),
        pytest.param(
            entry(url="http://downloads.example.invalid/fake.tar.gz"),
            "is not an https URL",
            id="an http URL",
        ),
        pytest.param(
            entry(url="https://downloads.example.invalid/{name}.tar.gz"),
            "has an unknown placeholder",
            id="an unknown placeholder in the URL",
        ),
        pytest.param(
            entry(binary="fake_{platform}/fake"),
            "has an unknown placeholder",
            id="an unknown placeholder in the binary",
        ),
        pytest.param(
            entry(checksum="abc"), "unknown key checksum in [fake]", id="unknown key"
        ),
        pytest.param(
            entry() + "version = 9.9.9\n",
            "version is set twice in [fake]",
            id="a key set twice",
        ),
        pytest.param(entry() + entry(), "[fake] appears twice", id="an entry twice"),
        pytest.param(
            "version = 1.2.3\n" + entry(),
            "version = 1.2.3 is outside an entry",
            id="outside",
        ),
        pytest.param(
            entry() + "not a key\n", "want [name] or key = value", id="malformed line"
        ),
    ],
)
def test_an_incomplete_or_wrong_entry_downloads_nothing(fetch, lock, message):
    fetch.lock(lock)

    result = fetch.run("fake")

    assert result.returncode == 2
    assert message in result.stderr
    assert fetch.urls == []
    assert not fetch.installed.parent.exists()


@pytest.mark.parametrize(
    ("uname", "message"),
    [
        (("FreeBSD", "x86_64"), "unsupported OS FreeBSD"),
        (("Linux", "i686"), "unsupported architecture i686"),
    ],
)
def test_an_unsupported_platform(fetch, uname, message):
    fetch.lock(entry())

    result = fetch.run("fake", uname=uname)

    assert result.returncode == 2
    assert message in result.stderr
    assert fetch.urls == []


@pytest.mark.parametrize("kind", ["directory", "symlink to a directory"])
def test_an_installed_path_that_is_not_a_regular_file(fetch, kind):
    fetch.lock(entry())
    fetch.installed.parent.mkdir()
    if kind == "directory":
        fetch.installed.mkdir()
    else:
        (fetch.installed.parent / "elsewhere").mkdir()
        fetch.installed.symlink_to("elsewhere")

    result = fetch.run("fake")

    assert result.returncode == 2
    assert "bin/fake exists and is not a regular file" in result.stderr
    assert fetch.urls == []
    assert fetch.installed.is_dir()


@pytest.mark.parametrize(
    "name", ["", "../fake", "-fake", ".fake", "fa ke", "fake/x", "fake\n"]
)
def test_a_name_that_is_not_a_tool_name(fetch, name):
    fetch.lock(entry())

    result = fetch.run(name)

    assert result.returncode == 2
    assert "is not a tool name" in result.stderr
    assert fetch.urls == []


@pytest.mark.parametrize(
    "args", [(), ("fake", "extra")], ids=["no argument", "two arguments"]
)
def test_a_wrong_number_of_arguments(fetch, args):
    fetch.lock(entry())

    result = fetch.run(*args)

    assert result.returncode == 2
    assert "usage: fetch-tool.sh <name>" in result.stderr
    assert fetch.urls == []


@pytest.mark.parametrize(
    "members",
    [
        pytest.param({"elsewhere/fake": "#!/bin/sh\n"}, id="the binary is missing"),
        pytest.param({LINUX_AMD64_BINARY: None}, id="the binary is a directory"),
    ],
)
def test_an_archive_without_the_binary_installs_nothing(fetch, members):
    sha = fetch.archive(members)
    fetch.lock(entry(shas={"linux/amd64": sha}))

    result = fetch.run("fake")

    assert result.returncode == 2
    assert f"extracting {LINUX_AMD64_BINARY} from" in result.stderr
    assert not fetch.installed.exists()
