"""Tests of .github/scripts/verify_release.py: the checks of an image index's
platforms, provenance and SBOM, and of the packages' PyPI attestations, and its
exit codes.

Each test runs the script in a throwaway copy of the repository where
docker and curl are fakes: ``docker buildx imagetools inspect`` prints the
manifest, provenance and SBOM the test wrote, shaped as BuildKit's, and curl
answers each URL with the body and status the test wrote. No test uses the
network.
"""

import hashlib
import json
from pathlib import Path

import pytest

SCRIPT = ".github/scripts/verify_release.py"
IMAGE = "permitio/opal-server@sha256:" + "a" * 64
COMMIT = "1" * 40
REPOSITORY = "permitio/opal"
BOTH = ("linux/amd64", "linux/arm64")
PUBLISHER = {
    "kind": "GitHub",
    "repository": REPOSITORY,
    "workflow": "on_release.yml",
    "environment": "pypi",
}

FAKE_DOCKER = r"""set -euo pipefail
printf '%s\n' "$*" >>"$FAKE_DIR/docker.log"
[[ $1 == buildx && $2 == imagetools && $3 == inspect ]] || exit 99
[[ -z ${FAKE_INSPECT_FAILS:-} ]] || { echo "ERROR: $4: not found" >&2; exit 1; }
[[ -z ${FAKE_INSPECT_HANGS:-} ]] || exec sleep 30
cat -- "$FAKE_DIR/inspect.json"
"""

# The fake curl answers the URL, its last argument, from FAKE_DIR/urls/<sha256 of the URL>: a
# file holding the status on its first line and the body after it, or 404 without one.
FAKE_CURL = r"""set -euo pipefail
url=${*: -1}
printf '%s\n' "$url" >>"$FAKE_DIR/curl.log"
[[ -z ${FAKE_CURL_FAILS:-} ]] || { echo "curl: (6) Could not resolve host" >&2; exit 6; }
[[ -z ${FAKE_CURL_NO_STATUS:-} ]] || { printf 'body only'; exit 0; }
key=$(printf '%s' "$url" | shasum -a 256 | cut -d' ' -f1)
answer=$FAKE_DIR/urls/$key
if [[ -f $answer ]]; then
  tail -n +2 -- "$answer"
  printf '\n%s' "$(head -n 1 -- "$answer")"
else
  printf 'Not Found\n404'
fi
"""


def provenance(
    target="server", commit=COMMIT, source="https://github.com/permitio/opal.git"
):
    """One platform's provenance, as imagetools prints it for BuildKit's SLSA
    v1."""
    return {
        "SLSA": {
            "buildDefinition": {
                "externalParameters": {
                    "request": {
                        "args": {"target": target, "source": "docker/dockerfile"}
                    }
                }
            },
            "runDetails": {
                "metadata": {
                    "buildkit_metadata": {"vcs": {"revision": commit, "source": source}}
                }
            },
        }
    }


def sbom(*names):
    """One platform's SBOM: BuildKit's root entry and the named packages."""
    packages = [{"name": "/", "SPDXID": "SPDXRef-DocumentRoot-Directory-sbom"}]
    packages += [{"name": name, "SPDXID": f"SPDXRef-Package-{name}"} for name in names]
    return {"SPDX": {"packages": packages}}


def manifest(*platforms):
    """An index of the platforms' images, each with its attestation
    manifest."""
    entries = []
    for platform in platforms:
        os_name, architecture = platform.split("/")
        entries.append({"platform": {"os": os_name, "architecture": architecture}})
        entries.append(
            {
                "platform": {"os": "unknown", "architecture": "unknown"},
                "annotations": {"vnd.docker.reference.type": "attestation-manifest"},
            }
        )
    return {
        "mediaType": "application/vnd.oci.image.index.v1+json",
        "manifests": entries,
    }


class Verify:
    """A throwaway repository with verify_release.py and fakes of docker and
    curl."""

    def __init__(self, repo, tmp_path: Path) -> None:
        self.repo = repo
        self.dir = tmp_path / "fake"
        (self.dir / "urls").mkdir(parents=True)
        repo.copy(SCRIPT)
        repo.stub("docker", FAKE_DOCKER)
        repo.stub("curl", FAKE_CURL)
        self.image(
            {p: provenance() for p in BOTH},
            {p: sbom("opal-common", "pygit2") for p in BOTH},
        )

    def image(self, provenance_json, sbom_json, platforms=BOTH) -> None:
        self.inspected(
            {
                "manifest": manifest(*platforms),
                "provenance": provenance_json,
                "sbom": sbom_json,
            }
        )

    def inspected(self, content) -> None:
        text = content if isinstance(content, str) else json.dumps(content)
        (self.dir / "inspect.json").write_text(text)

    def answer(self, url: str, status: int, body) -> None:
        key = hashlib.sha256(url.encode()).hexdigest()
        text = body if isinstance(body, str) else json.dumps(body)
        (self.dir / "urls" / key).write_text(f"{status}\n{text}")

    def published(self, project, version, files, publisher=PUBLISHER):
        self.answer(
            f"https://pypi.org/pypi/{project}/{version}/json",
            200,
            {"urls": [{"filename": name} for name in files]},
        )
        for name in files:
            self.answer(
                f"https://pypi.org/integrity/{project}/{version}/{name}/provenance",
                200,
                {"version": 1, "attestation_bundles": [{"publisher": publisher}]},
            )

    def run(self, *args: str, path=None, **env: str):
        return self.repo.run(
            SCRIPT, *args, env={"FAKE_DIR": str(self.dir), **env}, path=path
        )

    def run_image(self, target="server", commit=COMMIT, image=IMAGE, **env):
        return self.run(
            "image",
            image,
            "--target",
            target,
            "--commit",
            commit,
            "--repository",
            REPOSITORY,
            **env,
        )

    def run_packages(self, *projects, version="0.10.0", **env):
        args = ["packages", version]
        for project in projects:
            args += ["--project", project]
        args += ["--repository", REPOSITORY, "--workflow", "on_release.yml"]
        args += ["--environment", "pypi"]
        return self.run(*args, **env)

    def logged(self, name: str) -> list[str]:
        path = self.dir / name
        return path.read_text().splitlines() if path.exists() else []


@pytest.fixture
def verify(throwaway_repo, tmp_path):
    return Verify(throwaway_repo, tmp_path)


def test_an_index_with_its_provenance_and_sbom_passes_after_one_read(verify):
    result = verify.run_image()

    assert result.returncode == 0, result.output
    assert result.stdout.strip() == f"verify-release: {IMAGE}: PASS"
    (inspected,) = verify.logged("docker.log")
    assert inspected.startswith(f"buildx imagetools inspect {IMAGE} --format ")


@pytest.mark.parametrize(
    "image",
    [
        pytest.param("permitio/opal-server:0.10.0", id="a tag"),
        pytest.param("permitio/opal-server@sha256:abc", id="a short digest"),
    ],
)
def test_an_image_not_named_by_digest_is_refused(verify, image):
    result = verify.run_image(image=image)

    assert result.returncode == 2
    assert "does not name an image by digest" in result.stderr
    assert verify.logged("docker.log") == []


@pytest.mark.parametrize(
    ("arm64", "problem"),
    [
        pytest.param(
            provenance(commit="2" * 40),
            f"linux/arm64: built from revision '{'2' * 40}', not {COMMIT}",
            id="another commit",
        ),
        pytest.param(
            provenance(commit=COMMIT[:12]),
            f"linux/arm64: built from revision '{COMMIT[:12]}', not {COMMIT}",
            id="a prefix of the commit",
        ),
        pytest.param(
            provenance(commit=COMMIT + "x"),
            f"linux/arm64: built from revision '{COMMIT}x', not {COMMIT}",
            id="the commit and more",
        ),
        pytest.param(
            provenance(commit=f"{COMMIT}-dirty"),
            f"linux/arm64: built from revision '{COMMIT}-dirty', not {COMMIT}",
            id="a dirty revision",
        ),
        pytest.param(
            provenance(commit=None),
            f"linux/arm64: built from revision None, not {COMMIT}",
            id="no revision",
        ),
        pytest.param(
            provenance(target="client"),
            "linux/arm64: built for target 'client', not server",
            id="another target",
        ),
        pytest.param(
            provenance(target="server-test"),
            "linux/arm64: built for target 'server-test', not server",
            id="a target that starts with the target",
        ),
        pytest.param(
            provenance(source="https://github.com/someone/opal.git"),
            "linux/arm64: built from 'https://github.com/someone/opal.git', not permitio/opal",
            id="another repository",
        ),
        pytest.param(
            provenance(source="https://github.com/permitio/opal-evil"),
            "linux/arm64: built from 'https://github.com/permitio/opal-evil', not permitio/opal",
            id="a repository that starts with the repository",
        ),
        pytest.param({}, "linux/arm64: no SLSA provenance", id="no provenance"),
        pytest.param(
            {"SLSA": {"buildDefinition": {}}},
            "linux/arm64: the provenance has no VCS source or build args",
            id="a provenance without the fields",
        ),
        pytest.param(
            {
                "SLSA": {
                    **provenance()["SLSA"],
                    "runDetails": {"metadata": {"buildkit_metadata": {"vcs": "x"}}},
                }
            },
            "linux/arm64: the provenance has no VCS source or build args",
            id="a vcs that is not an object",
        ),
    ],
)
def test_an_index_whose_provenance_names_something_else_fails(verify, arm64, problem):
    verify.image(
        {"linux/amd64": provenance(), "linux/arm64": arm64},
        {p: sbom("opal-common") for p in BOTH},
    )

    result = verify.run_image()

    assert result.returncode == 1, result.output
    assert f"verify-release: {IMAGE}: {problem}" in result.stdout
    assert "linux/amd64" not in result.stdout
    assert result.stdout.splitlines()[-1] == f"verify-release: {IMAGE}: FAIL"


def test_a_client_image_does_not_pass_for_a_client_standalone_target(verify):
    verify.image(
        {p: provenance(target="client") for p in BOTH},
        {p: sbom("opal-common") for p in BOTH},
    )

    result = verify.run_image(target="client-standalone")

    assert result.returncode == 1
    assert "built for target 'client', not client-standalone" in result.stdout


@pytest.mark.parametrize(
    ("amd64", "problem"),
    [
        pytest.param({}, "no SPDX SBOM", id="no SBOM"),
        pytest.param(
            sbom(), "the SPDX SBOM does not list opal-common", id="the root only"
        ),
        pytest.param(
            sbom("pygit2"),
            "the SPDX SBOM does not list opal-common",
            id="no opal-common",
        ),
        pytest.param(
            {"SPDX": {"packages": "x"}}, "no SPDX SBOM", id="packages not a list"
        ),
    ],
)
def test_an_index_without_an_sbom_of_opal_fails(verify, amd64, problem):
    verify.image(
        {p: provenance() for p in BOTH},
        {"linux/amd64": amd64, "linux/arm64": sbom("opal-common")},
    )

    result = verify.run_image()

    assert result.returncode == 1
    assert f"linux/amd64: {problem}" in result.stdout


@pytest.mark.parametrize(
    "platforms",
    [
        pytest.param(("linux/amd64",), id="one platform"),
        pytest.param(BOTH + ("linux/s390x",), id="an unattested third platform"),
    ],
)
def test_an_index_of_other_platforms_fails(verify, platforms):
    verify.image(
        {p: provenance() for p in BOTH},
        {p: sbom("opal-common") for p in BOTH},
        platforms,
    )

    result = verify.run_image()

    assert result.returncode == 1
    assert "not exactly ['linux/amd64', 'linux/arm64']" in result.stdout


@pytest.mark.parametrize(
    ("env", "content", "message"),
    [
        pytest.param({"FAKE_INSPECT_FAILS": "1"}, None, "docker exited 1", id="fails"),
        pytest.param({}, "not json", "something other than JSON", id="not JSON"),
        pytest.param({}, "[]", "did not print the manifest", id="not an object"),
        pytest.param(
            {},
            {"manifest": {}, "provenance": {}, "sbom": {}},
            "is not an image index",
            id="not an index",
        ),
        pytest.param(
            {},
            {
                "manifest": {"manifests": [{"digest": "x"}]},
                "provenance": {},
                "sbom": {},
            },
            "without a platform",
            id="an entry without a platform",
        ),
    ],
)
def test_an_index_that_cannot_be_read_did_not_run(verify, env, content, message):
    if content is not None:
        verify.inspected(content)

    result = verify.run_image(**env)

    assert result.returncode == 2
    assert "DID NOT RUN" in result.stdout
    assert message in result.stdout


def test_a_missing_tool_did_not_run(verify, throwaway_repo, tmp_path):
    (throwaway_repo.stubs / "docker").rename(tmp_path / "docker-moved-away")

    result = verify.run(
        "image",
        IMAGE,
        "--target",
        "server",
        "--commit",
        COMMIT,
        "--repository",
        REPOSITORY,
        path=throwaway_repo.path_with_only("python3"),
    )

    assert result.returncode == 2
    assert "docker did not run" in result.stdout


def test_a_tool_that_hangs_did_not_run(verify):
    verify.repo.write(
        SCRIPT,
        (verify.repo.root / SCRIPT)
        .read_text()
        .replace("TIMEOUT_SECONDS = 120", "TIMEOUT_SECONDS = 1"),
        executable=True,
    )

    result = verify.run_image(FAKE_INSPECT_HANGS="1")

    assert result.returncode == 2
    assert "docker timed out after 1 s" in result.stdout


def test_packages_attested_by_this_workflow_pass(verify):
    verify.published("opal-common", "0.10.0", ["a.whl", "a.tar.gz"])
    verify.published("opal-server", "0.10.0", ["b.whl"])

    result = verify.run_packages("opal-common", "opal-server")

    assert result.returncode == 0, result.output
    assert result.stdout.strip() == "verify-release: version 0.10.0: PASS"


@pytest.mark.parametrize(
    "publisher",
    [
        pytest.param({**PUBLISHER, "workflow": "other.yml"}, id="another workflow"),
        pytest.param({**PUBLISHER, "environment": "other"}, id="another environment"),
        pytest.param({**PUBLISHER, "repository": "fork/opal"}, id="another repository"),
        pytest.param({**PUBLISHER, "kind": "GitLab"}, id="another kind"),
    ],
)
def test_a_package_attested_by_someone_else_fails(verify, publisher):
    verify.published("opal-common", "0.10.0", ["a.whl"], publisher=publisher)

    result = verify.run_packages("opal-common")

    assert result.returncode == 1
    assert "a.whl: no attestation from" in result.stdout


def test_a_file_with_another_bundle_besides_this_workflows_passes(verify):
    verify.published("opal-common", "0.10.0", ["a.whl"])
    verify.answer(
        "https://pypi.org/integrity/opal-common/0.10.0/a.whl/provenance",
        200,
        {
            "attestation_bundles": [
                {"publisher": {**PUBLISHER, "workflow": "other.yml"}},
                {"publisher": PUBLISHER},
            ]
        },
    )

    assert verify.run_packages("opal-common").returncode == 0


def test_the_second_file_without_provenance_fails(verify):
    verify.published("opal-common", "0.10.0", ["a.whl", "a.tar.gz"])
    verify.answer(
        "https://pypi.org/integrity/opal-common/0.10.0/a.tar.gz/provenance",
        404,
        "Not Found",
    )

    result = verify.run_packages("opal-common")

    assert result.returncode == 1
    assert "a.tar.gz: no provenance on PyPI (HTTP 404)" in result.stdout
    assert "a.whl" not in result.stdout


def test_the_second_project_that_is_not_on_pypi_fails(verify):
    verify.published("opal-common", "0.10.0", ["a.whl"])

    result = verify.run_packages("opal-common", "opal-client")

    assert result.returncode == 1
    assert (
        "opal-client 0.10.0: not on PyPI (HTTP 404); is it published?" in result.stdout
    )


def test_a_version_without_files_fails(verify):
    verify.published("opal-common", "0.10.0", [])

    result = verify.run_packages("opal-common")

    assert result.returncode == 1
    assert "PyPI lists no files" in result.stdout


@pytest.mark.parametrize(
    ("url", "status", "body", "message"),
    [
        pytest.param(
            "https://pypi.org/pypi/opal-common/0.10.0/json",
            200,
            "not json",
            "answered with something other than JSON",
            id="not JSON",
        ),
        pytest.param(
            "https://pypi.org/pypi/opal-common/0.10.0/json",
            200,
            {"files": []},
            "lists no files",
            id="no urls",
        ),
        pytest.param(
            "https://pypi.org/pypi/opal-common/0.10.0/json",
            503,
            "Service Unavailable",
            "answered HTTP 503",
            id="a server error",
        ),
        pytest.param(
            "https://pypi.org/integrity/opal-common/0.10.0/a.whl/provenance",
            200,
            {"bundles": []},
            "is not PyPI's",
            id="an integrity body that is not PyPI's",
        ),
        pytest.param(
            "https://pypi.org/integrity/opal-common/0.10.0/a.whl/provenance",
            429,
            "Too Many Requests",
            "answered HTTP 429",
            id="rate limited",
        ),
    ],
)
def test_pypi_answers_that_are_not_pypi_did_not_run(verify, url, status, body, message):
    verify.published("opal-common", "0.10.0", ["a.whl"])
    verify.answer(url, status, body)

    result = verify.run_packages("opal-common")

    assert result.returncode == 2
    assert message in result.stdout


def test_curl_that_fails_did_not_run_and_names_the_url(verify):
    result = verify.run_packages("opal-common", FAKE_CURL_FAILS="1")

    assert result.returncode == 2
    assert (
        "curl exited 6 on https://pypi.org/pypi/opal-common/0.10.0/json"
        in result.stdout
    )


def test_curl_without_a_status_did_not_run(verify):
    result = verify.run_packages("opal-common", FAKE_CURL_NO_STATUS="1")

    assert result.returncode == 2
    assert "curl gave no HTTP status" in result.stdout


@pytest.mark.parametrize(
    "args",
    [
        pytest.param((), id="no command"),
        pytest.param(("image", IMAGE), id="image without its options"),
        pytest.param(
            ("packages", "0.10.0", "--repository", REPOSITORY), id="no project"
        ),
    ],
)
def test_wrong_arguments(verify, args):
    assert verify.run(*args).returncode == 2


# Two entries of the SBOM BuildKit (syft) wrote for the Wolfi server image (docker buildx build
# --sbom=true --target server, 527 packages), trimmed to the fields the check reads and a few
# more: syft names the package as setup.py does, opal-common, read from its egg-info.
BUILDKIT_SBOM_EXCERPT = {
    "SPDX": {
        "packages": [
            {
                "name": "sbom",
                "SPDXID": "SPDXRef-DocumentRoot-Directory-sbom",
                "versionInfo": None,
                "primaryPackagePurpose": "FILE",
            },
            {
                "name": "opal-common",
                "SPDXID": "SPDXRef-Package-python-opal-common-e5195126e8aec168",
                "versionInfo": "0.0.0",
                "downloadLocation": "NOASSERTION",
                "sourceInfo": (
                    "acquired package info from installed python package manifest file: "
                    "/opt/venv/lib/python3.14/site-packages/opal_common-0.0.0-py3.14.egg-info/"
                    "PKG-INFO, /opt/venv/lib/python3.14/site-packages/"
                    "opal_common-0.0.0-py3.14.egg-info/top_level.txt"
                ),
                "externalRefs": [
                    {
                        "referenceCategory": "PACKAGE-MANAGER",
                        "referenceType": "purl",
                        "referenceLocator": "pkg:pypi/opal-common@0.0.0",
                    }
                ],
            },
        ]
    }
}


def test_an_sbom_as_buildkit_writes_it_for_an_opal_image_passes(verify):
    verify.image(
        {p: provenance() for p in BOTH}, {p: BUILDKIT_SBOM_EXCERPT for p in BOTH}
    )

    result = verify.run_image()

    assert result.returncode == 0, result.output
