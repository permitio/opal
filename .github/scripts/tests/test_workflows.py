"""Facts about .github/workflows that the repository relies on: permissions,
pinned actions, checkouts without stored credentials, the jobs the CI check
needs, the Python that CI and the release run on, the release's jobs and
environments, the Slack notices, and the code owners in .github/CODEOWNERS.

A change that breaks one of them fails here. A deliberate change, such
as a new job or a new write permission, also edits the fact pinned here.
"""

import os
import re
from fnmatch import fnmatch
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
    "git-cli-in-image",
    "e2e-scopes",
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
    ("on_release.yml", "publish-images", "id-token"),
    ("rebuild_images.yml", "publish", "id-token"),
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
        assert set(jobs["ci"]["needs"]) == set(jobs) - {"ci", "notify"}

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

    def test_the_e2e_job_runs_on_the_packages_python(self, jobs):
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


class TestE2e:
    """tests.yml: the E2E job runs the pytest suite in app-tests on the stack's
    own git server, with no secret."""

    @pytest.fixture
    def job(self):
        return load(WORKFLOWS / "tests.yml")["jobs"]["e2e-tests"]

    def test_installs_the_suite_from_its_hashed_requirements(self, job):
        assert any(
            "pip install --require-hashes -r app-tests/requirements.txt"
            in step.get("run", "")
            for step in steps_of(job)
        )

    def test_runs_the_whole_suite_on_the_images_it_built(self, job):
        (suite,) = [
            step
            for step in steps_of(job)
            if step.get("run", "").startswith("python -m pytest")
        ]

        assert suite["run"].strip() == "python -m pytest"
        assert suite["working-directory"] == "app-tests"
        assert suite["env"] == {"OPAL_IMAGE_TAG": "test"}
        # It runs on every event, and after a failed image gate, but never after a cancel.
        assert suite["if"] == (
            "${{ !cancelled() && (success() || steps.gate.outcome == 'failure') }}"
        )

    def test_no_step_sees_a_secret(self, job):
        assert "secrets." not in str(job)


class TestE2eGithub:
    """e2e-github.yml: the E2E suite's policy repo tests with the repo on
    github.com over SSH, where the deploy key's secret is set, outside the
    required checks."""

    WORKFLOW = "e2e-github.yml"
    DEPLOY_KEY = "${{ secrets.OPAL_TESTS_POLICY_REPO_DEPLOY_KEY }}"

    @pytest.fixture
    def jobs(self):
        return load(WORKFLOWS / self.WORKFLOW)["jobs"]

    def test_is_not_a_required_check(self, jobs):
        assert self.WORKFLOW not in REQUIRED_CHECKS
        assert not set(jobs) & set(load(WORKFLOWS / "tests.yml")["jobs"])

    def test_runs_only_when_the_deploy_key_is_set(self, jobs):
        (check,) = steps_of(jobs["deploy-key"])
        lane = jobs["e2e-github-ssh"]

        assert check["env"] == {"DEPLOY_KEY": self.DEPLOY_KEY}
        assert jobs["deploy-key"]["outputs"] == {
            "present": "${{ steps.check.outputs.present }}"
        }
        assert lane["needs"] == "deploy-key"
        assert lane["if"] == "needs.deploy-key.outputs.present == 'true'"

    def test_runs_the_policy_repo_tests_on_the_images_it_built(self, jobs):
        steps = steps_of(jobs["e2e-github-ssh"])
        builds = {
            step["with"]["target"]: step["with"]["tags"].strip()
            for step in steps
            if step.get("uses", "").startswith("docker/build-push-action@")
        }
        (suite,) = [
            step for step in steps if step.get("run", "").startswith("python -m pytest")
        ]

        assert builds == {
            "client": "permitio/opal-client:test",
            "server": "permitio/opal-server:test",
        }
        assert suite["run"].strip() == (
            "python -m pytest --policy-repo=github -m policy_repo"
        )
        assert suite["working-directory"] == "app-tests"
        assert suite["env"] == {
            "OPAL_IMAGE_TAG": "test",
            "OPAL_TESTS_POLICY_REPO_DEPLOY_KEY": self.DEPLOY_KEY,
        }

    def test_only_the_key_check_and_the_tests_see_the_key(self, jobs):
        workflow = load(WORKFLOWS / self.WORKFLOW)
        readers = [
            (job_id, step.get("id", step.get("name")))
            for job_id, job in jobs.items()
            for step in steps_of(job)
            if "secrets." in str(step)
        ]

        assert "secrets." not in str(workflow.get("env"))
        assert all("env" not in job for job in jobs.values())
        assert readers == [
            ("deploy-key", "check"),
            ("e2e-github-ssh", "E2E tests, policy repo on GitHub over SSH"),
        ]


class TestGitCliInImage:
    """tests.yml: the git command-line tests run in the server image, under its
    sh, git and ssh."""

    TESTS = PACKAGES / "opal-server" / "opal_server" / "tests"
    DOCKERFILE = WORKFLOWS.parents[1] / "docker" / "Dockerfile"

    @pytest.fixture
    def job(self):
        return load(WORKFLOWS / "tests.yml")["jobs"]["git-cli-in-image"]

    @pytest.fixture
    def command(self, job):
        (run,) = [
            step["run"] for step in steps_of(job) if "docker run" in step.get("run", "")
        ]
        return run.split()

    def test_builds_the_server_test_target(self, job):
        (build,) = [
            step["with"]
            for step in steps_of(job)
            if step.get("uses", "").startswith("docker/build-push-action@")
        ]

        assert build["target"] == "server-test"
        assert build["push"] is False
        assert build["load"] is True

    def test_runs_the_tests_from_the_checkout_offline_with_sshd_required(self, command):
        assert command[:4] == ["docker", "run", "--rm", "--init"]
        # As the image's user, not root, for whom the permission tests skip themselves.
        assert "--user 1000:1000" in " ".join(command)
        assert "--network none" in " ".join(command)
        assert "TESTS_REQUIRE_SSHD=1" in command
        assert '"$PWD:/src:ro"' in command

    def test_a_build_with_no_target_is_still_the_server_image(self):
        """Docker builds the last stage when it gets no --target, and server-
        test comes after the server stage it builds on."""
        lines = [line.strip() for line in self.DOCKERFILE.read_text().splitlines()]
        last = max(i for i, line in enumerate(lines) if line.startswith("FROM "))

        assert lines[last] == "FROM server"
        assert all(not line or line.startswith("#") for line in lines[last + 1 :])

    def test_installs_pytest_from_hashed_requirements(self):
        assert (
            "pip install --no-cache-dir --require-hashes -r /tmp/server-test-requirements.txt"
            in self.DOCKERFILE.read_text()
        )

    def test_runs_every_git_cli_test_file(self, command):
        files = {Path(arg).name for arg in command if arg.endswith("_test.py")}
        git_cli = {path.name for path in self.TESTS.glob("git_cli*_test.py")}

        assert git_cli, "no git_cli*_test.py under opal_server/tests"
        assert git_cli <= files
        assert {
            "git_config_isolation_test.py",
            "git_repack_test.py",
            "default_fetch_backend_test.py",
            "git_host_keys_test.py",
        } <= files
        for name in files:
            assert (self.TESTS / name).is_file(), name


class TestImageLock:
    """The images install their Python packages from the hashed lock
    docker/lock/requirements.txt, which one Dependabot entry updates."""

    ROOT = WORKFLOWS.parents[1]
    DOCKERFILE = ROOT / "docker" / "Dockerfile"

    @pytest.fixture
    def code(self):
        """The lines of docker/Dockerfile that are not comments."""
        lines = self.DOCKERFILE.read_text().splitlines()
        return [line.strip() for line in lines if not line.lstrip().startswith("#")]

    def test_pip_installs_only_the_lock_and_the_test_requirements(self, code):
        installs = [re.search(r"pip install [^&]*", line) for line in code]

        assert [m.group().strip() for m in installs if m] == [
            "pip install --no-cache-dir --require-hashes --no-deps --only-binary :all:"
            " -r ./requirements.txt",
            "pip install --no-cache-dir --require-hashes -r /tmp/server-test-requirements.txt",
        ]
        assert "COPY docker/lock/requirements.txt ./requirements.txt" in code

    def test_pip_check_follows_every_opal_package_install(self, code):
        installs = [line for line in code if "setup.py install" in line]

        assert len(installs) == 3
        for line in installs:
            assert line.endswith("python setup.py install && pip check")


class TestUvLocks:
    """Each lock that uv pip compile writes has one Dependabot entry, of the uv
    ecosystem, and a pip-compile hook that compiles it again with the command
    its header records."""

    ROOT = WORKFLOWS.parents[1]
    HEADER = "# This file was autogenerated by uv via the following command:"
    LOCKS = {
        "docker/lock/requirements.txt",
        "docker/server-test/requirements.txt",
        "app-tests/requirements.txt",
        "app-tests/git-leak/requirements.txt",
        ".github/scripts/tests/requirements.txt",
    }

    @pytest.fixture
    def locks(self):
        """The locks in the checkout, as paths from the repository root."""
        found = set()
        skipped = ("node_modules", "venv", "bin")
        for top, dirs, files in os.walk(self.ROOT):
            hidden = [d for d in dirs if d.startswith((".", "_")) and d != ".github"]
            dirs[:] = [d for d in dirs if d not in skipped and d not in hidden]
            for name in files:
                path = Path(top) / name
                if name.endswith(".txt"):
                    with path.open(errors="replace") as file:
                        if file.readline().rstrip("\n") == self.HEADER:
                            found.add(path.relative_to(self.ROOT).as_posix())
        return found

    @pytest.fixture
    def updates(self):
        return load(self.ROOT / ".github" / "dependabot.yml")["updates"]

    def test_finds_every_lock(self, locks):
        assert locks == self.LOCKS

    def test_one_dependabot_entry_owns_each_lock_and_it_is_uv(self, updates):
        """Dependabot's pip and uv fetchers read a directory and its immediate
        subdirectories; exclude-paths drops what it matches."""
        for lock in self.LOCKS:
            lock_dir = str(Path(lock).parent)
            owners = []
            for update in updates:
                if update["package-ecosystem"] not in ("pip", "uv"):
                    continue
                excluded = any(
                    fnmatch(lock, p) for p in update.get("exclude-paths", [])
                )
                for directory in update.get("directories", [update.get("directory")]):
                    directory = directory.strip("/") or "."
                    reached = directory in (lock_dir, str(Path(lock_dir).parent))
                    if reached and not excluded:
                        owners.append((update["package-ecosystem"], directory))

            assert [ecosystem for ecosystem, _ in owners] == ["uv"], (lock, owners)

    def test_the_images_lock_moves_only_inside_the_ranges(self, updates):
        (entry,) = [u for u in updates if u.get("directory") == "/docker/lock"]

        assert entry["versioning-strategy"] == "lockfile-only"

    def test_a_hook_compiles_each_lock_with_its_header_command(self):
        config = load(self.ROOT / ".pre-commit-config.yaml")
        hooks = [
            hook
            for repo in config["repos"]
            for hook in repo["hooks"]
            if hook["id"] == "pip-compile"
        ]
        for lock in self.LOCKS:
            source = lock.removesuffix(".txt") + ".in"
            (hook,) = [h for h in hooks if re.search(h["files"], lock)]
            command = (self.ROOT / lock).read_text().splitlines()[1]

            assert re.search(hook["files"], source), lock
            assert command == "#    uv pip compile " + " ".join(hook["args"]), lock

    def test_the_workflow_scripts_tests_run_on_the_packages_python(self):
        job = load(WORKFLOWS / "pre-commit.yml")["jobs"]["pre-commit"]
        (versions,) = setup_python_versions(job)
        (tests,) = [
            step["run"] for step in steps_of(job) if "pytest" in step.get("run", "")
        ]

        assert versions.split()[-1] == f"{PACKAGES_PYTHON}.x"
        assert f'--python {PACKAGES_PYTHON} "$venv"' in tests


class TestE2eScopes:
    """tests.yml: the scope bed runs on each fetch backend, set explicitly by
    an override file."""

    BED = WORKFLOWS.parents[1] / "app-tests" / "git-leak"

    @pytest.fixture
    def job(self):
        return load(WORKFLOWS / "tests.yml")["jobs"]["e2e-scopes"]

    @pytest.fixture
    def run(self, job):
        (step,) = [
            step
            for step in steps_of(job)
            if step.get("run", "").startswith("python -m pytest")
        ]
        return step

    def test_runs_a_leg_per_backend(self, job):
        assert job["strategy"]["matrix"] == {"backend": ["libgit2", "cli"]}
        assert job["strategy"]["fail-fast"] is False

    def test_each_leg_sets_its_backend_with_its_override_file(self, run):
        assert run["working-directory"] == "app-tests/git-leak"
        assert run["env"]["COMPOSE_FILE"] == (
            "docker-compose.yml:docker-compose.${{ matrix.backend }}.yml"
        )
        for backend in ("libgit2", "cli"):
            assert (self.BED / f"docker-compose.{backend}.yml").is_file()

    def test_runs_the_backend_check(self, run):
        assert "test_backend.py" in run["run"].split()

    def test_installs_the_bed_from_its_hashed_requirements(self, job):
        assert any(
            "pip install --require-hashes -r app-tests/git-leak/requirements.txt"
            in step.get("run", "")
            for step in steps_of(job)
        )


class TestRelease:
    """on_release.yml: built once, gated and tested, then the same bytes
    published from protected environments; a dry run on pull requests."""

    PUBLISH_JOBS = {"publish-images": "docker-hub", "publish-packages": "pypi"}
    RELEASE_ONLY = {"publish-images", "release-assets", "publish-packages", "verify"}

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
            # A job runs on a release only when its condition requires the release event.
            if re.search(
                r"(^|&& )github\.event_name == 'release'( &&|$)", job.get("if", "")
            ):
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

        assert "skopeo copy --all --preserve-digests" in runs
        assert '"oci-archive:$ARCHIVE" "docker://$REPOSITORY:$tag"' in runs
        assert not any(
            step.get("uses", "").startswith("docker/build-push-action@")
            for step in steps
        )

    def test_only_the_publish_and_verify_jobs_skip_a_dry_run(self, jobs):
        release_only = {
            job_id
            for job_id, job in jobs.items()
            if job.get("if") == "github.event_name == 'release'"
        }

        assert release_only == self.RELEASE_ONLY

    def test_release_images_carry_provenance_and_an_sbom(self, jobs):
        (build,) = [
            step
            for step in steps_of(jobs["build-images"])
            if step.get("uses", "").startswith("docker/build-push-action@")
        ]

        assert build["with"]["provenance"] == (
            "${{ github.event_name == 'release' && 'mode=max' || 'false' }}"
        )
        assert build["with"]["sbom"] == "${{ github.event_name == 'release' }}"

    def test_verifies_what_was_published(self, jobs):
        job = jobs["verify"]
        runs = "\n".join(step.get("run", "") for step in steps_of(job))

        assert {"publish-images", "publish-packages"} <= set(job["needs"])
        assert 'verify_release.py image "permitio/opal-$name@sha256:$digest"' in runs
        for _, target in RELEASE_IMAGES:
            assert target in runs
        assert "verify_release.py packages" in runs
        for project in ("opal-common", "opal-client", "opal-server"):
            assert f"--project {project}" in runs

    def test_the_digest_each_image_was_pushed_as_reaches_verify(self, jobs):
        publish = steps_of(jobs["publish-images"])
        (upload,) = [
            step
            for step in publish
            if step.get("uses", "").startswith("actions/upload-artifact@")
        ]
        (download,) = [
            step
            for step in steps_of(jobs["verify"])
            if step.get("uses", "").startswith("actions/download-artifact@")
        ]

        assert upload["with"]["name"] == "digest-${{ matrix.name }}"
        assert download["with"]["pattern"] == "digest-*"

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


def test_no_workflow_reads_a_stored_docker_hub_credential():
    """Docker Hub tokens come from OIDC only; builds and scans pull
    anonymously."""
    for path in WORKFLOW_FILES:
        assert "DOCKERHUB_TOKEN" not in path.read_text(), path.name
        assert "DOCKERHUB_USERNAME" not in path.read_text(), path.name


def test_only_the_image_publish_job_logs_in_to_docker_hub_and_through_oidc():
    logins = [
        (path.name, job_id, step)
        for path, (job_id, job) in (
            (path, item)
            for path in WORKFLOW_FILES
            for item in load(path)["jobs"].items()
        )
        for step in steps_of(job)
        if step.get("uses", "").startswith("docker/login-action@")
    ]

    assert {(name, job_id) for name, job_id, _ in logins} == {
        ("on_release.yml", "publish-images"),
        ("rebuild_images.yml", "publish"),
    }
    for _, _, login in logins:
        assert "password" not in login["with"]
        assert login["with"]["username"] == "${{ vars.DOCKERHUB_ORGANIZATION }}"
        assert login["env"]["DOCKERHUB_OIDC_CONNECTIONID"] == (
            "${{ vars.DOCKERHUB_OIDC_CONNECTIONID }}"
        )


# The jobs that post a failure to Slack, per workflow: the condition they run on. Each runs
# .github/scripts/notify.sh with the webhook of the security-scan environment.
NOTIFY_CONDITIONS = {
    "tests.yml": (
        "always() && github.event_name == 'push' && github.ref == 'refs/heads/master'"
        " && needs.ci.result != 'success'"
    ),
    "pre-commit.yml": (
        "always() && github.event_name == 'push' && github.ref == 'refs/heads/master'"
        " && needs.pre-commit.result != 'success'"
    ),
    "on_release.yml": (
        "always() && github.event_name == 'release'"
        " && (contains(needs.*.result, 'failure') || contains(needs.*.result, 'cancelled'))"
    ),
    "rebuild_images.yml": (
        "always() && !inputs.dry-run"
        " && (contains(needs.*.result, 'failure') || contains(needs.*.result, 'cancelled'))"
    ),
}


@pytest.mark.parametrize(("file_name", "condition"), NOTIFY_CONDITIONS.items())
def test_a_failed_gate_on_master_or_a_failed_release_reaches_slack(
    file_name, condition
):
    jobs = load(WORKFLOWS / file_name)["jobs"]
    notify = jobs["notify"]
    runs = [step.get("run", "") for step in steps_of(notify)]

    assert notify["if"] == condition
    assert environment_name(notify) == "security-scan"
    assert notify["permissions"] == {"contents": "read"}
    assert any(".github/scripts/notify.sh" in run for run in runs)
    # tests.yml and pre-commit.yml: the required check's job; on_release.yml: every job.
    expected = {"tests.yml": {"ci"}, "pre-commit.yml": {"pre-commit"}}
    assert set(notify["needs"]) == expected.get(file_name, set(jobs) - {"notify"})


def codeowners_rules() -> list[tuple[str, list[str]]]:
    """The rules of .github/CODEOWNERS, in order: (pattern, owners)."""
    text = (WORKFLOWS.parent / "CODEOWNERS").read_text()
    rules = []
    for line in text.splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            pattern, *owners = line.split()
            rules.append((pattern, owners))
    return rules


def test_codeowners_cover_the_repository_and_hold_github_tighter():
    """The catch-all comes first, since the last matching rule wins; the CI and
    release automation has a narrower set of owners than the rest."""
    rules = codeowners_rules()
    owners = dict(rules)

    assert rules[0] == ("*", ["@permitio/r-d"])
    for pattern in ("/.github/", "/.pre-commit-config.yaml", "/.gitleaks.toml"):
        assert owners[pattern], pattern
        assert "@permitio/r-d" not in owners[pattern], pattern
    assert all(owner.startswith("@") for _, found in rules for owner in found)


class TestRebuild:
    """rebuild_images.yml: the latest GA release's images with their Wolfi
    packages upgraded, through the release's build, gate, publish and verify
    path."""

    @pytest.fixture
    def workflow(self):
        return load(WORKFLOWS / "rebuild_images.yml")

    @pytest.fixture
    def jobs(self, workflow):
        return workflow["jobs"]

    def test_runs_weekly_and_by_hand(self, workflow):
        triggers = workflow[True]

        assert set(triggers) == {"schedule", "workflow_dispatch"}
        assert set(triggers["workflow_dispatch"]["inputs"]) == {"tag", "dry-run"}

    def test_builds_an_overlay_of_the_release_image_with_attestations(self, jobs):
        (build,) = [
            step
            for step in steps_of(jobs["build"])
            if step.get("uses", "").startswith("docker/build-push-action@")
        ]

        assert build["with"]["file"] == ".github/rebuild/Dockerfile"
        assert build["with"]["target"] == "rebuild"
        assert build["with"]["no-cache"] is True
        assert build["with"]["provenance"] == "mode=max"
        assert build["with"]["sbom"] is True
        legs = jobs["build"]["strategy"]["matrix"]["include"]
        assert {leg["repository"] for leg in legs} == {
            repository for repository, _ in RELEASE_IMAGES
        }

    def test_every_image_of_both_platforms_passes_the_gate_before_any_is_published(
        self, jobs
    ):
        (gate,) = image_gate_runs(jobs["test"])
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
        assert "test" in jobs["publish"]["needs"]

    def test_publishes_like_the_release_never_at_the_same_time(self, jobs):
        release = load(WORKFLOWS / "on_release.yml")["jobs"]["publish-images"]
        publish = jobs["publish"]

        assert publish["if"] == "${{ !inputs.dry-run }}"
        assert environment_name(publish) == "docker-hub"
        assert publish["concurrency"] == release["concurrency"]
        assert publish["concurrency"]["cancel-in-progress"] is False
        runs = "\n".join(step.get("run", "") for step in steps_of(publish))
        assert 'for tag in "$TAG-$DATE" "$TAG" latest; do' in runs
        assert "skopeo copy --all --preserve-digests" in runs

    def test_verifies_what_it_published(self, jobs):
        runs = "\n".join(step.get("run", "") for step in steps_of(jobs["verify"]))

        assert "publish" in jobs["verify"]["needs"]
        assert 'verify_release.py image "permitio/opal-$name@sha256:$digest"' in runs
        assert "--target rebuild" in runs
        (upload,) = [
            step
            for step in steps_of(jobs["publish"])
            if step.get("uses", "").startswith("actions/upload-artifact@")
        ]
        assert upload["with"]["name"] == "digest-${{ matrix.name }}"


def test_the_overlay_keeps_the_release_and_labels_it():
    dockerfile = (WORKFLOWS.parent / "rebuild" / "Dockerfile").read_text()

    assert "FROM ${RELEASE_IMAGE} AS rebuild" in dockerfile
    assert (
        "RUN sed -i -E 's/[<>~=].*//' /etc/apk/world && apk upgrade --no-cache && \\\n"
        "  python /opal/check_trust_store.py\n"
    ) in dockerfile
    assert 'LABEL ac.opal.rebuilt-from="${RELEASE_IMAGE}"' in dockerfile
    assert dockerfile.rstrip().endswith("USER opal")


_PROPERTY = re.compile(r"\b[a-z_]+(?:\.(?:[a-z_]+|\*))+")


def _lookup(value, keys: list[str]):
    """A property of a context, with GitHub's .* filter over a list; a missing
    property is null."""
    for index, key in enumerate(keys):
        if key == "*":
            return [_lookup(item, keys[index + 1 :]) for item in value or []]
        value = value.get(key) if isinstance(value, dict) else None
    return value


def evaluate(expression: str, context: dict):
    """The value of a GitHub Actions expression, for the subset mutation.yml
    uses: properties, string literals, ==, !=, &&, ||, parentheses and
    contains() on a list. A value that is one ${{ }} is its expression's value,
    and a value with other text around its ${{ }} parts is a string."""
    whole = re.fullmatch(r"\s*\$\{\{(.*?)\}\}\s*", expression, flags=re.S)
    if whole and "${{" not in whole[1]:
        return evaluate(whole[1], context)
    if "${{" in expression:
        parts = re.split(r"\$\{\{(.*?)\}\}", expression, flags=re.S)
        return "".join(
            str(evaluate(part, context)) if odd else part
            for odd, part in zip([False, True] * len(parts), parts)
        )
    python = _PROPERTY.sub(
        lambda found: f"lookup(context, {found[0].split('.')!r})", expression
    )
    python = python.replace("&&", " and ").replace("||", " or ")
    # Only the workflow's own expressions reach here, in this subset of the syntax.
    return eval(  # noqa: S307
        " ".join(python.split()),
        {
            "lookup": _lookup,
            "context": context,
            "contains": lambda items, item: item in items,
        },
    )


def mutation_event(event_name: str, action: str = "", labels=(), label: str = ""):
    """The github context of a run of mutation.yml: on pull request 7 for a
    pull_request event."""
    pull_request = event_name == "pull_request"
    event: dict = {}
    if pull_request:
        event = {
            "action": action,
            "pull_request": {"labels": [{"name": name} for name in labels]},
        }
        if label:
            event["label"] = {"name": label}
    return {
        "github": {
            "workflow": "Mutation",
            "event_name": event_name,
            "event": event,
            "ref": "refs/pull/7/merge" if pull_request else "refs/heads/master",
            "run_id": "1234",
        }
    }


class TestMutation:
    """mutation.yml: the capped gate on the lines of a pull request that
    carries the label "mutation", and the weekly full run."""

    @pytest.fixture
    def workflow(self):
        return load(WORKFLOWS / "mutation.yml")

    def test_runs_on_pull_requests_that_change_package_code_and_weekly(self, workflow):
        triggers = workflow[True]

        assert set(triggers) == {"pull_request", "schedule", "workflow_dispatch"}
        assert triggers["pull_request"]["paths"] == ["packages/**/*.py"]
        assert set(triggers["pull_request"]["types"]) == {
            "opened",
            "synchronize",
            "reopened",
            "labeled",
        }

    @pytest.mark.parametrize(
        ("context", "runs", "group"),
        [
            pytest.param(
                mutation_event("pull_request", "labeled", ["mutation"], "mutation"),
                True,
                "Mutation-refs/pull/7/merge",
                id="the label added",
            ),
            pytest.param(
                mutation_event("pull_request", "synchronize", ["bug", "mutation"]),
                True,
                "Mutation-refs/pull/7/merge",
                id="a push with the label",
            ),
            pytest.param(
                mutation_event("pull_request", "opened", ["mutation"]),
                True,
                "Mutation-refs/pull/7/merge",
                id="opened with the label",
            ),
            pytest.param(
                mutation_event("pull_request", "reopened", ["mutation"]),
                True,
                "Mutation-refs/pull/7/merge",
                id="reopened with the label",
            ),
            pytest.param(
                mutation_event("pull_request", "synchronize", ["bug"]),
                False,
                "Mutation-refs/pull/7/merge",
                id="a push without the label",
            ),
            pytest.param(
                mutation_event("pull_request", "opened"),
                False,
                "Mutation-refs/pull/7/merge",
                id="opened without the label",
            ),
            pytest.param(
                mutation_event("pull_request", "labeled", ["mutation", "bug"], "bug"),
                False,
                "Mutation-1234",
                id="another label added beside it",
            ),
            pytest.param(
                mutation_event("pull_request", "labeled", ["bug"], "bug"),
                False,
                "Mutation-1234",
                id="another label added alone",
            ),
            pytest.param(
                mutation_event("schedule"), True, "Mutation-1234", id="weekly"
            ),
            pytest.param(
                mutation_event("workflow_dispatch"), True, "Mutation-1234", id="by hand"
            ),
        ],
    )
    def test_a_pull_request_runs_only_with_the_label_and_another_label_cancels_nothing(
        self, workflow, context, runs, group
    ):
        concurrency = workflow["concurrency"]
        pull_request = context["github"]["event_name"] == "pull_request"

        assert bool(evaluate(workflow["jobs"]["mutation"]["if"], context)) is runs
        assert evaluate(concurrency["group"], context) == group
        assert evaluate(concurrency["cancel-in-progress"], context) is pull_request

    def test_the_full_run_reports_with_the_scripts_own_exit_code(self, workflow):
        (step,) = [
            step
            for step in steps_of(workflow["jobs"]["mutation"])
            if step.get("if") == "github.event_name != 'pull_request'"
        ]

        assert step["run"] == (
            '.github/scripts/mutation_gate.py --full --summary "$GITHUB_STEP_SUMMARY"'
        )

    @pytest.mark.parametrize(
        ("gate_exit", "step_exit"), [(0, 0), (1, 1), (2, 2), (3, 0), (143, 143)]
    )
    def test_a_pull_request_step_passes_an_inconclusive_gate_with_a_warning(
        self, workflow, throwaway_repo, gate_exit, step_exit
    ):
        """The step runs the gate on the pull request's base; exit 3,
        inconclusive, passes the step with a warning annotation, and every
        other exit code is the step's own."""
        (step,) = [
            step
            for step in steps_of(workflow["jobs"]["mutation"])
            if step.get("if") == "github.event_name == 'pull_request'"
        ]
        assert step["env"] == {"BASE": "${{ github.event.pull_request.base.sha }}"}
        throwaway_repo.write(
            ".github/scripts/mutation_gate.py",
            f'#!/usr/bin/env bash\necho "gate: $*"\nexit {gate_exit}\n',
            executable=True,
        )
        throwaway_repo.write("step.sh", step["run"])
        shell = workflow["defaults"]["run"]["shell"].replace("{0}", "step.sh")
        throwaway_repo.write(
            "run-step.sh", f"#!/usr/bin/env bash\nexec {shell}\n", executable=True
        )

        result = throwaway_repo.run(
            "run-step.sh", env={"BASE": "abc123", "GITHUB_STEP_SUMMARY": "summary.md"}
        )

        assert result.returncode == step_exit, result.output
        assert "gate: --base abc123 --summary summary.md" in result.stdout
        warnings = [
            line for line in result.stdout.splitlines() if line.startswith("::warning")
        ]
        if gate_exit == 3:
            assert warnings == [
                "::warning title=Mutation testing inconclusive::The budget left more than a "
                "quarter of the sampled mutants not run, so the score is no verdict. The job "
                "summary says how many ran."
            ]
        else:
            assert warnings == []

    def test_installs_the_coverage_tools_the_script_tests_pin(self, workflow):
        pinned = (
            WORKFLOWS.parent / "scripts" / "tests" / "requirements.in"
        ).read_text()
        (install,) = [
            step["run"]
            for step in steps_of(workflow["jobs"]["mutation"])
            if "pytest-cov==" in step.get("run", "")
        ]

        for tool in re.findall(r"(?:pytest-cov|coverage)==[\d.]+", install):
            assert tool in pinned

    def test_installs_the_opa_the_unit_tests_use(self, workflow):
        """Without it the inline-OPA tests skip, and their lines look
        uncovered."""
        tests = load(WORKFLOWS / "tests.yml")["jobs"]["build"]
        mutation = workflow["jobs"]["mutation"]

        def opa(job):
            (step,) = [
                s for s in steps_of(job) if s.get("name", "").startswith("Install OPA")
            ]
            return step

        assert opa(mutation)["run"] == opa(tests)["run"]
        assert opa(mutation)["env"] == opa(tests)["env"]
