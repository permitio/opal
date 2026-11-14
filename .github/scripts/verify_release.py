#!/usr/bin/env python3
"""Check what a release published: each image's provenance and SBOM, and each
package file's PyPI attestation.

``verify_release.py image <repository>@sha256:<digest> --target <target> --commit <sha>
--repository <owner/name>`` reads the image index that was tested and pushed, by its digest,
with one ``docker buildx imagetools inspect``. It passes when the index holds exactly the
linux/amd64 and linux/arm64 images (besides their attestations), and each carries an SLSA
provenance that names the repository as its source, exactly the commit as its revision, and
exactly the Dockerfile target, and an SPDX SBOM that lists opal-common.

``verify_release.py packages <version> --project <name>... --repository <owner/name>
--workflow <file> --environment <name>`` lists each project's files of that version with PyPI's
JSON API and reads each file's provenance from PyPI's integrity API. It passes when every file
has an attestation bundle published by GitHub from that repository, workflow and environment, as
trusted publishing makes. It checks who published each file, not the file's bytes: a file left
on PyPI by an earlier upload of the same version from the same workflow passes too.

Exit codes: 0 when everything checked passes; 1 when an attestation is missing or names something
else; 2 when the check did not run: wrong arguments, a tool that is missing or fails or times
out, an HTTP answer other than 200 and 404, or an answer that is not what the registry or PyPI
sends.
"""

import argparse
import json
import re
import subprocess
import sys
import urllib.parse

PLATFORMS = {"linux/amd64", "linux/arm64"}
SBOM_PACKAGE = "opal-common"
PYPI = "https://pypi.org"
TIMEOUT_SECONDS = 120
# curl's own limits stay inside TIMEOUT_SECONDS: each try at most 30 s, all of them 90 s.
CURL_LIMITS = ["--max-time", "30", "--retry", "2", "--retry-max-time", "90"]
_BY_DIGEST = re.compile(r"[a-z0-9][a-z0-9._/:-]*@sha256:[0-9a-f]{64}")
# One read of the index: its manifest, and each platform's provenance and SBOM.
_INSPECT_FORMAT = (
    '{"manifest": {{json .Manifest}}, "provenance": {{json .Provenance}}, '
    '"sbom": {{json .SBOM}}}'
)


class NotRun(Exception):
    """The check did not run, for the reason in the message."""


def run(command: list[str], what: str) -> str:
    """A command's standard output.

    Args:
        command: The command.
        what: What it reads, for the message when it fails.

    Raises:
        NotRun: It cannot be started, times out or fails.
    """
    try:
        done = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except OSError as e:
        raise NotRun(f"{command[0]} did not run for {what}: {e}") from e
    except subprocess.TimeoutExpired as e:
        raise NotRun(
            f"{command[0]} timed out after {TIMEOUT_SECONDS} s on {what}"
        ) from e
    if done.returncode != 0:
        last = (done.stderr.strip().splitlines() or ["no output"])[-1]
        raise NotRun(f"{command[0]} exited {done.returncode} on {what}: {last[:200]}")
    return done.stdout


def inspect(image: str) -> dict:
    """The image index's manifest, provenance and SBOM, as imagetools prints
    them.

    Raises:
        NotRun: imagetools fails or prints something other than those three objects.
    """
    text = run(
        [
            "docker",
            "buildx",
            "imagetools",
            "inspect",
            image,
            "--format",
            _INSPECT_FORMAT,
        ],
        image,
    )
    try:
        found = json.loads(text)
    except ValueError as e:
        raise NotRun(
            f"imagetools printed something other than JSON for {image}: {e}"
        ) from e
    if not isinstance(found, dict) or not all(
        isinstance(found.get(key), dict) for key in ("manifest", "provenance", "sbom")
    ):
        raise NotRun(
            f"imagetools did not print the manifest, provenance and SBOM of {image}"
        )
    return found


def platforms_of(manifest: dict, image: str) -> set[str]:
    """The platforms of an index's images, without its attestation manifests.

    Raises:
        NotRun: The manifest is not an index of platform images.
    """
    entries = manifest.get("manifests")
    if not isinstance(entries, list):
        raise NotRun(f"{image} is not an image index")
    found = set()
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("platform"), dict):
            raise NotRun(f"{image} has a manifest entry without a platform")
        annotations = entry.get("annotations") or {}
        if annotations.get("vnd.docker.reference.type") == "attestation-manifest":
            continue
        platform = entry["platform"]
        found.add(f"{platform.get('os')}/{platform.get('architecture')}")
    return found


def source_matches(source: object, repository: str) -> bool:
    """Whether a VCS source URL is the repository on GitHub."""
    pattern = rf"https://github\.com/{re.escape(repository)}(\.git)?/?"
    return isinstance(source, str) and re.fullmatch(pattern, source) is not None


def provenance_problems(
    slsa: object, target: str, commit: str, repository: str
) -> list[str]:
    """What is wrong with one platform's SLSA provenance."""
    if not isinstance(slsa, dict):
        return ["no SLSA provenance"]
    try:
        vcs = slsa["runDetails"]["metadata"]["buildkit_metadata"]["vcs"]
        args = slsa["buildDefinition"]["externalParameters"]["request"]["args"]
    except KeyError, TypeError:
        return ["the provenance has no VCS source or build args"]
    if not isinstance(vcs, dict) or not isinstance(args, dict):
        return ["the provenance has no VCS source or build args"]
    problems = []
    if not source_matches(vcs.get("source"), repository):
        problems.append(f"built from {vcs.get('source')!r}, not {repository}")
    if vcs.get("revision") != commit:
        problems.append(f"built from revision {vcs.get('revision')!r}, not {commit}")
    if args.get("target") != target:
        problems.append(f"built for target {args.get('target')!r}, not {target}")
    return problems


def sbom_problems(sbom: object) -> list[str]:
    """What is wrong with one platform's SBOM."""
    spdx = sbom.get("SPDX") if isinstance(sbom, dict) else None
    packages = spdx.get("packages") if isinstance(spdx, dict) else None
    if not isinstance(packages, list):
        return ["no SPDX SBOM"]
    names = {package.get("name") for package in packages if isinstance(package, dict)}
    if SBOM_PACKAGE not in names:
        return [f"the SPDX SBOM does not list {SBOM_PACKAGE}"]
    return []


def check_image(image: str, target: str, commit: str, repository: str) -> list[str]:
    """The problems with an image index's platforms, provenance and SBOM; empty
    when there are none.

    Raises:
        NotRun: Its index cannot be read.
    """
    found = inspect(image)
    problems = []
    platforms = platforms_of(found["manifest"], image)
    if platforms != PLATFORMS:
        problems.append(
            f"holds the platforms {sorted(platforms)}, not exactly {sorted(PLATFORMS)}"
        )
    for platform in sorted(PLATFORMS):
        attested = found["provenance"].get(platform) or {}
        slsa = attested.get("SLSA") if isinstance(attested, dict) else None
        for problem in provenance_problems(slsa, target, commit, repository):
            problems.append(f"{platform}: {problem}")
        for problem in sbom_problems(found["sbom"].get(platform)):
            problems.append(f"{platform}: {problem}")
    return problems


def fetch_json(url: str) -> object | None:
    """The JSON body of a GET, or None when the answer is 404.

    Raises:
        NotRun: curl fails, the answer is neither 200 nor 404, or a 200 answer is not JSON.
    """
    out = run(
        [
            "curl",
            "--disable",
            "--silent",
            "--show-error",
            "--proto",
            "=https",
            *CURL_LIMITS,
            "--write-out",
            "\n%{http_code}",
            "--",
            url,
        ],
        url,
    )
    body, _, status = out.rpartition("\n")
    if not status.isdigit():
        raise NotRun(f"curl gave no HTTP status for {url}")
    if status == "404":
        return None
    if status != "200":
        raise NotRun(f"{url} answered HTTP {status}")
    try:
        return json.loads(body)
    except ValueError as e:
        raise NotRun(f"{url} answered with something other than JSON: {e}") from e


def check_package(project: str, version: str, publisher: dict[str, str]) -> list[str]:
    """The problems with one project's files of a version; empty when there are
    none.

    Raises:
        NotRun: PyPI cannot be read, or answers in an unexpected shape.
    """
    quoted = urllib.parse.quote(project)
    release = fetch_json(f"{PYPI}/pypi/{quoted}/{urllib.parse.quote(version)}/json")
    if release is None:
        return [f"{project} {version}: not on PyPI (HTTP 404); is it published?"]
    try:
        files = [entry["filename"] for entry in release["urls"]]
    except (KeyError, TypeError) as e:
        raise NotRun(
            f"PyPI's JSON for {project} {version} lists no files: {e!r}"
        ) from e
    if not files:
        return [f"{project} {version}: PyPI lists no files"]
    problems = []
    for filename in files:
        url = (
            f"{PYPI}/integrity/{quoted}/{urllib.parse.quote(version)}/"
            f"{urllib.parse.quote(filename)}/provenance"
        )
        provenance = fetch_json(url)
        if provenance is None:
            problems.append(f"{filename}: no provenance on PyPI (HTTP 404)")
            continue
        try:
            publishers = [
                bundle["publisher"] for bundle in provenance["attestation_bundles"]
            ]
        except (KeyError, TypeError) as e:
            raise NotRun(f"the provenance of {filename} is not PyPI's: {e!r}") from e
        if not any(
            isinstance(found, dict)
            and all(found.get(key) == value for key, value in publisher.items())
            for found in publishers
        ):
            problems.append(
                f"{filename}: no attestation from {publisher}; found {publishers}"
            )
    return problems


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check what a release published.")
    commands = parser.add_subparsers(dest="command", required=True)
    image = commands.add_parser("image", help="an image's provenance and SBOM")
    image.add_argument("image", help="<repository>@sha256:<digest> of the pushed index")
    image.add_argument("--target", required=True)
    image.add_argument("--commit", required=True)
    image.add_argument("--repository", required=True)
    packages = commands.add_parser("packages", help="the packages' PyPI attestations")
    packages.add_argument("version")
    packages.add_argument("--project", action="append", required=True)
    packages.add_argument("--repository", required=True)
    packages.add_argument("--workflow", required=True)
    packages.add_argument("--environment", required=True)
    args = parser.parse_args(argv)
    if args.command == "image" and not _BY_DIGEST.fullmatch(args.image):
        parser.error(
            f"{args.image} does not name an image by digest (<repository>@sha256:...)"
        )
    return args


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    what = args.image if args.command == "image" else f"version {args.version}"
    try:
        if args.command == "image":
            problems = check_image(
                args.image, args.target, args.commit, args.repository
            )
        else:
            publisher = {
                "kind": "GitHub",
                "repository": args.repository,
                "workflow": args.workflow,
                "environment": args.environment,
            }
            problems = []
            for project in args.project:
                problems += check_package(project, args.version, publisher)
    except NotRun as e:
        print(f"verify-release: {what}: DID NOT RUN: {e}")
        return 2
    for problem in problems:
        print(f"verify-release: {what}: {problem}")
    if problems:
        print(f"verify-release: {what}: FAIL")
        return 1
    print(f"verify-release: {what}: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
