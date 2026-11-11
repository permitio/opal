"""Facts about .github/workflows that the repository relies on: permissions,
pinned actions, checkouts without stored credentials, the jobs the CI check
needs, the Python that CI and the release run on, and the PyPI environment.

A change that breaks one of them fails here. A deliberate change, such
as a new job or a new write permission, also edits the fact pinned here.
"""

import re
from pathlib import Path

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parents[2] / "workflows"
WORKFLOW_FILES = sorted(WORKFLOWS.glob("*.y*ml"))
PACKAGES = Path(__file__).resolve().parents[3] / "packages"

# The one Python the three packages support (python_requires in packages/*/setup.py), so the one
# that CI tests them on and the release builds them on.
PACKAGES_PYTHON = "3.14"
PACKAGES_PYTHON_REQUIRES = '">=3.14,<3.15"'

# The required checks of the branch ruleset: the job names, per workflow.
REQUIRED_CHECKS = {"tests.yml": "CI", "pre-commit.yml": "pre-commit"}

# The jobs that the CI job of tests.yml needs, and of them the ones that run on pull requests
# only. Adding a job to tests.yml means adding it here and to the CI job's needs.
CI_NEEDS = {
    "build",
    "e2e-tests",
    "binary-stages",
    "secrets",
    "dependency-review",
    "vuln",
}
CI_PULL_REQUEST_JOBS = {"dependency-review", "vuln"}

# The images the release publishes: (Docker Hub repository, docker/Dockerfile target). Every image
# builds on Wolfi, in one variant.
RELEASE_IMAGES = {
    ("permitio/opal-client", "client"),
    ("permitio/opal-client-standalone", "client-standalone"),
    ("permitio/opal-client-cedar", "client-cedar"),
    ("permitio/opal-client-eopa", "client-eopa"),
    ("permitio/opal-server", "server"),
}

# Every write permission a job has: (workflow, job, scope).
WRITE_PERMISSIONS = {
    ("tests.yml", "dependency-review", "pull-requests"),
    ("on_release.yml", "release-assets", "contents"),
    ("on_release.yml", "publish-packages", "id-token"),
}

SHA_PIN = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")
USES_LINE = re.compile(r"^\s*(?:-\s+)?uses:\s*(?P<ref>\S+)(?P<rest>.*)$")
VERSION_COMMENT = re.compile(r"^\s+#\s+v\d+\.\d+\.\d+\s*$")


def load(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def steps_of(job: dict) -> list[dict]:
    return job.get("steps") or []


def all_jobs():
    """Each job of every workflow, as (workflow file name, job id, job)."""
    for path in WORKFLOW_FILES:
        for job_id, job in load(path)["jobs"].items():
            yield path.name, job_id, job


def all_uses(workflow: dict) -> list[str]:
    """Every uses: value of a workflow, of its jobs and of their steps."""
    found = []
    for job in workflow["jobs"].values():
        if "uses" in job:
            found.append(job["uses"])
        found.extend(step["uses"] for step in steps_of(job) if "uses" in step)
    return found


def setup_python_versions(job: dict) -> list:
    return [
        step.get("with", {}).get("python-version")
        for step in steps_of(job)
        if step.get("uses", "").startswith("actions/setup-python@")
    ]


def image_gate_runs(job: dict) -> list[str]:
    """The run: of each step of a job that runs .github/scripts/image_gate.py."""
    return [
        step["run"] for step in steps_of(job) if "image_gate.py" in step.get("run", "")
    ]


def environment_name(job: dict) -> str | None:
    environment = job.get("environment")
    if isinstance(environment, dict):
        return environment.get("name")
    return environment


def test_finds_the_workflows():
    assert {path.name for path in WORKFLOW_FILES} >= {
        "tests.yml",
        "pre-commit.yml",
        "security.yml",
        "on_release.yml",
        "docs-build.yml",
    }


@pytest.mark.parametrize("path", WORKFLOW_FILES, ids=lambda path: path.name)
def test_every_workflow_sets_read_only_top_level_permissions(path):
    workflow = load(path)

    assert "permissions" in workflow, f"{path.name} has no top-level permissions"
    permissions = workflow["permissions"]
    assert isinstance(permissions, dict), f"{path.name}: permissions: {permissions!r}"
    assert set(permissions.values()) <= {"read", "none"}, f"{path.name}: {permissions}"


@pytest.mark.parametrize(
    ("workflow", "job_id", "job"),
    list(all_jobs()),
    ids=[f"{name}:{job_id}" for name, job_id, _ in all_jobs()],
)
def test_every_job_sets_its_permissions(workflow, job_id, job):
    assert "permissions" in job, f"{workflow}: job {job_id} has no permissions block"
    assert isinstance(
        job["permissions"], dict
    ), f"{workflow}: {job_id}: {job['permissions']!r}"


def test_only_the_known_jobs_can_write():
    writes = {
        (workflow, job_id, scope)
        for workflow, job_id, job in all_jobs()
        for scope, level in job["permissions"].items()
        if level == "write"
    }

    assert writes == WRITE_PERMISSIONS


@pytest.mark.parametrize("path", WORKFLOW_FILES, ids=lambda path: path.name)
def test_every_remote_action_is_pinned_to_a_commit_with_its_version(path):
    lines = path.read_text().splitlines()
    uses_lines = [match for line in lines if (match := USES_LINE.match(line))]

    assert sorted(match["ref"] for match in uses_lines) == sorted(
        all_uses(load(path))
    ), "a uses: in a form this test does not read"
    for match in uses_lines:
        ref = match["ref"]
        if ref.startswith("./"):
            continue
        assert SHA_PIN.match(
            ref
        ), f"{path.name}: {ref} is not pinned to a full commit SHA"
        assert VERSION_COMMENT.match(
            match["rest"]
        ), f"{path.name}: {ref} has no '# vX.Y.Z' comment on its line"


def test_one_version_of_an_action_is_one_commit():
    commits: dict[tuple[str, str], set[str]] = {}
    for path in WORKFLOW_FILES:
        for line in path.read_text().splitlines():
            match = USES_LINE.match(line)
            if not match or match["ref"].startswith("./"):
                continue
            action, sha = match["ref"].split("@")
            version = match["rest"].strip().lstrip("#").strip()
            commits.setdefault((action, version), set()).add(sha)

    assert {key: shas for key, shas in commits.items() if len(shas) > 1} == {}


@pytest.mark.parametrize("path", WORKFLOW_FILES, ids=lambda path: path.name)
def test_every_checkout_keeps_no_credentials(path):
    for job_id, job in load(path)["jobs"].items():
        for step in steps_of(job):
            if not step.get("uses", "").startswith("actions/checkout@"):
                continue
            assert (
                step.get("with", {}).get("persist-credentials") is False
            ), f"{path.name}: a checkout in {job_id} does not set persist-credentials: false"


@pytest.mark.parametrize(("file_name", "check"), REQUIRED_CHECKS.items())
def test_the_required_checks_keep_their_names(file_name, check):
    jobs = load(WORKFLOWS / file_name)["jobs"]

    assert check in {job.get("name", job_id) for job_id, job in jobs.items()}


class TestCiJob:
    """The CI job of tests.yml, the check that the ruleset requires.

    It hands the results of the jobs it needs to ci-aggregate.sh.
    """

    @pytest.fixture
    def jobs(self):
        return load(WORKFLOWS / "tests.yml")["jobs"]

    @pytest.fixture
    def env(self, jobs):
        steps = [
            step
            for step in steps_of(jobs["ci"])
            if "ci-aggregate.sh" in step.get("run", "")
        ]
        assert len(steps) == 1, "the CI job runs .github/scripts/ci-aggregate.sh once"
        return steps[0]["env"]

    def test_needs_every_other_job(self, jobs):
        assert set(jobs["ci"]["needs"]) == set(jobs) - {"ci"}

    def test_needs_the_pinned_jobs(self, jobs):
        assert set(jobs["ci"]["needs"]) == CI_NEEDS

    def test_runs_whatever_the_needed_jobs_did(self, jobs):
        assert jobs["ci"]["if"] == "always()"

    def test_expects_as_many_results_as_it_needs(self, jobs, env):
        assert int(env["EXPECTED_JOBS"]) == len(jobs["ci"]["needs"])

    def test_passes_the_results_and_the_event(self, env):
        assert env["NEEDS"] == "${{ toJSON(needs) }}"
        assert env["EVENT"] == "${{ github.event_name }}"

    def test_the_jobs_that_run_on_pull_requests_only(self, jobs, env):
        pull_request_jobs = set(env["PULL_REQUEST_JOBS"].split())

        assert pull_request_jobs == CI_PULL_REQUEST_JOBS
        for job_id in pull_request_jobs:
            assert jobs[job_id]["if"] == "github.event_name == 'pull_request'"

    def test_every_other_needed_job_runs_on_every_event(self, jobs, env):
        pull_request_jobs = set(env["PULL_REQUEST_JOBS"].split())
        conditional = {job_id for job_id in jobs["ci"]["needs"] if "if" in jobs[job_id]}

        assert (
            conditional == pull_request_jobs
        ), "ci-aggregate.sh fails a skipped job that is not in PULL_REQUEST_JOBS"


@pytest.mark.parametrize("package", ["opal-common", "opal-client", "opal-server"])
def test_every_package_requires_the_python_ci_runs(package):
    setup_py = (PACKAGES / package / "setup.py").read_text()

    assert f"python_requires={PACKAGES_PYTHON_REQUIRES}," in setup_py
    assert f'"Programming Language :: Python :: {PACKAGES_PYTHON}",' in setup_py


class TestTests:
    """tests.yml: the Python of the unit and E2E jobs."""

    @pytest.fixture
    def jobs(self):
        return load(WORKFLOWS / "tests.yml")["jobs"]

    def test_the_unit_job_runs_on_the_packages_python_only(self, jobs):
        assert jobs["build"]["strategy"]["matrix"] == {
            "python-version": [PACKAGES_PYTHON]
        }

    def test_the_e2e_job_installs_the_packages_on_their_python(self, jobs):
        assert setup_python_versions(jobs["e2e-tests"]) == [PACKAGES_PYTHON]

    def test_the_e2e_job_gates_the_images_it_builds(self, jobs):
        (gate,) = image_gate_runs(jobs["e2e-tests"])

        assert "permitio/opal-client:test" in gate
        assert "permitio/opal-server:test" in gate

    def test_the_e2e_checks_after_the_gate_still_run_when_only_the_gate_failed(
        self, jobs
    ):
        """A blocking finding fails the job, but the E2E still reports."""
        steps = steps_of(jobs["e2e-tests"])
        (index,) = [
            i for i, step in enumerate(steps) if "image_gate.py" in step.get("run", "")
        ]

        assert steps[index]["id"] == "gate"
        assert steps[index + 1 :]
        for step in steps[index + 1 :]:
            # Never after a cancel: a pull request's newer commit cancels its older run.
            assert step.get("if") == (
                "${{ !cancelled() && (success() || steps.gate.outcome == 'failure') }}"
            ), step

    def test_the_vuln_job_scans_the_published_ranges_with_vuln_sh(self, jobs):
        """vuln.sh resolves the packages' requires files at their floor and
        ceiling and fails on a fixable HIGH or CRITICAL vulnerability; the job
        only runs it."""
        runs = [step["run"] for step in steps_of(jobs["vuln"]) if "run" in step]

        assert runs == [".github/scripts/vuln.sh"]
        assert jobs["vuln"]["permissions"] == {"contents": "read"}


class TestRelease:
    """on_release.yml: built once, gated and tested, then the same bytes
    published from protected environments; a dry run on pull requests."""

    PUBLISH_JOBS = {"publish-images": "docker-hub", "publish-packages": "pypi"}

    @pytest.fixture
    def workflow(self):
        return load(WORKFLOWS / "on_release.yml")

    @pytest.fixture
    def jobs(self, workflow):
        return workflow["jobs"]

    @pytest.mark.parametrize("job_id", ["version", "build-packages", "test-packages"])
    def test_the_packages_are_built_and_tested_on_their_python(self, jobs, job_id):
        assert setup_python_versions(jobs[job_id]) == [PACKAGES_PYTHON]

    def test_builds_the_wolfi_images_only(self, jobs):
        legs = jobs["build-images"]["strategy"]["matrix"]["include"]

        assert {(leg["repository"], leg["target"]) for leg in legs} == RELEASE_IMAGES
        assert len(legs) == len(RELEASE_IMAGES)

    def test_publishes_every_image_it_builds(self, jobs):
        legs = jobs["publish-images"]["strategy"]["matrix"]["include"]

        assert {leg["repository"] for leg in legs} == {
            repository for repository, _ in RELEASE_IMAGES
        }

    def test_every_image_of_both_platforms_passes_the_gate_before_any_is_published(
        self, jobs
    ):
        (gate,) = image_gate_runs(jobs["test-images"])
        names = gate.split()

        for repository, _ in RELEASE_IMAGES:
            assert f"{repository}:test" in names
            assert f"{repository}:test-arm64" in names
        report_only = [
            names[i + 1] for i, word in enumerate(names) if word == "--report-only"
        ]
        assert report_only == [
            "permitio/opal-client-eopa:test",
            "permitio/opal-client-eopa:test-arm64",
        ]

    def test_a_dry_run_reads_no_secret_variable_or_environment(self, jobs):
        """The jobs a pull request runs, from a fork too, use nothing
        stored."""
        for job_id, job in jobs.items():
            if job.get("if") == "github.event_name == 'release'":
                continue
            text = yaml.safe_dump(job)
            assert "secrets." not in text, job_id
            assert "vars." not in text, job_id
            assert "environment" not in job, job_id

    def test_a_dry_run_attaches_no_provenance(self, jobs):
        (build,) = [
            step
            for step in steps_of(jobs["build-images"])
            if step.get("uses", "").startswith("docker/build-push-action@")
        ]

        assert build["with"]["provenance"].endswith("|| 'false' }}")
        assert "github.event_name == 'release'" in build["with"]["provenance"]

    @pytest.mark.parametrize("job_id", sorted(PUBLISH_JOBS))
    def test_publishes_on_a_release_only_after_every_test(self, jobs, job_id):
        job = jobs[job_id]

        assert job["if"] == "github.event_name == 'release'"
        assert {"test-images", "test-packages"} <= set(job["needs"])
        assert environment_name(job) == self.PUBLISH_JOBS[job_id]

    def test_publishes_the_archive_it_tested_without_rebuilding(self, jobs):
        steps = steps_of(jobs["publish-images"])
        runs = "\n".join(step.get("run", "") for step in steps)

        assert 'skopeo copy --all --preserve-digests "oci-archive:$ARCHIVE"' in runs
        assert not any(
            step.get("uses", "").startswith("docker/build-push-action@")
            for step in steps
        )

    def test_runs_as_a_dry_run_on_pull_requests(self, workflow):
        # PyYAML reads the key on: as True.
        triggers = workflow[True]

        assert set(triggers) == {"release", "pull_request"}
        # What decides the release's build, its gate and its scanners' versions.
        assert {
            ".github/workflows/on_release.yml",
            ".github/scripts/image_gate.py",
            ".github/image-waivers.toml",
            ".github/binaries.lock",
            ".github/grype/**",
            "docker/**",
        } <= set(triggers["pull_request"]["paths"])

    def test_the_package_build_installs_a_pinned_setuptools(self, jobs):
        """Python 3.14 ships no setuptools, which each setup.py imports."""
        (build,) = [
            step["run"]
            for step in steps_of(jobs["build-packages"])
            if "setup.py sdist" in step.get("run", "")
        ]

        assert re.search(r"^\s*pip install .*\bsetuptools==\d", build, re.MULTILINE)

    def test_only_the_pypi_environment_publishes_to_pypi(self, jobs):
        publishers = {
            job_id
            for job_id, job in jobs.items()
            if any(
                step.get("uses", "").startswith("pypa/gh-action-pypi-publish@")
                for step in steps_of(job)
            )
        }

        assert publishers == {"publish-packages"}

    def test_publishes_to_pypi_with_trusted_publishing(self, jobs):
        """An OIDC token of the pypi environment, never a stored PyPI token."""
        job = jobs["publish-packages"]
        publish_steps = [
            step
            for step in steps_of(job)
            if step.get("uses", "").startswith("pypa/gh-action-pypi-publish@")
        ]

        assert job["permissions"]["id-token"] == "write"
        assert publish_steps
        for step in publish_steps:
            assert "password" not in step.get("with", {})
        text = (WORKFLOWS / "on_release.yml").read_text()
        assert "PYPI_TOKEN" not in text
        assert "use-trusted-publishing" not in text

    def test_the_pypi_token_job_runs_nothing_but_the_publish_action(self, jobs):
        """Every step of a job with id-token: write can mint the token PyPI accepts."""
        job = jobs["publish-packages"]

        assert job["permissions"] == {"id-token": "write"}
        for step in steps_of(job):
            assert "run" not in step, step
            assert step["uses"].startswith(
                ("actions/download-artifact@", "pypa/gh-action-pypi-publish@")
            ), step

    def test_the_release_assets_job_writes_the_release_without_an_oidc_token(
        self, jobs
    ):
        job = jobs["release-assets"]

        assert job["if"] == "github.event_name == 'release'"
        assert {"test-images", "test-packages"} <= set(job["needs"])
        assert job["permissions"] == {"contents": "write"}
        assert "environment" not in job
