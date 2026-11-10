"""End-to-end tests for .github/scripts/security-scan.sh.

Each test runs the real scan script, format_security_report.py and notify.sh in a throwaway git
repository. gitleaks and TruffleHog are the real releases that .github/binaries.lock pins, fetched
once per test session; a test can swap TruffleHog for a fake one to reach a failure. The
dependency scans are stubbed: vuln.sh prepares two small trees, trivy.sh writes the findings the
test gives it, and a fake uv resolves the PyPI release. A fake curl stands in for the Slack
webhook and keeps the message it was sent.
"""

import json
import os
import re
import secrets
import shutil
import subprocess
from pathlib import Path

import pytest

SCAN = ".github/scripts/security-scan.sh"
COPIED = (
    SCAN,
    ".github/scripts/format_security_report.py",
    ".github/scripts/notify.sh",
    ".github/binaries.lock",
    ".gitleaks.toml",
)
REPO_ROOT = Path(__file__).resolve().parents[3]
WEBHOOK = "https://hooks.example.invalid/services/T0/B0/x"

FETCH_TOOL = """\
set -euo pipefail
root=$(CDPATH='' cd -- "$(dirname -- "$0")/../.." && pwd)
mkdir -p "$root/bin"
if [[ $1 == trufflehog && -n ${FAKE_TRUFFLEHOG:-} ]]; then
  cp "$FAKE_TRUFFLEHOG" "$root/bin/$1"
else
  cp "$TOOL_CACHE/$1" "$root/bin/$1"
fi
chmod +x "$root/bin/$1"
echo "$root/bin/$1"
"""

VULN = """\
set -euo pipefail
[[ $1 == --prepare ]] || exit 2
mkdir -p "$2/floor" "$2/ceiling"
echo "anyio==4.4.0" >"$2/floor/requirements.txt"
echo "anyio==4.14.2" >"$2/ceiling/requirements.txt"
"""

TRIVY = """\
set -euo pipefail
case $2 in
image:permitio/opal-server:latest) key=image-opal-server ;;
image:permitio/opal-client:latest) key=image-opal-client ;;
*/floor/requirements.txt) key=floor ;;
*/ceiling/requirements.txt) key=ceiling ;;
*) key=pypi-latest ;;
esac
if [[ -f $STUB_FINDINGS/$key.fail ]]; then
  echo "trivy: $(cat "$STUB_FINDINGS/$key.fail")"
  echo "trivy: DID NOT RUN"
  exit 2
fi
if [[ -f $STUB_FINDINGS/$key.jsonl ]]; then
  cp "$STUB_FINDINGS/$key.jsonl" "$3"
else
  : >"$3"
fi
echo "trivy: PASS"
"""

UV = """\
set -euo pipefail
while [[ $# -gt 0 ]]; do
  if [[ $1 == -o ]]; then
    printf 'opal-client==0.9.9\\nopal-server==0.9.9\\n' >"$2"
  fi
  shift
done
"""

CURL = """\
cat >"$CURL_PAYLOAD"
printf 200
"""


def lock_version(name: str) -> str:
    """The version .github/binaries.lock pins for a tool."""
    text = (REPO_ROOT / ".github/binaries.lock").read_text()
    section = text.split(f"[{name}]", 1)[1]
    match = re.search(r"^version\s*=\s*(\S+)", section, re.MULTILINE)
    assert match is not None
    return match.group(1)


@pytest.fixture(scope="session")
def tool_cache(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Gitleaks and TruffleHog as the real fetch-tool.sh installs them, once
    per session."""
    base = tmp_path_factory.mktemp("tools")
    (base / ".github/scripts").mkdir(parents=True)
    for relative in (".github/scripts/fetch-tool.sh", ".github/binaries.lock"):
        shutil.copy(REPO_ROOT / relative, base / relative)
    for tool in ("gitleaks", "trufflehog"):
        subprocess.run(
            [str(base / ".github/scripts/fetch-tool.sh"), tool],
            check=True,
            capture_output=True,
            timeout=300,
        )
    return base / "bin"


def git(root: Path, *args: str) -> str:
    """Run git in the throwaway repository without the user's or the system's
    configuration."""
    env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.hooksPath=/dev/null",
            *args,
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return completed.stdout.strip()


class Scan:
    """A throwaway repository set up to run the scan, and what the test gives
    its stubs."""

    def __init__(self, repo, tool_cache: Path) -> None:
        self.repo = repo
        self.tool_cache = tool_cache
        self.findings = repo.tmp / "stub-findings"
        self.findings.mkdir()
        self.payload = repo.tmp / "payload.json"
        self.summary = repo.tmp / "step-summary.md"
        repo.copy(*COPIED)
        repo.write(
            ".github/scripts/fetch-tool.sh", "#!/usr/bin/env bash\n" + FETCH_TOOL, True
        )
        repo.write(".github/scripts/vuln.sh", "#!/usr/bin/env bash\n" + VULN, True)
        repo.write(".github/scripts/trivy.sh", "#!/usr/bin/env bash\n" + TRIVY, True)
        repo.write(".gitignore", "/bin/\n")
        repo.write("README.md", "a throwaway repository\n")
        repo.stub("curl", CURL)
        repo.stub("gh", "exit 1\n")
        git(repo.root, "init", "--quiet")
        git(repo.root, "add", "-A")
        git(repo.root, "commit", "--quiet", "-m", "initial")
        repo.write("bin/uv", "#!/usr/bin/env bash\n" + UV, True)

    def give(self, source: str, findings: list[dict]) -> None:
        """Make trivy.sh report these findings for a source."""
        text = "".join(json.dumps(f) + "\n" for f in findings)
        (self.findings / f"{source}.jsonl").write_text(text)

    def fail(self, source: str, reason: str) -> None:
        """Make trivy.sh fail for a source with this reason."""
        (self.findings / f"{source}.fail").write_text(reason)

    def fake_trufflehog(self, body: str) -> Path:
        """A fake TruffleHog that reports the pinned version and then runs the
        body."""
        path = self.repo.tmp / "fake-trufflehog"
        version = lock_version("trufflehog")
        path.write_text(
            "#!/usr/bin/env bash\n"
            f'if [[ $1 == --version ]]; then echo "trufflehog {version}"; exit 0; fi\n'
            + body
        )
        path.chmod(0o755)
        return path

    def run(self, trufflehog: str = "run", fake_trufflehog: Path | None = None):
        env = {
            "GITHUB_REPOSITORY": "permitio/opal",
            "GITHUB_SERVER_URL": "https://github.com",
            "GITHUB_RUN_ID": "42",
            "GITHUB_STEP_SUMMARY": str(self.summary),
            "SECURITY_SLACK_WEBHOOK_URL": WEBHOOK,
            "TOOL_CACHE": str(self.tool_cache),
            "STUB_FINDINGS": str(self.findings),
            "CURL_PAYLOAD": str(self.payload),
        }
        if fake_trufflehog is not None:
            env["FAKE_TRUFFLEHOG"] = str(fake_trufflehog)
        return self.repo.run(SCAN, "--trufflehog", trufflehog, env=env)

    def posted(self) -> str:
        """The Slack message the fake curl was sent."""
        return json.loads(self.payload.read_text())["text"]


@pytest.fixture
def scan(throwaway_repo, tool_cache: Path) -> Scan:
    return Scan(throwaway_repo, tool_cache)


def pyjwt(severity: str = "critical") -> dict:
    return {
        "id": "CVE-2026-1",
        "package": "pyjwt",
        "version": "2.13.0",
        "fix": "2.14.0",
        "severity": severity,
        "title": "PyJWT accepts a forged token",
        "score": 9.1,
        "aliases": [],
        "url": "https://avd.aquasec.com/nvd/cve-2026-1",
    }


def row(summary: str, scanner: str, scope: str) -> str:
    """The job summary's table row of one source."""
    prefix = f"| {scanner} | {scope} | "
    return next(line for line in summary.splitlines() if line.startswith(prefix))


def test_a_full_scan_runs_trufflehog_on_the_bare_mirror(scan: Scan) -> None:
    scan.give("image-opal-server", [pyjwt()])
    scan.give("image-opal-client", [pyjwt()])
    result = scan.run()
    assert result.returncode == 0, result.output
    summary = scan.summary.read_text()
    assert row(summary, "TruffleHog", "git history, verified only").endswith(
        "| none verified |"
    )
    assert "0 findings, 0 accepted, 0 new" in row(summary, "gitleaks", "git history")
    assert row(summary, "Trivy", "opal-server:latest").endswith("| 1 critical |")
    assert row(summary, "Trivy", "oldest allowed versions").endswith(
        "| clean · 1 pinned packages |"
    )
    message = scan.posted()
    assert message.startswith(
        ":rotating_light: *permitio/opal: 1 high/critical vulnerability"
    )
    assert "• *critical 9.1* — `pyjwt@2.13.0` — PyJWT accepts a forged token" in message
    assert "_(server image, client image)_" in message
    assert "(`opal-client==0.9.9 opal-server==0.9.9`): clean" in message
    assert "(`all ecosystems`): skipped: no Dependabot alerts token" in message
    assert message.endswith(
        "<https://github.com/permitio/opal/actions/runs/42|Workflow run>"
    )
    assert result.stdout.rstrip().endswith(
        "security-scan: 1 high/critical vulnerability found"
    )


def test_without_trufflehog_the_report_has_no_trufflehog_line(scan: Scan) -> None:
    result = scan.run(trufflehog="skip")
    assert result.returncode == 0, result.output
    assert "• *TruffleHog*" not in scan.posted()
    assert "| TruffleHog |" not in scan.summary.read_text()
    assert scan.posted().startswith(":white_check_mark:")


def test_a_source_that_did_not_complete_fails_the_scan_with_its_reason(
    scan: Scan,
) -> None:
    scan.fail(
        "image-opal-server", "Trivy listed no package in permitio/opal-server:latest"
    )
    result = scan.run(trufflehog="skip")
    assert result.returncode == 2, result.output
    summary = scan.summary.read_text()
    assert row(summary, "Trivy", "opal-server:latest").endswith(
        "| did not complete: Trivy listed no package in permitio/opal-server:latest |"
    )
    message = scan.posted()
    assert message.startswith(":warning: *permitio/opal: security scan incomplete*")
    assert ":warning: did not complete: Trivy listed no package" in message
    assert result.stdout.rstrip().endswith("security-scan: security scan incomplete")


def test_a_shallow_clone_makes_both_history_scans_incomplete(scan: Scan) -> None:
    head = git(scan.repo.root, "rev-parse", "HEAD")
    (scan.repo.root / ".git/shallow").write_text(head + "\n")
    result = scan.run()
    assert result.returncode == 2, result.output
    summary = scan.summary.read_text()
    reason = "did not complete: the repository is a shallow clone, which lacks part of the history"
    assert reason in row(summary, "gitleaks", "git history")
    assert reason in row(summary, "TruffleHog", "git history, verified only")


def test_a_trufflehog_error_is_shown_without_what_could_be_a_secret(scan: Scan) -> None:
    # Made at run time, so this file holds no token that a secret scan would flag.
    token = "ghp_" + secrets.token_hex(18)
    fake = scan.fake_trufflehog(
        'error="failed to scan Git: stat ${2#file://}/.git: no such file or directory, '
        f'token {token} from https://user:hunter2@example.com/repo.git"\n'
        'printf \'{"level":"error","msg":"error running scan","error":"%s"}\\n\' "$error" >&2\n'
        "exit 1\n"
    )
    result = scan.run(fake_trufflehog=fake)
    assert result.returncode == 2, result.output
    expected = (
        "trufflehog exited 1: failed to scan Git: stat <work>/mirror.git/.git: no such file or "
        "directory, token <redacted> from <url>"
    )
    assert expected in result.stdout
    assert expected in scan.posted().replace("&lt;", "<").replace("&gt;", ">")
    for text in (result.output, scan.summary.read_text(), scan.posted()):
        assert token not in text
        assert "hunter2" not in text


def test_a_verified_secret_fails_the_scan_and_is_listed_in_slack_only(
    scan: Scan,
) -> None:
    secret = {
        "Verified": True,
        "DetectorName": "AWS",
        "Redacted": "AKIAEXAMPLEREDACTED",
        "Raw": "the-raw-secret-value",
        "SourceMetadata": {
            "Data": {
                "Git": {"file": "creds.py", "line": 3, "commit": "abc123def4567890"}
            }
        },
    }
    finished = {
        "level": "info",
        "msg": "finished scanning",
        "chunks": 5,
        "verified_secrets": 1,
    }
    fake = scan.fake_trufflehog(
        f"echo '{json.dumps(secret)}'\n" f"echo '{json.dumps(finished)}' >&2\n"
    )
    result = scan.run(fake_trufflehog=fake)
    assert result.returncode == 1, result.output
    message = scan.posted()
    assert message.startswith(
        ":rotating_light: *permitio/opal: TruffleHog verified 1 secret that works, revoke now*"
    )
    assert "• *verified* — `creds.py:3` — AWS — commit `abc123def456`" in message
    assert "AKIAEXAMPLEREDACTED" in message
    for text in (result.output, scan.summary.read_text()):
        assert "creds.py" not in text
        assert "AKIAEXAMPLEREDACTED" not in text
    for text in (result.output, scan.summary.read_text(), message):
        assert "the-raw-secret-value" not in text
