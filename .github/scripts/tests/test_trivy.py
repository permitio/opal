"""Tests of .github/scripts/trivy.sh: its block and report policies, its exit
codes, the checks that decide whether a scan counts, and the findings file.

Each test runs the script in a throwaway copy of the repository whose
bin/trivy is a fake: it prints the version the copy's
.github/binaries.lock pins and a JSON report the test writes, and
records how it was run.
"""

import json
from pathlib import Path

import pytest

SCRIPT = ".github/scripts/trivy.sh"
VERSION = "0.70.2"

# The fake Trivy answers --version like Trivy; otherwise it records its arguments, its working
# directory and its TRIVY_ variables, prints a line on stderr and prints the report.
FAKE_TRIVY = r"""set -euo pipefail
if [[ ${1:-} == --version ]]; then
  [[ -z ${FAKE_TRIVY_VERSION_FAILS:-} ]] || exit 1
  printf 'Version: %s\nVulnerability DB:\n  Version: 2\n' "$FAKE_TRIVY_VERSION"
  exit 0
fi
printf '%s\n' "$@" >"$FAKE_TRIVY_OUT/args"
{ pwd; ls -A; } >"$FAKE_TRIVY_OUT/cwd"
env | grep '^TRIVY_' >"$FAKE_TRIVY_OUT/env" || true
echo "fake trivy: scanning" >&2
cat -- "$FAKE_TRIVY_OUT/report"
exit "${FAKE_TRIVY_EXIT:-0}"
"""

PINS = """\
# a comment, not a pin
pkg0==1.0 \\
    --hash=sha256:0000000000000000000000000000000000000000000000000000000000000000
    # via something
pkg1[extra]==2.0
"""
PIN_COUNT = 2


def vuln(vuln_id: str, severity: str, fixed: str | None = None, **fields) -> dict:
    """A vulnerability as Trivy's JSON report lists it.

    Args:
        vuln_id: Its VulnerabilityID.
        severity: Its Severity, such as "HIGH".
        fixed: Its FixedVersion; None leaves the field out, as Trivy does when there is no fix.
        **fields: Other fields, which override the defaults.

    Returns:
        The vulnerability.
    """
    found = {
        "VulnerabilityID": vuln_id,
        "PkgName": "pkg0",
        "InstalledVersion": "1.0",
        "Severity": severity,
        "PrimaryURL": f"https://avd.aquasec.com/nvd/{vuln_id.lower()}",
    }
    if fixed is not None:
        found["FixedVersion"] = fixed
    found.update(fields)
    return found


def report(
    vulns=(),
    packages: int = PIN_COUNT,
    root_package: bool = False,
    os_family: str | None = None,
) -> dict:
    """A Trivy JSON report of one target.

    Args:
        vulns: Its vulnerabilities.
        packages: The number of packages it lists, besides the root.
        root_package: Whether it also lists a package of relationship "root".

    Returns:
        The report.
    """
    listed = [{"Name": f"pkg{i}", "Version": "1.0"} for i in range(packages)]
    if root_package:
        listed.append({"Name": "project", "Version": "0", "Relationship": "root"})
    found = {
        "SchemaVersion": 2,
        "ArtifactType": "filesystem",
        "Results": [
            {
                "Target": "requirements.txt",
                "Packages": listed,
                "Vulnerabilities": list(vulns),
            }
        ],
    }
    if os_family is not None:
        found["Metadata"] = {"OS": {"Family": os_family, "Name": "20230201"}}
    return found


class Trivy:
    """A throwaway repository with trivy.sh, a lock and a fake bin/trivy."""

    def __init__(self, repo, tmp_path: Path) -> None:
        self.repo = repo
        self.out = tmp_path / "fake-trivy"
        self.out.mkdir()
        self.pins = tmp_path / "requirements.txt"
        self.pins.write_text(PINS)
        self.findings = tmp_path / "findings.jsonl"
        repo.copy(SCRIPT)
        repo.write(
            ".github/binaries.lock",
            f"[uv]\nversion = 9.9.9\n\n[trivy]\nversion = {VERSION}\n",
        )
        repo.write("bin/trivy", "#!/usr/bin/env bash\n" + FAKE_TRIVY, executable=True)
        self.report(report())

    def report(self, content) -> None:
        """Set what the fake Trivy prints: a report, or text as it is."""
        text = content if isinstance(content, str) else json.dumps(content)
        (self.out / "report").write_text(text)

    def run(self, *args: str, env=None, path=None):
        full_env = {"FAKE_TRIVY_OUT": str(self.out), "FAKE_TRIVY_VERSION": VERSION}
        full_env.update(env or {})
        return self.repo.run(SCRIPT, *args, env=full_env, path=path)

    def scan(self, policy: str = "block", findings: bool = False, **kwargs):
        args = [policy, str(self.pins)]
        if findings:
            args.append(str(self.findings))
        return self.run(*args, **kwargs)

    @property
    def args(self) -> list[str]:
        return (self.out / "args").read_text().splitlines()


@pytest.fixture
def trivy(throwaway_repo, tmp_path):
    return Trivy(throwaway_repo, tmp_path)


def last_line(text: str) -> str:
    return text.rstrip("\n").rsplit("\n", 1)[-1]


def test_passes_without_a_fixable_high_or_critical_vulnerability(trivy):
    trivy.report(
        report(
            [
                vuln("CVE-1", "HIGH"),
                vuln("CVE-2", "CRITICAL", fixed=""),
                vuln("CVE-3", "MEDIUM", fixed="1.1"),
                vuln("CVE-4", "LOW", fixed="1.1"),
            ]
        )
    )

    result = trivy.scan("block")

    assert result.returncode == 0, result.output
    assert (
        "trivy: vulnerabilities: 1 CRITICAL, 1 HIGH, 1 LOW, 1 MEDIUM; HIGH or CRITICAL with a"
        " fixed version: 0 (block)"
    ) in result.stdout
    assert f"trivy: {trivy.pins}: 2 packages, 2 pins; Trivy {VERSION}" in result.stdout
    assert last_line(result.stdout) == "trivy: PASS"


def test_no_vulnerability(trivy):
    result = trivy.scan("block")

    assert result.returncode == 0, result.output
    assert (
        "vulnerabilities: none; HIGH or CRITICAL with a fixed version: 0"
        in result.stdout
    )
    assert last_line(result.stdout) == "trivy: PASS"


@pytest.mark.parametrize("severity", ["HIGH", "CRITICAL"])
@pytest.mark.parametrize(
    ("policy", "code", "verdict"),
    [("block", 1, "trivy: FAIL"), ("report", 0, "trivy: PASS")],
)
def test_a_fixable_high_or_critical_vulnerability(
    trivy, severity, policy, code, verdict
):
    trivy.report(report([vuln("CVE-1", severity, fixed="1.1")]))

    result = trivy.scan(policy)

    assert result.returncode == code, result.output
    assert f"HIGH or CRITICAL with a fixed version: 1 ({policy})" in result.stdout
    assert last_line(result.stdout) == verdict


def test_lists_the_fixable_high_and_critical_vulnerabilities_critical_first(trivy):
    trivy.report(
        report(
            [
                vuln("CVE-A", "HIGH", fixed="1.1"),
                vuln(
                    "CVE-B",
                    "CRITICAL",
                    fixed="2.0",
                    PkgName="pkg1",
                    VendorIDs=["GHSA-1", "X"],
                ),
                vuln("CVE-C", "MEDIUM", fixed="1.2"),
                vuln("CVE-D", "HIGH"),
            ]
        )
    )

    result = trivy.scan("report")

    assert result.returncode == 0, result.output
    listed = [
        line for line in result.stdout.splitlines() if not line.startswith("trivy:")
    ]
    assert listed == [
        "CVE-B (GHSA-1, X)  CRITICAL, fixed in 2.0: pkg1 1.0",
        "CVE-A  HIGH, fixed in 1.1: pkg0 1.0",
    ]


def test_does_not_count_the_root_package(trivy):
    trivy.report(report(root_package=True))

    result = trivy.scan()

    assert result.returncode == 0, result.output


@pytest.mark.parametrize("packages", [PIN_COUNT - 1, PIN_COUNT + 1])
def test_a_package_count_that_does_not_match_the_pins(trivy, packages):
    trivy.report(report([vuln("CVE-1", "HIGH", fixed="1.1")], packages=packages))

    result = trivy.scan("block", findings=True)

    assert result.returncode == 2
    assert (
        f"Trivy listed {packages} packages for {trivy.pins}, which has 2 pins"
        in result.stdout
    )
    assert last_line(result.stdout) == "trivy: DID NOT RUN"
    assert not trivy.findings.exists(), (
        "the findings file is written only when the scan counts"
    )


@pytest.mark.parametrize(
    "output",
    [
        pytest.param("", id="nothing"),
        pytest.param("FATAL error\n", id="text"),
        pytest.param(
            '{"SchemaVersion": 1, "ArtifactType": "filesystem"}', id="schema 1"
        ),
        pytest.param('{"SchemaVersion": 2}', id="no artifact type"),
        pytest.param("[]", id="a list"),
    ],
)
def test_output_that_is_not_a_json_report(trivy, output):
    trivy.report(output)

    result = trivy.scan("report", findings=True)

    assert result.returncode == 2
    assert "trivy: Trivy's output is not a JSON report" in result.stdout
    assert last_line(result.stdout) == "trivy: DID NOT RUN"
    assert not trivy.findings.exists()


def test_a_report_whose_results_are_not_a_list(trivy):
    trivy.report({"SchemaVersion": 2, "ArtifactType": "filesystem", "Results": "none"})

    result = trivy.scan("report")

    assert result.returncode == 2
    assert "trivy: Trivy's report has no list of packages" in result.stdout
    assert last_line(result.stdout) == "trivy: DID NOT RUN"


def test_trivy_fails(trivy):
    result = trivy.scan(env={"FAKE_TRIVY_EXIT": "1"})

    assert result.returncode == 2
    assert "fake trivy: scanning" in result.stdout, "Trivy's log is printed"
    assert "trivy: Trivy exited 1" in result.stdout
    assert last_line(result.stdout) == "trivy: DID NOT RUN"


def test_trivy_of_another_version(trivy):
    result = trivy.scan(env={"FAKE_TRIVY_VERSION": "0.70.3"})

    assert result.returncode == 2
    assert (
        f'bin/trivy reports "Version: 0.70.3", want version {VERSION}' in result.stdout
    )
    assert last_line(result.stdout) == "trivy: DID NOT RUN"
    assert not (trivy.out / "args").exists(), "Trivy of another version scanned"


def test_trivy_version_fails(trivy):
    result = trivy.scan(env={"FAKE_TRIVY_VERSION_FAILS": "1"})

    assert result.returncode == 2
    assert "bin/trivy --version failed" in result.stdout


def test_trivy_is_missing(trivy):
    (trivy.repo.root / "bin" / "trivy").unlink()

    result = trivy.scan()

    assert result.returncode == 2
    assert "bin/trivy is missing" in result.stdout


@pytest.mark.parametrize(
    "lock",
    [
        pytest.param(f"[trivy]\nversion={VERSION}\n", id="no spaces around ="),
        pytest.param(
            f"[uv]\nversion = 9.9.9\n[trivy]\nurl = x\nversion  =  {VERSION}  \n[gitleaks]\n"
            "version = 1.0.0\n",
            id="between other entries",
        ),
    ],
)
def test_reads_the_version_of_the_trivy_entry(trivy, lock):
    trivy.repo.write(".github/binaries.lock", lock)

    result = trivy.scan()

    assert result.returncode == 0, result.output


def test_a_lock_without_a_trivy_version(trivy):
    trivy.repo.write(".github/binaries.lock", "[uv]\nversion = 9.9.9\n")

    result = trivy.scan()

    assert result.returncode == 2
    assert ".github/binaries.lock has no version for trivy" in result.stdout


def test_writes_every_vulnerability_to_the_findings_file(trivy):
    trivy.report(
        report(
            [
                vuln("CVE-1", "HIGH", fixed="1.1"),
                vuln("CVE-2", "UNKNOWN", PrimaryURL=None),
                vuln(
                    "CVE-3", "LOW", fixed="1.2", PkgName="pkg1", InstalledVersion="2.0"
                ),
            ]
        )
    )

    result = trivy.scan("report", findings=True)

    assert result.returncode == 0, result.output
    lines = [json.loads(line) for line in trivy.findings.read_text().splitlines()]
    want = [
        {
            "id": "CVE-1",
            "package": "pkg0",
            "version": "1.0",
            "fix": "1.1",
            "severity": "high",
            "url": "https://avd.aquasec.com/nvd/cve-1",
        },
        {
            "id": "CVE-2",
            "package": "pkg0",
            "version": "1.0",
            "fix": "",
            "severity": "",
            "url": "",
        },
        {
            "id": "CVE-3",
            "package": "pkg1",
            "version": "2.0",
            "fix": "1.2",
            "severity": "low",
            "url": "https://avd.aquasec.com/nvd/cve-3",
        },
    ]
    assert len(lines) == len(want)
    pairs = zip(lines, want, strict=True)
    assert [{key: line.get(key) for key in fields} for line, fields in pairs] == want


def test_an_empty_findings_file_without_vulnerabilities(trivy):
    result = trivy.scan("block", findings=True)

    assert result.returncode == 0, result.output
    assert trivy.findings.read_text() == ""


@pytest.mark.parametrize(
    "url",
    [
        "http://example.invalid/cve",
        "https://example.invalid/a|b",
        "https://example.invalid/a b",
        "https://example.invalid/<script>",
        "https://example.invalid/" + "a" * 300,
    ],
)
def test_the_findings_file_drops_a_link_that_is_not_plain_https(trivy, url):
    trivy.report(report([vuln("CVE-1", "HIGH", fixed="1.1", PrimaryURL=url)]))

    result = trivy.scan("report", findings=True)

    assert result.returncode == 0, result.output
    assert json.loads(trivy.findings.read_text())["url"] == ""


def test_the_findings_file_clips_long_and_odd_values(trivy):
    trivy.report(
        report(
            [
                vuln(
                    "CVE-" + "9" * 100,
                    "HIGH",
                    fixed="1.1",
                    PkgName="bad\tname\nhere",
                    InstalledVersion="é" * 150,
                )
            ]
        )
    )

    result = trivy.scan("report", findings=True)

    assert result.returncode == 0, result.output
    line = json.loads(trivy.findings.read_text())
    assert line["id"] == "CVE-" + "9" * 73 + "..."
    assert line["package"] == "bad name here"
    assert line["version"].endswith("...")
    assert len(line["version"].encode()) <= 200
    assert line["version"] == "é" * 98 + "..."


def test_a_findings_file_that_cannot_be_written(trivy, tmp_path):
    findings = tmp_path / "no-such-directory" / "findings.jsonl"

    result = trivy.run("report", str(trivy.pins), str(findings))

    assert result.returncode == 2
    assert f"writing the findings to {findings} failed" in result.stdout


def test_a_temporary_directory_that_cannot_be_made(trivy, tmp_path):
    result = trivy.scan(env={"RUNNER_TEMP": str(tmp_path / "missing")})

    assert result.returncode == 2
    assert "creating a temporary directory failed" in result.stdout
    assert not (trivy.out / "args").exists()


@pytest.mark.parametrize(
    "args",
    [
        pytest.param((), id="no argument"),
        pytest.param(("block",), id="one argument"),
        pytest.param(("block", "a", "b", "c"), id="four arguments"),
        pytest.param(("warn", "requirements.txt"), id="another policy"),
    ],
)
def test_wrong_arguments(trivy, args):
    result = trivy.run(*args)

    assert result.returncode == 2
    assert last_line(result.stdout) == "trivy: DID NOT RUN"
    assert not (trivy.out / "args").exists()


def test_a_target_that_is_not_a_file(trivy, tmp_path):
    result = trivy.run("block", str(tmp_path / "missing.txt"))

    assert result.returncode == 2
    assert "missing.txt is not a file" in result.stdout


def test_a_target_without_a_pin(trivy):
    trivy.pins.write_text("# no pins\npkg0>=1.0\n")

    result = trivy.scan()

    assert result.returncode == 2
    assert "has no name==version pin" in result.stdout
    assert not (trivy.out / "args").exists()


def test_an_image_target(trivy):
    trivy.report(report(packages=5, os_family="wolfi"))

    result = trivy.run("block", "image:example.invalid/opal-server:latest")

    assert result.returncode == 0, result.output
    assert (
        "trivy: example.invalid/opal-server:latest (wolfi): 5 packages" in result.stdout
    )
    assert trivy.args[0] == "image"
    assert trivy.args[-1] == "example.invalid/opal-server:latest"
    assert "linux/amd64" in trivy.args


def test_an_image_target_without_packages(trivy):
    trivy.report(report(packages=0, root_package=True))

    result = trivy.run("report", "image:example.invalid/opal-server:latest")

    assert result.returncode == 2
    assert (
        "Trivy listed no package in example.invalid/opal-server:latest" in result.stdout
    )


def test_an_image_target_without_an_image(trivy):
    result = trivy.run("block", "image:")

    assert result.returncode == 2
    assert 'the target "image:" names no image' in result.stdout


def test_an_archive_target(trivy, tmp_path):
    archive = tmp_path / "opal-server.tar"
    archive.write_bytes(b"an image archive")
    trivy.report(report(packages=5, os_family="wolfi"))

    result = trivy.run("report", f"archive:{archive}")

    assert result.returncode == 0, result.output
    assert f"trivy: {archive} (wolfi): 5 packages" in result.stdout
    assert trivy.args[0] == "image"
    assert trivy.args[-2:] == ["--input", str(archive)]


def test_an_archive_target_without_packages(trivy, tmp_path):
    archive = tmp_path / "opal-server.tar"
    archive.write_bytes(b"an image archive")
    trivy.report(report(packages=0))

    result = trivy.run("report", f"archive:{archive}")

    assert result.returncode == 2
    assert f"Trivy listed no package in {archive}" in result.stdout


def test_an_archive_target_that_is_not_a_file(trivy, tmp_path):
    result = trivy.run("block", f"archive:{tmp_path / 'missing.tar'}")

    assert result.returncode == 2
    assert f"{tmp_path / 'missing.tar'} is not a file" in result.stdout
    assert not (trivy.out / "args").exists()


def test_trivy_variables_and_files_cannot_change_the_scan(trivy):
    (trivy.repo.root / "trivy.yaml").write_text("severity: [LOW]\n")
    (trivy.repo.root / ".trivyignore").write_text("CVE-1\n")

    result = trivy.scan(env={"TRIVY_SEVERITY": "LOW", "TRIVY_IGNOREFILE": "/dev/null"})

    assert result.returncode == 0, result.output
    assert (trivy.out / "env").read_text() == ""
    cwd = (trivy.out / "cwd").read_text().splitlines()
    assert cwd[1:] == [], "Trivy runs in an empty directory"
    assert Path(cwd[0]).resolve() != trivy.repo.root.resolve()


def test_jq_is_missing(trivy):
    result = trivy.scan(path=trivy.repo.path_with_only("bash"))

    assert result.returncode == 2
    assert "jq is not installed" in result.stdout


@pytest.mark.parametrize("family", [None, ""])
@pytest.mark.parametrize("kind", ["image", "archive"])
def test_an_image_whose_os_trivy_did_not_find_did_not_run(
    trivy, tmp_path, kind, family
):
    archive = tmp_path / "image.tar"
    archive.write_bytes(b"an image archive")
    target = f"archive:{archive}" if kind == "archive" else "image:example.invalid/x:1"
    trivy.report(report(packages=5, os_family=family))

    result = trivy.run("report", target)

    assert result.returncode == 2
    assert "Trivy found no OS in" in result.stdout
