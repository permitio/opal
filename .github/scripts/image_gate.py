#!/usr/bin/env python3
"""Gate container images on Trivy and Grype before they are published.

``image_gate.py [--waivers FILE] [--summary FILE] [--report-only IMAGE]... <image>...`` saves each
image, which must be in the local Docker daemon, with ``docker image save`` and scans that one
archive twice:

* with Trivy, through ``.github/scripts/trivy.sh report archive:<file> <findings file>`` and the
  Trivy release ``.github/binaries.lock`` pins, which ``fetch-tool.sh trivy`` installs;
* with Grype, run from the image ``.github/grype/Dockerfile`` pins by digest (Dependabot
  proposes newer releases), as the caller's own uid, with ``--by-cve``, so a finding carries
  its CVE id where it has one. Grype is a second matcher with a vulnerability database of its
  own over the same archive.

A scan counts only when the scanner found the image's OS: trivy.sh checks Trivy's, and the
gate checks that Grype's report names a distro. Without one, neither would match any OS
package, and an empty report would pass.

A finding blocks the image when it is of HIGH or CRITICAL severity, has a fixed version, and no
waiver in force covers it. The waivers are in ``.github/image-waivers.toml``, as ``[[waiver]]``
tables:

    id        a CVE or GHSA id; it matches a finding's id or any of its aliases
    package   the package's name as the scanner reports it; case, "-", "_" and "." do not matter
    version   optional: the installed version it covers, exactly
    images    optional: the repositories (without the tag) it covers, such as
              "permitio/opal-client"; without it, every image
    expires   the last day it applies, at most MAX_WAIVER_DAYS days after the run
    reason    why the finding is accepted until then

An expired waiver no longer applies: its findings block again, and the report says it expired.
A waiver that covers no finding of any image scanned is reported, so it can be deleted. An
image given with ``--report-only`` is scanned and reported the same way, but its findings never
fail the gate: for an image whose findings no release can fix. Each image is named once, gated
or reported only; an image named twice stops the gate.

Everything it prints until the verdict is inside a stop-commands block, so that no scanner output
can issue a workflow command; the verdict lines are workflow commands. Neither scanner gets
GH_TOKEN or GITHUB_TOKEN. With ``--summary``, it appends a Markdown report to the file, such as
GITHUB_STEP_SUMMARY.

Exit codes: 0 when no image has a finding that blocks; 1 when one has; 2 when the gate did not
run for an image or at all: wrong arguments, a waiver file that cannot be read or has an
unknown key, a missing field or an expiry too far ahead, an image that cannot be saved, or a
scanner that failed or did not write its report.
"""

import argparse
import datetime
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WAIVERS = ROOT / ".github" / "image-waivers.toml"
GRYPE_DOCKERFILE = ROOT / ".github" / "grype" / "Dockerfile"
_GRYPE_FROM = re.compile(
    r"^FROM (anchore/grype:v\d+\.\d+\.\d+@sha256:[0-9a-f]{64})\s*$", re.MULTILINE
)
MAX_WAIVER_DAYS = 180
BLOCKING_SEVERITIES = ("critical", "high")
WAIVER_KEYS = {"id", "package", "version", "images", "expires", "reason"}
REQUIRED_WAIVER_KEYS = {"id", "package", "expires", "reason"}
MAX_VALUE = 120
SCANNER_TIMEOUT_SECONDS = 1800

_WHITESPACE = re.compile(r"[\s\x00-\x1f\x7f]+")
_NAME_SEPARATORS = re.compile(r"[-_.]+")


class GateError(Exception):
    """The gate did not run, for the reason in the message."""


@dataclass(frozen=True)
class Finding:
    """One vulnerability one scanner reported in one image.

    Attributes:
        scanner: "Trivy" or "Grype".
        vuln_id: The id the scanner gives it.
        aliases: Its other ids, such as a CVE's GHSA id.
        package: The package's name.
        version: The installed version.
        fix: The fixed version or versions; empty when there is none.
        severity: "critical", "high", "medium", "low", or "" when unknown.
    """

    scanner: str
    vuln_id: str
    aliases: tuple[str, ...]
    package: str
    version: str
    fix: str
    severity: str

    @property
    def fixable_and_severe(self) -> bool:
        """Whether it blocks the image unless a waiver covers it."""
        return self.severity in BLOCKING_SEVERITIES and bool(self.fix)

    @property
    def key(self) -> tuple[str, str, str]:
        """What makes two scanners' findings one: id, package and version."""
        return (self.vuln_id, normalise_name(self.package), self.version)


@dataclass(frozen=True)
class Waiver:
    """One ``[[waiver]]`` of the waiver file; see the module docstring."""

    vuln_id: str
    package: str
    version: str | None
    images: tuple[str, ...] | None
    expires: datetime.date
    reason: str

    def covers(self, finding: Finding, repository: str) -> bool:
        """Whether it names this finding in this image, whatever its expiry."""
        if self.vuln_id != finding.vuln_id and self.vuln_id not in finding.aliases:
            return False
        if normalise_name(self.package) != normalise_name(finding.package):
            return False
        if self.version is not None and self.version != finding.version:
            return False
        return self.images is None or repository in self.images

    def label(self) -> str:
        """How the report names it."""
        return f"{self.vuln_id} in {self.package}"


@dataclass
class ImageResult:
    """The outcome of one image.

    Attributes:
        image: The image as given.
        counts: How many findings each scanner reported.
        blocking: The findings that block it, one per key, with the scanners that saw it.
        waived: The findings a waiver in force covers, with that waiver.
        expired: The blocking findings whose only waiver expired, with that waiver.
        error: Why the gate did not run for it; empty when it did.
        report_only: Its findings are reported and never fail the gate.
    """

    image: str
    counts: dict[str, int] = field(default_factory=dict)
    blocking: list[tuple[Finding, list[str]]] = field(default_factory=list)
    waived: list[tuple[Finding, list[str], Waiver]] = field(default_factory=list)
    expired: list[tuple[Finding, Waiver]] = field(default_factory=list)
    error: str = ""
    report_only: bool = False

    @property
    def code(self) -> int:
        if self.error:
            return 2
        return 1 if self.blocking and not self.report_only else 0


def normalise_name(name: str) -> str:
    """A package name with case and the "-", "_" and "." separators made
    uniform."""
    return _NAME_SEPARATORS.sub("-", name).lower()


def clip(value: object, limit: int = MAX_VALUE) -> str:
    """An untrusted value on one line, cut to the limit."""
    text = _WHITESPACE.sub(" ", str(value)).strip()
    return text if len(text) <= limit else text[: limit - 3] + "..."


def repository_of(image: str) -> str:
    """The image's repository: the reference without its tag or digest."""
    name = image.split("@", 1)[0]
    slash = name.rfind("/")
    colon = name.rfind(":")
    return name[:colon] if colon > slash else name


def load_waivers(path: Path, today: datetime.date) -> list[Waiver]:
    """The waivers of the file, checked.

    Raises:
        GateError: The file cannot be read or parsed, or a waiver has an unknown key, misses a
            required one, has a value of the wrong type, or expires more than MAX_WAIVER_DAYS
            days after today.
    """
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise GateError(f"the waiver file {path} cannot be read: {e}") from e
    unknown_tables = set(data) - {"waiver"}
    if unknown_tables:
        raise GateError(
            f"{path} has keys other than [[waiver]]: {sorted(unknown_tables)}"
        )
    entries = data.get("waiver", [])
    if not isinstance(entries, list):
        raise GateError(f"{path}: waiver must be an array of tables, [[waiver]]")
    latest = today + datetime.timedelta(days=MAX_WAIVER_DAYS)
    waivers = []
    for number, entry in enumerate(entries, start=1):
        where = f"{path}: waiver {number}"
        unknown = set(entry) - WAIVER_KEYS
        missing = REQUIRED_WAIVER_KEYS - set(entry)
        if unknown or missing:
            raise GateError(
                f"{where}: unknown keys {sorted(unknown)}, missing keys {sorted(missing)}"
            )
        texts = [
            entry["id"],
            entry["package"],
            entry["reason"],
            entry.get("version", "x"),
        ]
        if not all(isinstance(value, str) and value.strip() for value in texts):
            raise GateError(f"{where}: id, package, version and reason must be text")
        images = entry.get("images")
        if images is not None and not (
            isinstance(images, list)
            and images
            and all(isinstance(image, str) and image for image in images)
        ):
            raise GateError(f"{where}: images must be a list of repository names")
        expires = entry["expires"]
        if not isinstance(expires, datetime.date) or isinstance(
            expires, datetime.datetime
        ):
            raise GateError(f"{where}: expires must be a date, such as 2027-01-31")
        if expires > latest:
            raise GateError(
                f"{where} ({entry['id']}) expires on {expires}, more than "
                f"{MAX_WAIVER_DAYS} days ahead (after {latest}); set an earlier date"
            )
        waivers.append(
            Waiver(
                vuln_id=entry["id"],
                package=entry["package"],
                version=entry.get("version"),
                images=tuple(images) if images is not None else None,
                expires=expires,
                reason=entry["reason"],
            )
        )
    return waivers


def trivy_findings(path: Path) -> list[Finding]:
    """The findings trivy.sh wrote, one JSON object per line.

    Raises:
        GateError: The file is missing, or a line is not a finding.
    """
    try:
        lines = path.read_text().splitlines()
    except OSError as e:
        raise GateError(f"trivy.sh wrote no findings file: {e}") from e
    findings = []
    for line in lines:
        try:
            entry = json.loads(line)
            findings.append(
                Finding(
                    scanner="Trivy",
                    vuln_id=str(entry["id"]),
                    aliases=tuple(str(alias) for alias in entry.get("aliases") or []),
                    package=str(entry["package"]),
                    version=str(entry.get("version") or ""),
                    fix=str(entry.get("fix") or ""),
                    severity=str(entry.get("severity") or "").lower(),
                )
            )
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            raise GateError(
                f"trivy.sh wrote a line that is not a finding: {e!r}"
            ) from e
    return findings


def grype_image(dockerfile: Path) -> str:
    """The Grype image the FROM line of .github/grype/Dockerfile names.

    Raises:
        GateError: The file cannot be read, or names no release tag pinned by digest.
    """
    try:
        text = dockerfile.read_text()
    except OSError as e:
        raise GateError(f"the Grype pin {dockerfile} cannot be read: {e}") from e
    found = _GRYPE_FROM.search(text)
    if found is None:
        raise GateError(
            f"{dockerfile} pins no anchore/grype image by digest: write its FROM line as "
            "anchore/grype:vX.Y.Z@sha256:<digest of the tag's index>"
        )
    return found.group(1)


def grype_findings(output: str) -> list[Finding]:
    """The findings of Grype's JSON report.

    Raises:
        GateError: The output is not a Grype report, or Grype found no OS in the image.
    """
    try:
        report = json.loads(output)
        matches = report["matches"]
        if not isinstance(matches, list):
            raise TypeError("matches is not a list")
        findings = []
        for match in matches:
            vulnerability = match["vulnerability"]
            artifact = match["artifact"]
            fix = vulnerability.get("fix") or {}
            fixed = fix.get("state") == "fixed" and fix.get("versions") or []
            findings.append(
                Finding(
                    scanner="Grype",
                    vuln_id=str(vulnerability["id"]),
                    aliases=tuple(
                        str(related["id"])
                        for related in match.get("relatedVulnerabilities") or []
                    ),
                    package=str(artifact["name"]),
                    version=str(artifact.get("version") or ""),
                    fix=", ".join(str(version) for version in fixed),
                    severity=str(vulnerability.get("severity") or "").lower(),
                )
            )
        distro = report.get("distro") or {}
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        raise GateError(f"Grype's output is not a JSON report of matches: {e!r}") from e
    if not isinstance(distro, dict) or not distro.get("name"):
        raise GateError(
            "Grype found no OS in the image (its report names no distro), so it matched "
            "no OS package"
        )
    return findings


def run(command: list[str], env: dict[str, str]) -> subprocess.CompletedProcess:
    """Run a command in the repository root and capture its output.

    Raises:
        GateError: It cannot be started or does not end within the timeout.
    """
    try:
        return subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=SCANNER_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise GateError(f"{command[0]} did not run: {e}") from e


def last_line(text: str) -> str:
    lines = [line for line in text.splitlines() if line.strip()]
    return clip(lines[-1]) if lines else "no output"


def scan(
    image: str, number: int, work: Path, env: dict[str, str], grype: str
) -> list[Finding]:
    """Save the image and scan the archive with Trivy and Grype; the archive is
    deleted afterwards.

    Raises:
        GateError: The image cannot be saved, or a scanner did not run.
    """
    archive = work / f"image-{number}.tar"
    try:
        return _scan_archive(image, number, archive, env, grype)
    finally:
        archive.unlink(missing_ok=True)


def _scan_archive(
    image: str, number: int, archive: Path, env: dict[str, str], grype: str
) -> list[Finding]:
    work = archive.parent
    saved = run(["docker", "image", "save", "--output", str(archive), image], env)
    if saved.returncode != 0:
        raise GateError(f"docker could not save {image}: {last_line(saved.stderr)}")
    trivy_file = work / f"trivy-{number}.jsonl"
    trivy = run(
        [
            ".github/scripts/trivy.sh",
            "report",
            f"archive:{archive}",
            str(trivy_file),
        ],
        env,
    )
    print(trivy.stdout, end="")
    if trivy.returncode != 0:
        raise GateError(
            f"trivy.sh exited {trivy.returncode}: {last_line(trivy.stdout)}"
        )
    found = trivy_findings(trivy_file)
    grype_db = work / "grype-db"
    grype_db.mkdir(exist_ok=True)
    grype_tmp = work / f"grype-tmp-{number}"
    grype_tmp.mkdir(exist_ok=True)
    # As the caller's uid, so that everything Grype writes (its DB, its unpacked layers) stays
    # the caller's to delete; the image sets no user of its own.
    scanned = run(
        [
            "docker",
            "run",
            "--rm",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--env",
            "GRYPE_DB_CACHE_DIR=/grype-db",
            "--env",
            "GRYPE_CHECK_FOR_APP_UPDATE=false",
            "--env",
            "TMPDIR=/grype-tmp",
            "--volume",
            f"{archive}:/scan/image.tar:ro",
            "--volume",
            f"{grype_db}:/grype-db",
            "--volume",
            f"{grype_tmp}:/grype-tmp",
            grype,
            "docker-archive:/scan/image.tar",
            "--by-cve",
            "--output",
            "json",
        ],
        env,
    )
    if scanned.returncode != 0:
        raise GateError(
            f"Grype exited {scanned.returncode}: {last_line(scanned.stderr)}"
        )
    found.extend(grype_findings(scanned.stdout))
    return found


def judge(
    image: str,
    findings: list[Finding],
    waivers: list[Waiver],
    today: datetime.date,
    used: set[Waiver],
) -> ImageResult:
    """Sort an image's fixable HIGH and CRITICAL findings into blocking and
    waived, and record the waivers that covered one in ``used``."""
    repository = repository_of(image)
    result = ImageResult(image=image)
    for finding in findings:
        result.counts[finding.scanner] = result.counts.get(finding.scanner, 0) + 1
    merged: dict[tuple[str, str, str], tuple[Finding, list[str]]] = {}
    for finding in findings:
        if not finding.fixable_and_severe:
            continue
        _, scanners = merged.setdefault(finding.key, (finding, []))
        if finding.scanner not in scanners:
            scanners.append(finding.scanner)
    for finding, scanners in merged.values():
        covering = [waiver for waiver in waivers if waiver.covers(finding, repository)]
        used.update(covering)
        in_force = [waiver for waiver in covering if waiver.expires >= today]
        if in_force:
            result.waived.append((finding, scanners, in_force[0]))
            continue
        result.blocking.append((finding, scanners))
        if covering:
            result.expired.append((finding, covering[0]))
    return result


def finding_line(finding: Finding, scanners: list[str]) -> str:
    return (
        f"{clip(finding.vuln_id)} {finding.severity} {clip(finding.package)} "
        f"{clip(finding.version)}, fixed in {clip(finding.fix)} ({', '.join(scanners)})"
    )


def markdown(value: str) -> str:
    """A value for a Markdown table cell."""
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("`", "'")


def render_summary(results: list[ImageResult]) -> str:
    """The Markdown report for the job summary."""
    lines = ["## Image gate (Trivy and Grype)", ""]
    for result in results:
        if result.error:
            verdict = f"did not run: {markdown(result.error)}"
        elif result.blocking and result.report_only:
            verdict = f"reported, not gated: {len(result.blocking)} findings"
        elif result.blocking:
            verdict = f"**{len(result.blocking)} findings block it**"
        else:
            verdict = "passes"
        lines.append(f"### `{markdown(result.image)}`: {verdict}")
        lines.append("")
        status = "reported" if result.report_only else "blocks"
        rows = [(status, finding, scanners) for finding, scanners in result.blocking]
        rows += [
            (f"waived until {waiver.expires}", finding, scanners)
            for finding, scanners, waiver in result.waived
        ]
        if rows:
            lines += [
                "| | Vulnerability | Severity | Package | Installed | Fixed in | Seen by |",
                "|---|---|---|---|---|---|---|",
            ]
            for status, finding, scanners in rows:
                cells = [
                    status,
                    clip(finding.vuln_id),
                    finding.severity,
                    clip(finding.package),
                    clip(finding.version),
                    clip(finding.fix),
                    ", ".join(scanners),
                ]
                lines.append("| " + " | ".join(markdown(cell) for cell in cells) + " |")
            lines.append("")
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gate container images on Trivy and Grype findings."
    )
    parser.add_argument("images", nargs="+", help="images in the local Docker daemon")
    parser.add_argument("--waivers", type=Path, default=WAIVERS, help="the waiver file")
    parser.add_argument("--summary", type=Path, help="a file to append the report to")
    parser.add_argument(
        "--report-only",
        action="append",
        default=[],
        metavar="IMAGE",
        help="an image to scan and report whose findings never fail the gate",
    )
    return parser.parse_args(argv)


def gate(args: argparse.Namespace, today: datetime.date) -> list[ImageResult]:
    """Scan and judge every image; the waiver file is read first."""
    named = args.images + args.report_only
    twice = sorted({image for image in named if named.count(image) > 1})
    if twice:
        raise GateError(
            f"{', '.join(twice)} is named more than once: name each image once, gated or "
            "with --report-only"
        )
    waivers = load_waivers(args.waivers, today)
    grype = grype_image(GRYPE_DOCKERFILE)
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in ("GH_TOKEN", "GITHUB_TOKEN")
    }
    fetched = run([".github/scripts/fetch-tool.sh", "trivy"], env)
    if fetched.returncode != 0:
        print(fetched.stdout + fetched.stderr, end="")
        raise GateError("installing Trivy with fetch-tool.sh failed")
    base = os.environ.get("RUNNER_TEMP") or tempfile.gettempdir()
    try:
        work = Path(tempfile.mkdtemp(prefix="image-gate.", dir=base))
    except OSError as e:
        raise GateError(f"creating a temporary directory failed: {e}") from e
    results = []
    used: set[Waiver] = set()
    report_only = set(args.report_only)
    for number, image in enumerate(args.images + args.report_only):
        print(f"image-gate: {image}")
        try:
            findings = scan(image, number, work, env, grype)
        except GateError as e:
            results.append(ImageResult(image=image, error=str(e)))
            continue
        result = judge(image, findings, waivers, today, used)
        result.report_only = image in report_only
        results.append(result)
        counts = ", ".join(f"{name} {count}" for name, count in result.counts.items())
        print(
            f"image-gate: {image}: findings by scanner: {counts or 'none'}; "
            f"{len(result.blocking)} block, {len(result.waived)} waived"
        )
        status = "reported" if result.report_only else "blocks"
        for finding, scanners in result.blocking:
            print(f"image-gate:   {status}: {finding_line(finding, scanners)}")
        for finding, waiver in result.expired:
            print(
                f"image-gate:   the waiver of {waiver.label()} expired on {waiver.expires}"
            )
        for finding, scanners, waiver in result.waived:
            print(
                f"image-gate:   waived until {waiver.expires}: "
                f"{finding_line(finding, scanners)}"
            )
    if all(not result.error for result in results):
        for waiver in waivers:
            if waiver not in used:
                print(f"image-gate: the waiver of {waiver.label()} covers no finding")
    return results


def main(argv: list[str] | None = None) -> int:
    token = secrets.token_hex(16)
    print(f"::stop-commands::{token}", flush=True)
    resumed = False

    def resume() -> None:
        nonlocal resumed
        if not resumed:
            print(f"::{token}::", flush=True)
            resumed = True

    try:
        try:
            args = parse_args(argv)
        except SystemExit as e:
            resume()
            print("::error title=Image gate::wrong arguments; the gate did not run")
            return 2 if e.code else 0
        try:
            results = gate(args, datetime.date.today())
        except GateError as e:
            print(f"image-gate: {e}")
            resume()
            print(f"::error title=Image gate::the gate did not run: {clip(e, 300)}")
            return 2
        if args.summary is not None:
            try:
                with args.summary.open("a") as handle:
                    handle.write(render_summary(results))
            except OSError as e:
                resume()
                print(f"::error title=Image gate::writing {args.summary} failed: {e}")
                return 2
        resume()
        for result in results:
            if result.error:
                print(
                    f"::error title=Image gate::{result.image}: the gate did not run: "
                    f"{clip(result.error, 300)}"
                )
            elif result.blocking and result.report_only:
                print(
                    f"::warning title=Image gate::{result.image}: {len(result.blocking)} "
                    "fixable HIGH or CRITICAL vulnerabilities (reported, not gated)"
                )
            elif result.blocking:
                print(
                    f"::error title=Image gate::{result.image}: {len(result.blocking)} "
                    "fixable HIGH or CRITICAL vulnerabilities; upgrade the package, or "
                    "waive one in .github/image-waivers.toml with a reason and an expiry"
                )
        code = max(result.code for result in results)
        print(f"image-gate: {['PASS', 'FAIL', 'DID NOT RUN'][code]}")
        return code
    finally:
        resume()


if __name__ == "__main__":
    sys.exit(main())
