"""Tests of .github/scripts/image_gate.py: which findings block an image, how
waivers and their expiry apply, its exit codes and failure paths, and that its
output stays inside a stop-commands block.

Each test runs the script in a throwaway copy of the repository where
docker, trivy.sh and fetch-tool.sh are fakes: ``docker image save`` writes
an archive that names the image, ``docker run`` answers as Grype with the
report the test wrote for that image, and trivy.sh writes the findings the
test wrote for it. No test uses the network or Docker.
"""

import datetime
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

import pytest

SCRIPT = ".github/scripts/image_gate.py"
SPEC = importlib.util.spec_from_file_location(
    "image_gate", Path(__file__).resolve().parents[1] / "image_gate.py"
)
assert SPEC is not None and SPEC.loader is not None
image_gate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = image_gate
SPEC.loader.exec_module(image_gate)

TODAY = datetime.date.today()
SERVER = "permitio/opal-server:test"
CLIENT = "permitio/opal-client:test"

FAKE_DOCKER = r"""set -euo pipefail
printf '%s\n' "$*" >>"$FAKE_LOG/docker"
name() { tr '/:@' '___' <<<"$1"; }
case $1 in
image)
  out=$4
  image=$5
  if [[ " ${FAKE_DOCKER_MISSING:-} " == *" $image "* ]]; then
    echo "Error response from daemon: reference does not exist" >&2
    exit 1
  fi
  printf '%s\n' "$image" >"$out"
  ;;
run)
  printf '%s %s\n' "${GH_TOKEN-unset}" "${GITHUB_TOKEN-unset}" >>"$FAKE_LOG/grype-env"
  archive=''
  for arg in "$@"; do
    [[ $arg != *:/scan/image.tar:ro ]] || archive=${arg%:/scan/image.tar:ro}
  done
  image=$(cat -- "$archive")
  if [[ -n ${FAKE_GRYPE_FAILS:-} ]]; then
    echo "failed to load vulnerability db" >&2
    exit 1
  fi
  report=$FAKE_REPORTS/grype-$(name "$image").json
  if [[ -f $report ]]; then
    cat -- "$report"
  else
    echo '{"matches": [], "distro": {"name": "wolfi", "version": "20230201"}}'
  fi
  ;;
*) exit 99 ;;
esac
"""

FAKE_TRIVY = r"""set -euo pipefail
name() { tr '/:@' '___' <<<"$1"; }
printf '%s %s %s\n' "$*" "${GH_TOKEN-unset}" "${GITHUB_TOKEN-unset}" >>"$FAKE_LOG/trivy"
image=$(cat -- "${2#archive:}")
echo "::error::trivy.sh output that must not be a workflow command"
[[ -z ${FAKE_TRIVY_FAILS:-} ]] || { echo "trivy: DID NOT RUN"; exit 2; }
findings=$FAKE_REPORTS/trivy-$(name "$image").jsonl
if [[ -f $findings ]]; then cp -- "$findings" "$3"; else : >"$3"; fi
echo "trivy: PASS"
"""

FAKE_FETCH_TOOL = r"""set -euo pipefail
printf '%s\n' "$1" >>"$FAKE_LOG/fetch-tool"
[[ -z ${FAKE_FETCH_FAILS:-} ]] || { echo "fetch-tool: download failed"; exit 2; }
echo "$PWD/bin/$1"
"""


def trivy(vuln_id, severity="high", fix="2.0", package="pkg", version="1.0", **extra):
    """A finding line as trivy.sh writes it."""
    entry = {
        "id": vuln_id,
        "package": package,
        "version": version,
        "fix": fix,
        "severity": severity,
        "aliases": [],
    }
    entry.update(extra)
    return entry


def grype(
    vuln_id, severity="High", fix=("2.0",), package="pkg", version="1.0", related=()
):
    """A match as Grype's JSON report lists it."""
    return {
        "vulnerability": {
            "id": vuln_id,
            "severity": severity,
            "fix": {"versions": list(fix), "state": "fixed" if fix else "not-fixed"},
        },
        "relatedVulnerabilities": [{"id": alias} for alias in related],
        "artifact": {"name": package, "version": version, "type": "python"},
    }


def waiver(vuln_id="CVE-2026-1", package="pkg", expires=None, **extra) -> str:
    """One [[waiver]] table."""
    expires = expires or TODAY + datetime.timedelta(days=30)
    lines = [
        "[[waiver]]",
        f'id = "{vuln_id}"',
        f'package = "{package}"',
        f"expires = {expires.isoformat()}",
        'reason = "accepted for the test"',
    ]
    for key, value in extra.items():
        lines.append(f"{key} = {json.dumps(value)}")
    return "\n".join(lines) + "\n"


class Gate:
    """A throwaway repository with image_gate.py and fakes of what it runs."""

    def __init__(self, repo, tmp_path: Path) -> None:
        self.repo = repo
        self.log = tmp_path / "log"
        self.reports = tmp_path / "reports"
        self.log.mkdir()
        self.reports.mkdir()
        repo.copy(SCRIPT)
        repo.write(
            ".github/scripts/trivy.sh", "#!/usr/bin/env bash\n" + FAKE_TRIVY, True
        )
        repo.write(
            ".github/scripts/fetch-tool.sh",
            "#!/usr/bin/env bash\n" + FAKE_FETCH_TOOL,
            True,
        )
        repo.stub("docker", FAKE_DOCKER)
        repo.copy(".github/grype/Dockerfile")
        self.waivers("")

    @staticmethod
    def _name(image: str) -> str:
        return re.sub(r"[/:@]", "_", image)

    def trivy(self, image: str, *findings: dict) -> None:
        path = self.reports / f"trivy-{self._name(image)}.jsonl"
        path.write_text("".join(json.dumps(finding) + "\n" for finding in findings))

    def grype(self, image: str, *matches: dict, raw: str | None = None) -> None:
        path = self.reports / f"grype-{self._name(image)}.json"
        report = {"matches": list(matches), "distro": {"name": "wolfi"}}
        path.write_text(raw if raw is not None else json.dumps(report))

    def waivers(self, text: str) -> None:
        self.repo.write(".github/image-waivers.toml", text)

    def run(self, *args: str, **env: str):
        return self.repo.run(
            SCRIPT,
            *args,
            env={"FAKE_LOG": str(self.log), "FAKE_REPORTS": str(self.reports), **env},
        )

    def logged(self, name: str) -> list[str]:
        path = self.log / name
        return path.read_text().splitlines() if path.exists() else []


@pytest.fixture
def gate(throwaway_repo, tmp_path):
    return Gate(throwaway_repo, tmp_path)


def commands(stdout: str) -> list[str]:
    """The lines after the stop-commands block: the verdict."""
    lines = stdout.splitlines()
    token = re.fullmatch(r"::stop-commands::([0-9a-f]{32})", lines[0]).group(1)
    return lines[lines.index(f"::{token}::") + 1 :]


def test_passes_an_image_without_findings(gate):
    result = gate.run(SERVER, CLIENT)

    assert result.returncode == 0, result.output
    assert commands(result.stdout) == ["image-gate: PASS"]
    docker = gate.logged("docker")
    assert [line.split()[:2] for line in docker] == [
        ["image", "save"],
        ["run", "--rm"],
        ["image", "save"],
        ["run", "--rm"],
    ]
    grype_image = image_gate.grype_image(image_gate.GRYPE_DOCKERFILE)
    assert f" {grype_image} docker-archive:/scan/image.tar --by-cve " in (
        docker[1] + " "
    )
    assert f" --user {os.getuid()}:{os.getgid()} " in docker[1]
    assert len(gate.logged("trivy")) == 2
    assert all(line.startswith("report archive:") for line in gate.logged("trivy"))
    assert gate.logged("fetch-tool") == ["trivy"]


def test_deletes_each_archive_after_its_scans(gate):
    result = gate.run(SERVER, CLIENT, RUNNER_TEMP=str(gate.repo.tmp))

    assert result.returncode == 0, result.output
    (work,) = gate.repo.tmp.glob("image-gate.*")
    assert list(work.glob("*.tar")) == []
    assert len(list(work.glob("trivy-*.jsonl"))) == 2


def test_a_fixable_high_finding_of_trivy_blocks(gate):
    gate.trivy(SERVER, trivy("CVE-2026-1", "high", "2.0"))

    result = gate.run(SERVER, CLIENT)

    assert result.returncode == 1, result.output
    assert "image-gate:   blocks: CVE-2026-1 high pkg 1.0, fixed in 2.0 (Trivy)" in (
        result.stdout
    )
    verdict = commands(result.stdout)
    assert verdict[0].startswith(f"::error title=Image gate::{SERVER}: 1 fixable HIGH")
    assert verdict[-1] == "image-gate: FAIL"
    assert not any(CLIENT in line for line in verdict)


def test_a_fixable_critical_finding_only_grype_reports_blocks(gate):
    gate.grype(
        CLIENT, grype("CVE-2026-2", "Critical", ("3.14.11",), "python", "3.14.10")
    )

    result = gate.run(SERVER, CLIENT)

    assert result.returncode == 1, result.output
    assert (
        "blocks: CVE-2026-2 critical python 3.14.10, fixed in 3.14.11 (Grype)"
        in result.stdout
    )


@pytest.mark.parametrize(
    "finding",
    [
        pytest.param(trivy("CVE-2026-3", "high", ""), id="high without a fix"),
        pytest.param(trivy("CVE-2026-3", "medium", "2.0"), id="medium with a fix"),
        pytest.param(trivy("CVE-2026-3", "", "2.0"), id="unknown severity"),
    ],
)
def test_a_finding_that_is_not_fixable_and_severe_passes(gate, finding):
    gate.trivy(SERVER, finding)
    gate.grype(SERVER, grype("CVE-2026-4", "High", ()))

    result = gate.run(SERVER)

    assert result.returncode == 0, result.output
    assert "findings by scanner: Trivy 1, Grype 1; 0 block, 0 waived" in result.stdout


def test_a_finding_both_scanners_report_is_one_line(gate):
    gate.trivy(SERVER, trivy("CVE-2026-5"))
    gate.grype(SERVER, grype("CVE-2026-5"))

    result = gate.run(SERVER)

    assert result.returncode == 1
    assert result.stdout.count("blocks: CVE-2026-5") == 1
    assert "fixed in 2.0 (Trivy, Grype)" in result.stdout


@pytest.mark.parametrize(
    ("waived", "finding"),
    [
        pytest.param(waiver("CVE-2026-6"), trivy("CVE-2026-6"), id="by id"),
        pytest.param(
            waiver("GHSA-aaaa-bbbb-cccc"),
            trivy("CVE-2026-6", aliases=["GHSA-aaaa-bbbb-cccc"]),
            id="by an alias",
        ),
        pytest.param(
            waiver("CVE-2026-6", package="Some_Package"),
            trivy("CVE-2026-6", package="some.package"),
            id="package name spelled differently",
        ),
        pytest.param(
            waiver("CVE-2026-6", version="1.0", images=["permitio/opal-server"]),
            trivy("CVE-2026-6"),
            id="with the version and the image",
        ),
    ],
)
def test_a_waiver_in_force_waives_the_finding(gate, waived, finding):
    gate.waivers(waived)
    gate.trivy(SERVER, finding)

    result = gate.run(SERVER)

    assert result.returncode == 0, result.output
    expires = (TODAY + datetime.timedelta(days=30)).isoformat()
    assert f"waived until {expires}: CVE-2026-6" in result.stdout
    assert "covers no finding" not in result.stdout


def test_a_report_only_image_is_reported_and_never_fails_the_gate(gate):
    eopa = "permitio/opal-client-eopa:test"
    gate.trivy(eopa, trivy("CVE-2026-8"))

    result = gate.run("--report-only", eopa, SERVER)

    assert result.returncode == 0, result.output
    assert "reported: CVE-2026-8" in result.stdout
    verdict = commands(result.stdout)
    assert verdict[0] == (
        f"::warning title=Image gate::{eopa}: 1 fixable HIGH or CRITICAL "
        "vulnerabilities (reported, not gated)"
    )
    assert verdict[-1] == "image-gate: PASS"
    assert len(gate.logged("trivy")) == 2


def test_a_report_only_image_that_cannot_be_scanned_did_not_run(gate):
    eopa = "permitio/opal-client-eopa:test"

    result = gate.run("--report-only", eopa, SERVER, FAKE_DOCKER_MISSING=eopa)

    assert result.returncode == 2
    assert commands(result.stdout)[0].startswith(
        f"::error title=Image gate::{eopa}: the gate did not run"
    )


def test_a_waiver_that_expires_today_still_applies(gate):
    gate.waivers(waiver(expires=TODAY))
    gate.trivy(SERVER, trivy("CVE-2026-1"))

    assert gate.run(SERVER).returncode == 0


@pytest.mark.parametrize(
    "waived",
    [
        pytest.param(waiver(version="0.9"), id="another version"),
        pytest.param(waiver(images=["permitio/opal-client"]), id="another image"),
        pytest.param(waiver(package="other"), id="another package"),
        pytest.param(waiver("CVE-2026-99"), id="another id"),
    ],
)
def test_a_waiver_for_something_else_does_not_waive(gate, waived):
    gate.waivers(waived)
    gate.trivy(SERVER, trivy("CVE-2026-1"))

    result = gate.run(SERVER)

    assert result.returncode == 1
    assert "covers no finding" in result.stdout


def test_an_expired_waiver_no_longer_applies(gate):
    yesterday = TODAY - datetime.timedelta(days=1)
    gate.waivers(waiver(expires=yesterday))
    gate.trivy(SERVER, trivy("CVE-2026-1"))

    result = gate.run(SERVER)

    assert result.returncode == 1
    assert "blocks: CVE-2026-1" in result.stdout
    assert f"the waiver of CVE-2026-1 in pkg expired on {yesterday}" in result.stdout


@pytest.mark.parametrize(
    ("text", "message"),
    [
        pytest.param(
            waiver(expires=TODAY + datetime.timedelta(days=181)),
            "more than 180 days ahead",
            id="an expiry too far ahead",
        ),
        pytest.param(
            waiver().replace('reason = "accepted for the test"\n', ""),
            "missing keys ['reason']",
            id="no reason",
        ),
        pytest.param(waiver(owner="me"), "unknown keys ['owner']", id="an unknown key"),
        pytest.param(
            waiver().replace(
                f"expires = {(TODAY + datetime.timedelta(days=30))}", 'expires = "soon"'
            ),
            "expires must be a date",
            id="an expiry that is not a date",
        ),
        pytest.param(waiver(images=[]), "images must be a list", id="no images"),
        pytest.param("[[waiver]\n", "cannot be read", id="not TOML"),
        pytest.param(
            "[other]\nkey = 1\n", "keys other than [[waiver]]", id="another table"
        ),
    ],
)
def test_a_waiver_file_that_is_not_valid_stops_the_gate(gate, text, message):
    gate.waivers(text)

    result = gate.run(SERVER)

    assert result.returncode == 2
    assert message in result.stdout
    assert commands(result.stdout)[0].startswith(
        "::error title=Image gate::the gate did not run"
    )
    assert gate.logged("docker") == []


def test_a_missing_waiver_file_stops_the_gate(gate, tmp_path):
    result = gate.run("--waivers", str(tmp_path / "missing.toml"), SERVER)

    assert result.returncode == 2
    assert "cannot be read" in result.stdout


def test_an_image_that_cannot_be_saved_did_not_run_and_the_others_still_scan(gate):
    gate.trivy(CLIENT, trivy("CVE-2026-1"))

    result = gate.run(SERVER, CLIENT, FAKE_DOCKER_MISSING=SERVER)

    assert result.returncode == 2
    verdict = commands(result.stdout)
    assert verdict[0].startswith(
        f"::error title=Image gate::{SERVER}: the gate did not run"
    )
    assert "docker could not save" in verdict[0]
    assert verdict[1].startswith(f"::error title=Image gate::{CLIENT}: 1 fixable")
    assert verdict[-1] == "image-gate: DID NOT RUN"


@pytest.mark.parametrize(
    ("env", "message"),
    [
        pytest.param(
            {"FAKE_TRIVY_FAILS": "1"}, "trivy.sh exited 2", id="trivy.sh fails"
        ),
        pytest.param({"FAKE_GRYPE_FAILS": "1"}, "Grype exited 1", id="Grype fails"),
    ],
)
def test_a_scanner_that_fails_did_not_run(gate, env, message):
    result = gate.run(SERVER, **env)

    assert result.returncode == 2
    assert message in commands(result.stdout)[0]


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param("not json", id="not JSON"),
        pytest.param('{"matches": {}}', id="matches not a list"),
        pytest.param(
            '{"matches": [{"vulnerability": {}}]}', id="a match without fields"
        ),
        pytest.param("{}", id="no matches"),
    ],
)
def test_grype_output_that_is_not_a_report_did_not_run(gate, raw):
    gate.grype(SERVER, raw=raw)

    result = gate.run(SERVER)

    assert result.returncode == 2
    assert "Grype's output is not a JSON report" in result.stdout


def test_trivy_findings_that_are_not_findings_did_not_run(gate):
    (gate.reports / "trivy-permitio_opal-server_test.jsonl").write_text('{"id": 1}\n')

    result = gate.run(SERVER)

    assert result.returncode == 2
    assert "trivy.sh wrote a line that is not a finding" in result.stdout


def test_trivy_that_cannot_be_installed_stops_the_gate(gate):
    result = gate.run(SERVER, FAKE_FETCH_FAILS="1")

    assert result.returncode == 2
    assert "installing Trivy with fetch-tool.sh failed" in result.stdout
    assert gate.logged("docker") == []


def test_wrong_arguments(gate):
    result = gate.run()

    assert result.returncode == 2
    assert commands(result.stdout) == [
        "::error title=Image gate::wrong arguments; the gate did not run"
    ]


@pytest.mark.parametrize(
    "env",
    [
        pytest.param({}, id="a passing gate"),
        pytest.param({"FAKE_TRIVY_FAILS": "1"}, id="a gate that did not run"),
    ],
)
def test_prints_scanner_output_with_workflow_commands_stopped(gate, env):
    result = gate.run(SERVER, **env)

    lines = result.stdout.splitlines()
    token = re.fullmatch(r"::stop-commands::([0-9a-f]{32})", lines[0]).group(1)
    resume = lines.index(f"::{token}::")
    assert any("trivy.sh output that must not" in line for line in lines[1:resume])
    assert result.stdout.count(token) == 2


def test_the_scanners_run_without_the_github_tokens(gate):
    result = gate.run(SERVER, GH_TOKEN="gh-token", GITHUB_TOKEN="github-token")

    assert result.returncode == 0, result.output
    logged = gate.logged("trivy") + gate.logged("grype-env")
    assert len(logged) == 2
    assert all("gh-token" not in line and "github-token" not in line for line in logged)


def test_appends_the_report_to_the_summary(gate, tmp_path):
    summary = tmp_path / "summary.md"
    summary.write_text("earlier\n")
    gate.waivers(waiver("CVE-2026-7"))
    gate.trivy(SERVER, trivy("CVE-2026-1", package="a|b"), trivy("CVE-2026-7"))

    result = gate.run("--summary", str(summary), SERVER)

    assert result.returncode == 1
    text = summary.read_text()
    assert text.startswith("earlier\n## Image gate (Trivy and Grype)")
    assert f"### `{SERVER}`: **1 findings block it**" in text
    assert "| blocks | CVE-2026-1 | high | a\\|b | 1.0 | 2.0 | Trivy |" in text
    assert "| waived until " in text


@pytest.mark.parametrize(
    ("image", "repository"),
    [
        ("permitio/opal-server:test", "permitio/opal-server"),
        ("permitio/opal-server", "permitio/opal-server"),
        ("registry.example:5000/opal/server:1.0", "registry.example:5000/opal/server"),
        ("permitio/opal-server@sha256:" + "0" * 64, "permitio/opal-server"),
        ("permitio/opal-server:1.0@sha256:" + "0" * 64, "permitio/opal-server"),
    ],
)
def test_the_repository_of_an_image(image, repository):
    assert image_gate.repository_of(image) == repository


def test_the_waiver_file_of_the_repository_is_valid():
    waivers = image_gate.load_waivers(image_gate.WAIVERS, TODAY)

    assert all(waiver.reason.strip() for waiver in waivers)
    lines = image_gate.WAIVERS.read_text().splitlines()
    assert [line for line in lines if len(line) > 100] == []


def test_the_grype_pin_is_a_digest_pinned_release_dependabot_updates():
    dockerfile = image_gate.GRYPE_DOCKERFILE.read_text()
    dependabot = (image_gate.ROOT / ".github" / "dependabot.yml").read_text()

    assert re.search(
        r"^FROM anchore/grype:v\d+\.\d+\.\d+@sha256:[0-9a-f]{64}$", dockerfile, re.M
    )
    assert "directory: /.github/grype" in dependabot


@pytest.mark.parametrize(
    "dockerfile",
    [
        pytest.param("FROM anchore/grype:v0.121.1\n", id="a tag without a digest"),
        pytest.param("# no FROM line\n", id="no FROM line"),
    ],
)
def test_a_grype_pin_without_a_digest_stops_the_gate(gate, dockerfile):
    gate.repo.write(".github/grype/Dockerfile", dockerfile)

    result = gate.run(SERVER)

    assert result.returncode == 2
    assert "pins no anchore/grype image by digest" in result.stdout
    assert gate.logged("docker") == []


@pytest.mark.parametrize(
    "distro",
    [
        pytest.param({"name": "", "version": ""}, id="an empty distro"),
        pytest.param(None, id="no distro"),
    ],
)
def test_a_grype_scan_that_found_no_os_did_not_run(gate, distro):
    report = {"matches": []}
    if distro is not None:
        report["distro"] = distro
    gate.grype(SERVER, raw=json.dumps(report))

    result = gate.run(SERVER)

    assert result.returncode == 2
    assert "Grype found no OS in the image" in result.stdout


@pytest.mark.parametrize(
    "args",
    [
        pytest.param(("--report-only", SERVER, SERVER), id="gated and reported only"),
        pytest.param(
            ("--report-only", CLIENT, "--report-only", CLIENT, SERVER), id="twice"
        ),
        pytest.param((SERVER, SERVER), id="gated twice"),
    ],
)
def test_an_image_named_twice_stops_the_gate(gate, args):
    gate.trivy(SERVER, trivy("CVE-2026-1"))

    result = gate.run(*args)

    assert result.returncode == 2
    assert "is named more than once" in result.stdout
    assert gate.logged("docker") == []


def test_report_only_findings_are_labelled_reported(gate, tmp_path):
    eopa = "permitio/opal-client-eopa:test"
    gate.trivy(eopa, trivy("CVE-2026-8"))
    summary = tmp_path / "summary.md"

    result = gate.run("--summary", str(summary), "--report-only", eopa, SERVER)

    assert result.returncode == 0, result.output
    assert "image-gate:   reported: CVE-2026-8 high pkg 1.0" in result.stdout
    assert "blocks: CVE-2026-8" not in result.stdout
    assert "| reported | CVE-2026-8 |" in summary.read_text()
