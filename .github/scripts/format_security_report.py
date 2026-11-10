#!/usr/bin/env python3
"""Build the security scan's Slack message and job summary from its sources'
results.

security-scan.sh runs each source and leaves its results in one directory, under the source's
name: ``<name>.exit`` (0 clean, 1 findings, 2 did not complete, 3 skipped), ``<name>.state`` (one
line about what it scanned), ``<name>.findings`` (one JSON object per line) and ``<name>.out``
(its log). This script reads them and renders the report in the layout of permitio/PDP's
scheduled security scan: a headline, one line per source, the secrets that need action, then the
high and critical vulnerabilities with package, advisory link and fix. The same advisory seen by
several sources is one line that names every source that saw it.

A source with no result, or one that did not complete, is shown as "did not complete" with the
last line of its log as the reason, and the report never reads as clean while one is missing.
The Dependabot alerts and the secrets are private findings: the Slack message lists them, and the
job summary, which is public, counts them only.

Every value from a scanner or from GitHub is untrusted and is escaped here, once: notify.sh sends
the Slack message as it is. The script exits 0 once it has written both files, and 2 on a usage
error or a file it cannot write.
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "unscored": 4}
SEVERE = ("critical", "high")
MAX_LISTED = 15
MAX_SUMMARY_LISTED = 30
MAX_TITLE = 120
MAX_REASON = 300

_HTTPS_URL = re.compile(r"^https://[^\s<>|()\[\]\"]+$")
# The name a script of .github/scripts starts each line of its log with.
_SCRIPT_PREFIX = re.compile(r"^(security-scan|trivy|vuln|fetch-tool|notify): ")
# Whitespace and control characters, which every untrusted value has collapsed into one space, so
# a value can never start a line of its own in the log, the summary or Slack.
_WHITESPACE = re.compile(r"[\s\x00-\x1f\x7f]+")


@dataclass(frozen=True)
class SourceInfo:
    """How the report names one source of security-scan.sh.

    Attributes:
        scanner: The tool that ran, shown in bold.
        scope: What it scanned, shown in a code span; the state replaces it when ``scope_from_state``.
        label: The short name a finding line gives in its list of sources.
        kind: ``vulns`` for Trivy, ``alerts`` for Dependabot, ``secrets`` for gitleaks and
            ``verified`` for TruffleHog.
        private: Its findings are listed in Slack only, never in the public job summary.
        scope_from_state: Its state names what it scanned, such as the PyPI versions.
    """

    scanner: str
    scope: str
    label: str
    kind: str
    private: bool = False
    scope_from_state: bool = False


SOURCES = {
    "image-opal-server": SourceInfo(
        "Trivy", "opal-server:latest", "server image", "vulns"
    ),
    "image-opal-client": SourceInfo(
        "Trivy", "opal-client:latest", "client image", "vulns"
    ),
    "pypi-latest": SourceInfo("Trivy", "PyPI", "PyPI", "vulns", scope_from_state=True),
    "floor": SourceInfo("Trivy", "oldest allowed versions", "floor", "vulns"),
    "ceiling": SourceInfo("Trivy", "newest allowed versions", "ceiling", "vulns"),
    "dependabot-alerts": SourceInfo(
        "Dependabot alerts", "all ecosystems", "Dependabot", "alerts", private=True
    ),
    "history-secrets": SourceInfo(
        "gitleaks", "git history", "gitleaks", "secrets", private=True
    ),
    "verified-secrets": SourceInfo(
        "TruffleHog",
        "git history, verified only",
        "TruffleHog",
        "verified",
        private=True,
    ),
}


@dataclass
class Finding:
    """One advisory affecting one or more packages, as seen by one or more
    sources."""

    id: str
    severity: str
    score: float | None
    title: str
    url: str
    remediation: str
    packages: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    aliases: set[str] = field(default_factory=set)
    private: bool = False


@dataclass
class Secret:
    """A secret in the git history: a new gitleaks finding or one TruffleHog verified."""

    rule: str
    where: str
    commit: str
    action: str
    verified: bool


@dataclass
class Source:
    """One source's result: its findings, or why it has none to give."""

    name: str
    info: SourceInfo
    scope: str
    exit_code: int
    state: str = ""
    reason: str = ""
    findings: list[Finding] = field(default_factory=list)
    secrets: list[Secret] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        """Whether the source ran to the end or was skipped on purpose."""
        return self.exit_code in (0, 1, 3)


class UsageError(Exception):
    """The command line, or a file the script must write, is wrong."""


def flatten(text: str) -> str:
    """Collapse whitespace and control characters into single spaces."""
    return _WHITESPACE.sub(" ", text).strip()


def escape_slack(text: str) -> str:
    """Flatten text and escape it for Slack mrkdwn: ``&`` first, then ``<`` and ``>``."""
    return flatten(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def escape_markdown(text: str) -> str:
    """Flatten text and escape it for GitHub Markdown, so it opens no link,
    tag, cell or code."""
    text = flatten(text).replace("\\", "\\\\")
    for char in "`*_[]|":
        text = text.replace(char, f"\\{char}")
    return text.replace("<", "&lt;").replace(">", "&gt;")


def code_span(text: str) -> str:
    """Text inside backticks, with any backtick in it turned into a quote."""
    quoted = text.replace("`", "'")
    return f"`{quoted}`"


def truncate(text: str, limit: int = MAX_TITLE) -> str:
    """Collapse whitespace and cut to ``limit`` characters, marking the cut."""
    flat = flatten(text)
    return flat if len(flat) <= limit else f"{flat[: limit - 1]}…"


def slack_link(url: str, label: str) -> str:
    """A Slack link for a plain https URL, or the escaped label alone for
    anything else."""
    safe_label = escape_slack(label).replace("|", "¦")
    return f"<{url}|{safe_label}>" if _HTTPS_URL.match(url) else safe_label


def markdown_link(url: str, label: str) -> str:
    """A Markdown link for a plain https URL, or the escaped label alone for
    anything else."""
    safe_label = escape_markdown(label)
    return f"[{safe_label}]({url})" if _HTTPS_URL.match(url) else safe_label


def normalise_severity(value: object, score: float | None = None) -> str:
    """Map a scanner's severity word to critical, high, medium, low or
    unscored.

    Args:
        value: The scanner's word; ``moderate`` is GitHub's word for medium.
        score: The CVSS base score, which decides when the word is missing or unknown.

    Returns:
        One of the keys of ``SEVERITY_ORDER``.
    """
    word = str(value or "").strip().lower()
    if word == "moderate":
        word = "medium"
    if word in SEVERITY_ORDER and word != "unscored":
        return word
    if score is None or score <= 0:
        return "unscored"
    for floor, name in ((9.0, "critical"), (7.0, "high"), (4.0, "medium")):
        if score >= floor:
            return name
    return "low"


def _score(value: object) -> float | None:
    """A positive CVSS score, or None for anything else."""
    if isinstance(value, bool):
        return None
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _text(value: object) -> str:
    """A scanner value as text: a string as it is, anything else empty."""
    return value if isinstance(value, str) else ""


def _read_text(path: Path) -> str | None:
    """The file's text, or None when it does not exist or cannot be read."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _reason(log: str | None) -> str:
    """Why a source did not complete: the last line of its log that names a cause."""
    if log is None:
        return "it left no log"
    lines = [line.strip() for line in log.splitlines() if line.strip()]
    causes = [line for line in lines if not line.endswith("DID NOT RUN")]
    if not causes:
        return "its log names no cause"
    return truncate(_SCRIPT_PREFIX.sub("", causes[-1]), MAX_REASON)


def _remediation(fixed: str) -> str:
    return f"fix: {fixed}" if fixed else "no fix released"


def _vulnerability(entry: dict, info: SourceInfo) -> Finding:
    """A Trivy finding or a Dependabot alert from one line of a findings
    file."""
    score = _score(entry.get("score"))
    package = _text(entry.get("package")) or "?"
    version = _text(entry.get("version"))
    if info.kind == "alerts":
        ecosystem = _text(entry.get("ecosystem"))
        shown = f"{package} ({ecosystem})" if ecosystem else package
    else:
        shown = f"{package}@{version}" if version else package
    aliases = entry.get("aliases")
    return Finding(
        id=_text(entry.get("id")) or "?",
        severity=normalise_severity(entry.get("severity"), score),
        score=score,
        title=_text(entry.get("title")),
        url=_text(entry.get("url")),
        remediation=_remediation(_text(entry.get("fix"))),
        packages=[shown],
        sources=[info.label],
        aliases={a for a in aliases if isinstance(a, str) and a}
        if isinstance(aliases, list)
        else set(),
        private=info.private,
    )


def _secret(entry: dict, info: SourceInfo) -> Secret:
    """A secret from one line of a gitleaks or TruffleHog findings file."""
    return Secret(
        rule=_text(entry.get("id")) or "?",
        where=_text(entry.get("package")) or "?",
        commit=_text(entry.get("version")),
        action=_text(entry.get("fix")),
        verified=info.kind == "verified",
    )


def read_source(results: Path, name: str) -> Source:
    """One source's result from the results directory.

    A missing or unreadable exit file, an exit code that is not 0 to 3, or a findings file that
    is not JSON objects makes the source incomplete, so a broken result never reads as clean.

    Args:
        results: The directory security-scan.sh wrote the results to.
        name: The source's name, a key of ``SOURCES``.

    Returns:
        The source, with its findings or secrets, or with the reason it did not complete.
    """
    info = SOURCES[name]
    raw_exit = _read_text(results / f"{name}.exit")
    try:
        exit_code = int((raw_exit or "").strip())
    except ValueError:
        exit_code = -1
    state = ((_read_text(results / f"{name}.state") or "").splitlines() or [""])[
        0
    ].strip()
    scope = state if info.scope_from_state and state else info.scope
    source = Source(name=name, info=info, scope=scope, exit_code=exit_code, state=state)
    if raw_exit is None:
        source.exit_code, source.reason = 2, "it has no result"
        return source
    if exit_code not in (0, 1, 2, 3):
        source.exit_code, source.reason = (
            2,
            f"its exit code {raw_exit.strip()!r} is not 0 to 3",
        )
        return source
    if exit_code == 2:
        source.reason = _reason(_read_text(results / f"{name}.out"))
        return source
    findings = _read_text(results / f"{name}.findings")
    for number, line in enumerate((findings or "").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            entry = None
        if not isinstance(entry, dict):
            source.findings, source.secrets = [], []
            source.exit_code = 2
            source.reason = f"line {number} of its findings is not a JSON object"
            return source
        if info.kind in ("secrets", "verified"):
            source.secrets.append(_secret(entry, info))
        else:
            source.findings.append(_vulnerability(entry, info))
    if exit_code == 1 and not source.findings and not source.secrets:
        source.exit_code, source.reason = 2, "it reported findings but listed none"
    return source


def merge(sources: list[Source]) -> list[Finding]:
    """One finding per advisory across every source, keeping the worst severity
    seen.

    Two findings are the same advisory when their IDs or aliases meet, such as a Dependabot alert
    by its GHSA ID and a Trivy finding by its CVE ID. The remediation is the first one that names
    a fix. A finding is private when any source that saw it is private.

    Args:
        sources: The sources, in report order.

    Returns:
        The merged findings, the most severe first, then by score and ID.
    """
    by_id: dict[str, Finding] = {}
    merged: list[Finding] = []
    for finding in (f for s in sources for f in s.findings):
        keys = {finding.id, *finding.aliases} - {"", "?"}
        existing = next((by_id[k] for k in keys if k in by_id), None)
        if existing is None:
            existing = replace(finding, packages=[], sources=[], aliases=set())
            merged.append(existing)
        elif SEVERITY_ORDER[finding.severity] < SEVERITY_ORDER[existing.severity]:
            existing.severity, existing.score = finding.severity, finding.score
        elif finding.severity == existing.severity and (finding.score or 0) > (
            existing.score or 0
        ):
            existing.score = finding.score
        if existing.remediation == "no fix released":
            existing.remediation = finding.remediation
        existing.title = existing.title or finding.title
        existing.url = existing.url or finding.url
        existing.private = existing.private or finding.private
        existing.aliases |= keys
        existing.packages += [p for p in finding.packages if p not in existing.packages]
        existing.sources += [s for s in finding.sources if s not in existing.sources]
        for key in keys:
            by_id[key] = existing
    return sorted(
        merged, key=lambda f: (SEVERITY_ORDER[f.severity], -(f.score or 0), f.id)
    )


def count_line(findings: list[Finding]) -> str:
    """The findings counted by severity, the most severe first, or
    ``clean``."""
    counts = {s: sum(1 for f in findings if f.severity == s) for s in SEVERITY_ORDER}
    parts = [f"{n} {s}" for s, n in counts.items() if n]
    return ", ".join(parts) if parts else "clean"


def result_text(source: Source) -> str:
    """A source's result in plain words, without its name; untrusted parts are
    not escaped."""
    if not source.complete:
        return f"did not complete: {source.reason}"
    if source.exit_code == 3:
        return f"skipped: {source.state}" if source.state else "skipped"
    if source.info.kind == "secrets":
        return source.state.removeprefix("history: ") or (
            f"{len(source.secrets)} new" if source.secrets else "clean"
        )
    if source.info.kind == "verified":
        return f"{len(source.secrets)} verified" if source.secrets else "none verified"
    text = count_line(source.findings)
    if (
        source.state
        and not source.info.scope_from_state
        and source.info.kind == "vulns"
    ):
        if source.name not in ("image-opal-server", "image-opal-client"):
            text += f" · {source.state}"
    return text


def headline(sources: list[Source], findings: list[Finding]) -> tuple[str, str]:
    """The report's headline and its emoji.

    Returns:
        The headline in plain words, and the Slack emoji that goes before it.
    """
    verified = sum(len(s.secrets) for s in sources if s.info.kind == "verified")
    new_secrets = sum(len(s.secrets) for s in sources if s.info.kind == "secrets")
    severe = sum(1 for f in findings if f.severity in SEVERE)
    unscored = sum(1 for f in findings if f.severity == "unscored")
    incomplete = any(not s.complete for s in sources)
    if verified:
        noun = "secret that works" if verified == 1 else "secrets that work"
        return f"TruffleHog verified {verified} {noun}, revoke now", ":rotating_light:"
    parts = []
    if severe:
        noun = "vulnerability" if severe == 1 else "vulnerabilities"
        parts.append(f"{severe} high/critical {noun}")
    if new_secrets:
        noun = "secret" if new_secrets == 1 else "secrets"
        parts.append(f"{new_secrets} new {noun} in the git history")
    if parts:
        return " and ".join(parts) + " found", ":rotating_light:"
    if incomplete:
        return "security scan incomplete", ":warning:"
    if unscored:
        return f"no high/critical vulnerabilities, {unscored} unscored to triage", (
            ":large_yellow_circle:"
        )
    return "no high/critical vulnerabilities found", ":white_check_mark:"


def incomplete_names(sources: list[Source]) -> list[str]:
    """The names of the sources that did not complete, as the report shows
    them."""
    return [f"{s.info.scanner} ({s.scope})" for s in sources if not s.complete]


def slack_source_line(source: Source) -> str:
    label = f"*{escape_slack(source.info.scanner)}* ({code_span(escape_slack(source.scope))})"
    if not source.complete:
        return f"• {label}: :warning: did not complete: {escape_slack(source.reason)}"
    return f"• {label}: {escape_slack(result_text(source))}"


def slack_finding_line(finding: Finding) -> str:
    label = (
        finding.severity
        if finding.score is None
        else f"{finding.severity} {finding.score:.1f}"
    )
    pieces = [f"*{label}*", code_span(escape_slack(", ".join(finding.packages) or "?"))]
    if finding.title:
        pieces.append(escape_slack(truncate(finding.title)))
    pieces.append(slack_link(finding.url, finding.id))
    pieces.append(escape_slack(finding.remediation))
    sources = escape_slack(", ".join(finding.sources))
    return f"• {' — '.join(pieces)} _({sources})_"


def slack_secret_line(secret: Secret) -> str:
    label = "*verified*" if secret.verified else "*new*"
    pieces = [label, code_span(escape_slack(secret.where)), escape_slack(secret.rule)]
    if secret.commit:
        pieces.append(f"commit {code_span(escape_slack(secret.commit))}")
    if secret.action:
        pieces.append(escape_slack(truncate(secret.action, 200)))
    return f"• {' — '.join(pieces)}"


def _capped(lines: list[str], total: int, limit: int, more: str) -> list[str]:
    if total > limit:
        return [*lines[:limit], more.format(total - limit)]
    return lines


def render_slack(
    repo: str, run_url: str, sources: list[Source], findings: list[Finding]
) -> str:
    """The Slack message, every untrusted value escaped."""
    words, emoji = headline(sources, findings)
    body = [f"{emoji} *{escape_slack(repo)}: {escape_slack(words)}*"]
    missing = incomplete_names(sources)
    if missing and not words.startswith("security scan incomplete"):
        body.append(
            f":warning: {escape_slack(', '.join(missing))} did not complete, "
            "so the results are partial."
        )
    body += [
        "",
        "_Trivy and Dependabot: high and critical findings are listed, the rest are counted. "
        "gitleaks and TruffleHog: every secret that needs action is listed._",
        *(slack_source_line(s) for s in sources),
    ]
    secrets = [x for s in sources for x in s.secrets]
    secrets.sort(key=lambda x: not x.verified)
    if secrets:
        lines = [slack_secret_line(x) for x in secrets]
        body += [
            "",
            "*Secrets*",
            *_capped(lines, len(lines), MAX_LISTED, "• …and {} more"),
        ]
    severe = [f for f in findings if f.severity in SEVERE]
    unscored = [f for f in findings if f.severity == "unscored"]
    for title, listed in (
        ("*High / critical*", severe),
        ("*Unscored* (no severity or CVSS score, triage by hand)", unscored),
    ):
        if listed:
            lines = [slack_finding_line(f) for f in listed[:MAX_LISTED]]
            more = "• …and {} more (see the run)"
            body += ["", title, *_capped(lines, len(listed), MAX_LISTED, more)]
    if _HTTPS_URL.match(run_url):
        body += ["", slack_link(run_url, "Workflow run")]
    return "\n".join(body)


def summary_finding_line(finding: Finding) -> str:
    label = (
        finding.severity
        if finding.score is None
        else f"{finding.severity} {finding.score:.1f}"
    )
    packages = escape_markdown(", ".join(finding.packages) or "?")
    pieces = [f"**{label}**", packages]
    if finding.title:
        pieces.append(escape_markdown(truncate(finding.title)))
    pieces.append(markdown_link(finding.url, finding.id))
    pieces.append(escape_markdown(finding.remediation))
    return f"- {' · '.join(pieces)} ({escape_markdown(', '.join(finding.sources))})"


def render_summary(sources: list[Source], findings: list[Finding]) -> str:
    """The job summary in GitHub Markdown; it is public, so private findings
    are counted only."""
    words, _ = headline(sources, findings)
    body = ["## Security scan", "", escape_markdown(words), ""]
    missing = incomplete_names(sources)
    if missing and words != "security scan incomplete":
        body += [f"{escape_markdown(', '.join(missing))} did not complete.", ""]
    body += ["| Source | Scope | Result |", "|---|---|---|"]
    for source in sources:
        cells = (source.info.scanner, source.scope, result_text(source))
        body.append("| " + " | ".join(escape_markdown(c) for c in cells) + " |")
    body += [
        "",
        "The Dependabot alerts and the secrets are counted here and listed in Slack only.",
    ]
    public = [f for f in findings if f.severity in SEVERE and not f.private]
    if public:
        lines = [summary_finding_line(f) for f in public[:MAX_SUMMARY_LISTED]]
        more = "- …and {} more"
        body += [
            "",
            "### High / critical",
            "",
            *_capped(lines, len(public), MAX_SUMMARY_LISTED, more),
        ]
    return "\n".join(body)


@dataclass
class Report:
    """The rendered report."""

    slack: str
    summary: str
    headline: str


def build(repo: str, run_url: str, results: Path, names: list[str]) -> Report:
    """Read every named source's result and render the report.

    Args:
        repo: owner/name, shown in the headline.
        run_url: The workflow run's URL; the Slack message links it when it is an https URL.
        results: The directory security-scan.sh wrote the results to.
        names: The sources that should have run, in report order.

    Returns:
        The Slack message, the job summary and the plain headline.
    """
    sources = [read_source(results, name) for name in names]
    findings = merge(sources)
    words, _ = headline(sources, findings)
    return Report(
        slack=render_slack(repo, run_url, sources, findings),
        summary=render_summary(sources, findings),
        headline=words,
    )


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the security scan's Slack message and job summary."
    )
    parser.add_argument(
        "--repo", required=True, help="owner/name, shown in the headline"
    )
    parser.add_argument("--run-url", default="", help="the workflow run's URL")
    parser.add_argument(
        "--results", required=True, type=Path, help="the results directory"
    )
    parser.add_argument(
        "--source",
        action="append",
        required=True,
        choices=list(SOURCES),
        help="a source that should have run; once per source, in report order",
    )
    parser.add_argument(
        "--slack-out", required=True, type=Path, help="write the Slack message here"
    )
    parser.add_argument(
        "--summary-out", required=True, type=Path, help="write the job summary here"
    )
    parser.add_argument(
        "--headline-out", type=Path, help="write the plain headline here"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.results.is_dir():
        print(
            f"format_security_report: {args.results} is not a directory",
            file=sys.stderr,
        )
        return 2
    report = build(args.repo, args.run_url, args.results, args.source)
    outputs = [(args.slack_out, report.slack), (args.summary_out, report.summary)]
    if args.headline_out:
        outputs.append((args.headline_out, report.headline))
    for path, text in outputs:
        try:
            path.write_text(text + "\n", encoding="utf-8")
        except OSError as exc:
            print(
                f"format_security_report: writing {path} failed: {exc}", file=sys.stderr
            )
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
