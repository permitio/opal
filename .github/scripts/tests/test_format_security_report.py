"""Tests for .github/scripts/format_security_report.py, the security scan's
report.

Each test writes the results that security-scan.sh leaves for its sources (``<name>.exit``,
``.state``, ``.findings``, ``.out``) into a temporary directory, renders the report and checks the
Slack message, the job summary and the headline.
"""

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "format_security_report.py"
SPEC = importlib.util.spec_from_file_location("format_security_report", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
report = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = report
SPEC.loader.exec_module(report)

RUN_URL = "https://github.com/permitio/opal/actions/runs/1"
ALL_SOURCES = list(report.SOURCES)


def vuln(
    cve: str,
    package: str = "pyjwt",
    version: str = "2.13.0",
    severity: str = "high",
    **extra: object,
) -> dict:
    """A finding line as trivy.sh writes it."""
    entry = {
        "id": cve,
        "package": package,
        "version": version,
        "fix": "2.14.0",
        "severity": severity,
        "title": f"{package} is broken",
        "score": None,
        "aliases": [],
        "url": f"https://avd.aquasec.com/nvd/{cve.lower()}",
    }
    entry.update(extra)
    return entry


def write_source(
    results: Path,
    name: str,
    code: int,
    state: str = "",
    findings: list[dict] | None = None,
    out: str = "",
) -> None:
    """Write one source's result files the way security-scan.sh does."""
    (results / f"{name}.exit").write_text(f"{code}\n")
    (results / f"{name}.out").write_text(out)
    if state:
        (results / f"{name}.state").write_text(state + "\n")
    if findings is not None:
        lines = "".join(json.dumps(f) + "\n" for f in findings)
        (results / f"{name}.findings").write_text(lines)


@pytest.fixture
def results(tmp_path: Path) -> Path:
    """A results directory in which every source completed clean."""
    directory = tmp_path / "results"
    directory.mkdir()
    for name in ALL_SOURCES:
        state = {
            "pypi-latest": "opal-client==0.9.9 opal-server==0.9.9",
            "history-secrets": "history: 3 findings, 3 accepted, 0 new",
            "verified-secrets": "TruffleHog verified secrets: 0",
        }.get(name, "")
        write_source(directory, name, 0, state=state, findings=[])
    return directory


def build(results: Path, names: list[str] | None = None) -> Any:
    """Render the report of every source, or of the named ones."""
    return report.build("permitio/opal", RUN_URL, results, names or ALL_SOURCES)


def test_all_clean_reads_clean_and_lists_nothing(results: Path) -> None:
    rendered = build(results)
    assert rendered.headline == "no high/critical vulnerabilities found"
    assert rendered.slack.startswith(
        ":white_check_mark: *permitio/opal: no high/critical vulnerabilities found*"
    )
    assert "*High / critical*" not in rendered.slack
    assert "• *Trivy* (`opal-server:latest`): clean" in rendered.slack
    assert (
        "• *gitleaks* (`git history`): 3 findings, 3 accepted, 0 new" in rendered.slack
    )
    assert (
        "• *TruffleHog* (`git history, verified only`): none verified" in rendered.slack
    )
    assert rendered.slack.endswith(f"<{RUN_URL}|Workflow run>")


def test_the_pypi_source_is_named_by_the_versions_it_scanned(results: Path) -> None:
    assert (
        "*Trivy* (`opal-client==0.9.9 opal-server==0.9.9`): clean"
        in build(results).slack
    )


def test_same_cve_from_several_sources_is_one_line_naming_all(results: Path) -> None:
    for name in ("image-opal-server", "image-opal-client", "floor"):
        write_source(
            results, name, 1, findings=[vuln("CVE-2026-1", severity="critical")]
        )
    rendered = build(results)
    lines = [line for line in rendered.slack.splitlines() if "CVE-2026-1" in line]
    assert len(lines) == 1
    assert lines[0].endswith("_(server image, client image, floor)_")
    assert rendered.headline == "1 high/critical vulnerability found"


def test_a_cve_in_several_packages_names_every_package(results: Path) -> None:
    write_source(
        results,
        "image-opal-server",
        1,
        findings=[
            vuln("CVE-2026-2", package="perl", version="5.36"),
            vuln("CVE-2026-2", package="perl-base", version="5.36"),
        ],
    )
    assert "`perl@5.36, perl-base@5.36`" in build(results).slack


def test_a_dependabot_alert_merges_into_the_trivy_finding_by_alias(
    results: Path,
) -> None:
    write_source(results, "image-opal-server", 1, findings=[vuln("CVE-2026-3")])
    alert = vuln("GHSA-aaaa-bbbb-cccc", ecosystem="pip", aliases=["CVE-2026-3"])
    alert["url"] = "https://github.com/advisories/GHSA-aaaa-bbbb-cccc"
    write_source(
        results, "dependabot-alerts", 1, state="1 open alerts", findings=[alert]
    )
    rendered = build(results)
    lines = [line for line in rendered.slack.splitlines() if "CVE-2026-3" in line]
    assert len(lines) == 1
    assert "`pyjwt@2.13.0, pyjwt (pip)`" in lines[0]
    assert lines[0].endswith("_(server image, Dependabot)_")


def test_the_worst_severity_and_the_highest_score_win_on_merge(results: Path) -> None:
    write_source(
        results, "floor", 1, findings=[vuln("CVE-2026-4", severity="high", score=7.5)]
    )
    write_source(
        results,
        "ceiling",
        1,
        findings=[vuln("CVE-2026-4", severity="critical", score=9.8)],
    )
    assert "• *critical 9.8* — `pyjwt@2.13.0`" in build(results).slack


def test_findings_are_ordered_by_severity_then_score(results: Path) -> None:
    write_source(
        results,
        "floor",
        1,
        findings=[
            vuln("CVE-2026-10", severity="high", score=7.1),
            vuln("CVE-2026-11", severity="critical", score=9.1),
            vuln("CVE-2026-12", severity="high", score=8.8),
        ],
    )
    slack = build(results).slack
    order = [slack.index(cve) for cve in ("CVE-2026-11", "CVE-2026-12", "CVE-2026-10")]
    assert order == sorted(order)


def test_medium_and_low_are_counted_but_not_listed(results: Path) -> None:
    write_source(
        results,
        "floor",
        1,
        state="77 pinned packages",
        findings=[
            vuln("CVE-2026-5", severity="medium"),
            vuln("CVE-2026-6", severity="low"),
        ],
    )
    rendered = build(results)
    assert (
        "(`oldest allowed versions`): 1 medium, 1 low · 77 pinned packages"
        in rendered.slack
    )
    assert "CVE-2026-5" not in rendered.slack
    assert rendered.headline == "no high/critical vulnerabilities found"


def test_a_finding_without_severity_takes_it_from_its_score(results: Path) -> None:
    write_source(
        results, "floor", 1, findings=[vuln("CVE-2026-7", severity="", score=9.3)]
    )
    assert "• *critical 9.3*" in build(results).slack


def test_a_finding_without_severity_or_score_is_listed_as_unscored(
    results: Path,
) -> None:
    write_source(
        results, "floor", 1, findings=[vuln("CVE-2026-8", severity="", score=None)]
    )
    rendered = build(results)
    assert rendered.headline == "no high/critical vulnerabilities, 1 unscored to triage"
    assert "*Unscored* (no severity or CVSS score, triage by hand)" in rendered.slack
    assert rendered.slack.startswith(":large_yellow_circle:")


def test_no_fix_is_said_out_loud(results: Path) -> None:
    write_source(results, "floor", 1, findings=[vuln("CVE-2026-9", fix="")])
    assert "— no fix released _(floor)_" in build(results).slack


def test_a_source_without_results_is_incomplete_never_clean(results: Path) -> None:
    (results / "image-opal-client.exit").unlink()
    rendered = build(results)
    assert rendered.headline == "security scan incomplete"
    assert rendered.slack.startswith(
        ":warning: *permitio/opal: security scan incomplete*"
    )
    assert (
        "(`opal-client:latest`): :warning: did not complete: it has no result"
        in rendered.slack
    )


def test_a_source_that_did_not_complete_gives_the_last_cause_in_its_log(
    results: Path,
) -> None:
    log = (
        "security-scan: verified-secrets\n"
        "security-scan: trufflehog exited 1: failed to stat .git\n"
        "trivy: DID NOT RUN\n"
    )
    write_source(results, "verified-secrets", 2, out=log)
    rendered = build(results)
    assert (
        "did not complete: trufflehog exited 1: failed to stat .git" in rendered.slack
    )
    assert (
        "| TruffleHog | git history, verified only | did not complete: trufflehog"
        in (rendered.summary)
    )


def test_findings_and_an_incomplete_source_lead_with_the_count(results: Path) -> None:
    write_source(results, "floor", 1, findings=[vuln("CVE-2026-13")])
    write_source(results, "ceiling", 2, out="security-scan: vuln.sh --prepare failed\n")
    slack = build(results).slack
    assert slack.startswith(
        ":rotating_light: *permitio/opal: 1 high/critical vulnerability found*"
    )
    assert ":warning: Trivy (newest allowed versions) did not complete" in slack


@pytest.mark.parametrize(
    "content",
    ["not json\n", "[1, 2]\n", '"a string"\n'],
    ids=["not-json", "a-list", "a-string"],
)
def test_a_findings_line_that_is_not_an_object_is_incomplete(
    results: Path, content: str
) -> None:
    write_source(results, "floor", 1)
    (results / "floor.findings").write_text(content)
    assert (
        "did not complete: line 1 of its findings is not a JSON object"
        in build(results).slack
    )


def test_findings_reported_but_none_listed_is_incomplete(results: Path) -> None:
    write_source(results, "floor", 1, findings=[])
    assert (
        "did not complete: it reported findings but listed none" in build(results).slack
    )


def test_an_exit_code_outside_the_contract_is_incomplete(results: Path) -> None:
    (results / "floor.exit").write_text("7\n")
    assert "did not complete: its exit code '7' is not 0 to 3" in build(results).slack


def test_a_skipped_source_says_why(results: Path) -> None:
    write_source(results, "dependabot-alerts", 3, state="no Dependabot alerts token")
    rendered = build(results)
    assert "(`all ecosystems`): skipped: no Dependabot alerts token" in rendered.slack
    assert rendered.headline == "no high/critical vulnerabilities found"


def test_a_verified_secret_leads_the_report(results: Path) -> None:
    secret = {
        "id": "AWS",
        "package": "config.py:3",
        "version": "abc123",
        "fix": "revoke it now: TruffleHog verified that it works (AKIA...)",
    }
    write_source(results, "verified-secrets", 1, findings=[secret])
    write_source(results, "floor", 1, findings=[vuln("CVE-2026-14")])
    rendered = build(results)
    assert rendered.headline == "TruffleHog verified 1 secret that works, revoke now"
    assert "• *verified* — `config.py:3` — AWS — commit `abc123` — revoke it now" in (
        rendered.slack
    )
    assert "config.py" not in rendered.summary


def test_new_history_secrets_are_listed_in_slack_and_counted_in_the_summary(
    results: Path,
) -> None:
    secret = {
        "id": "generic-api-key",
        "package": "a.py:1",
        "version": "abc",
        "fix": "revoke it",
    }
    write_source(
        results,
        "history-secrets",
        1,
        state="history: 1 findings, 0 accepted, 1 new",
        findings=[secret],
    )
    rendered = build(results)
    assert rendered.headline == "1 new secret in the git history found"
    assert (
        "• *new* — `a.py:1` — generic-api-key — commit `abc` — revoke it"
        in rendered.slack
    )
    assert (
        "| gitleaks | git history | 1 findings, 0 accepted, 1 new |" in rendered.summary
    )
    assert "a.py" not in rendered.summary


def test_dependabot_alerts_stay_out_of_the_public_summary(results: Path) -> None:
    alert = vuln("GHSA-dddd-eeee-ffff", package="private-pkg", ecosystem="pip")
    write_source(
        results, "dependabot-alerts", 1, state="1 open alerts", findings=[alert]
    )
    write_source(
        results, "floor", 1, findings=[vuln("CVE-2026-15", package="public-pkg")]
    )
    rendered = build(results)
    assert "private-pkg" in rendered.slack
    assert "private-pkg" not in rendered.summary
    assert "public-pkg@2.13.0" in rendered.summary


def test_untrusted_text_cannot_ping_link_or_break_lines(results: Path) -> None:
    evil = vuln(
        "CVE-2026-16",
        package="pkg`<!channel>",
        title="<https://evil.example|click> & *bold*\n:: injected",
        url="https://evil.example/x|y",
    )
    write_source(results, "floor", 1, findings=[evil])
    rendered = build(results)
    line = next(x for x in rendered.slack.splitlines() if "CVE-2026-16" in x)
    assert "<!channel>" not in rendered.slack
    assert "<https://evil.example" not in rendered.slack
    assert "&lt;https://evil.example¦click&gt;" not in line
    assert "&lt;https://evil.example|click&gt; &amp; *bold* :: injected" in line
    assert "`pkg'&lt;!channel&gt;@2.13.0`" in line
    assert "CVE-2026-16 —" in line
    assert all(not x.startswith("::") for x in rendered.summary.splitlines())


def test_the_summary_escapes_markdown_in_untrusted_text(results: Path) -> None:
    evil = vuln(
        "CVE-2026-17", package="a|b", title="[link](https://evil.example) <b>`x`</b>"
    )
    write_source(results, "floor", 1, findings=[evil])
    summary = build(results).summary
    line = next(x for x in summary.splitlines() if "CVE-2026-17" in x)
    assert "a\\|b@2.13.0" in line
    assert "\\[link\\](https://evil.example) &lt;b&gt;\\`x\\`&lt;/b&gt;" in line
    assert "[CVE-2026-17](https://avd.aquasec.com/nvd/cve-2026-17)" in line


def test_listing_is_capped(results: Path) -> None:
    findings = [vuln(f"CVE-2026-{100 + n}") for n in range(report.MAX_LISTED + 4)]
    write_source(results, "floor", 1, findings=findings)
    slack = build(results).slack
    listed = [x for x in slack.splitlines() if x.startswith("• *high*")]
    assert len(listed) == report.MAX_LISTED
    assert "• …and 4 more (see the run)" in slack


def test_a_run_url_that_is_not_https_is_not_linked(results: Path) -> None:
    rendered = report.build("permitio/opal", "", results, ALL_SOURCES)
    assert "Workflow run" not in rendered.slack


@pytest.mark.parametrize(
    ("word", "score", "expected"),
    [
        ("CRITICAL", None, "critical"),
        ("moderate", None, "medium"),
        ("", 9.0, "critical"),
        ("unknown", 7.0, "high"),
        ("", 4.0, "medium"),
        ("", 0.1, "low"),
        ("", None, "unscored"),
        ("", 0, "unscored"),
    ],
)
def test_normalise_severity(word: str, score: float | None, expected: str) -> None:
    assert report.normalise_severity(word, score) == expected


def test_the_cli_writes_the_message_the_summary_and_the_headline(
    results: Path, tmp_path: Path
) -> None:
    out = {
        name: tmp_path / name for name in ("slack.txt", "summary.md", "headline.txt")
    }
    code = report.main(
        [
            "--repo=permitio/opal",
            f"--run-url={RUN_URL}",
            f"--results={results}",
            *(f"--source={name}" for name in ALL_SOURCES),
            f"--slack-out={out['slack.txt']}",
            f"--summary-out={out['summary.md']}",
            f"--headline-out={out['headline.txt']}",
        ]
    )
    assert code == 0
    assert out["headline.txt"].read_text() == "no high/critical vulnerabilities found\n"
    assert out["slack.txt"].read_text().startswith(":white_check_mark:")
    assert out["summary.md"].read_text().startswith("## Security scan\n")


def test_the_cli_refuses_a_missing_results_directory(tmp_path: Path) -> None:
    code = report.main(
        [
            "--repo=permitio/opal",
            f"--results={tmp_path / 'missing'}",
            "--source=floor",
            f"--slack-out={tmp_path / 's'}",
            f"--summary-out={tmp_path / 'm'}",
        ]
    )
    assert code == 2


def test_the_cli_refuses_an_unknown_source(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as raised:
        report.main(
            [
                "--repo=permitio/opal",
                f"--results={tmp_path}",
                "--source=nope",
                f"--slack-out={tmp_path / 's'}",
                f"--summary-out={tmp_path / 'm'}",
            ]
        )
    assert raised.value.code == 2


def test_the_cli_fails_when_it_cannot_write(results: Path, tmp_path: Path) -> None:
    code = report.main(
        [
            "--repo=permitio/opal",
            f"--results={results}",
            "--source=floor",
            f"--slack-out={tmp_path / 'missing-dir' / 's'}",
            f"--summary-out={tmp_path / 'm'}",
        ]
    )
    assert code == 2
