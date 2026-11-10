"""Tests of .github/scripts/digest.sh: the digest's three sections, what needs
attention, its exit codes and failure paths, and where its secrets go.

Each test runs the script in a throwaway copy of the repository with a
.github/binaries.lock of its own. A fake gh answers each API path with
JSON the test writes, a fake notify.sh records what it would post, and a
fake curl fails, so no test uses the network. The tests of a missing or
non-https webhook run the real notify.sh, which does not post in those
cases.
"""

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

SCRIPT = ".github/scripts/digest.sh"
NOTIFY = ".github/scripts/notify.sh"
REPO = "example/opal"
NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
GH_TOKEN = "gh-token-for-tests"
WEBHOOK = "https://hooks.example.invalid/services/webhook-for-tests"
RUNS = f"repos/{REPO}/actions/workflows/security.yml/runs?branch=master&event={{}}&per_page=30"
LOCK = """\
# The release binaries, as .github/binaries.lock lists them.

[alpha]
version = 1.2.3
url = https://github.com/example-org/alpha/releases/download/v{version}/alpha.tar.gz
archive = tar.gz
"""

# The fake gh logs the token and the webhook it was given and its arguments, then prints the
# reply the test wrote for the API path, or fails like gh on a 404.
FAKE_GH = r"""set -euo pipefail
printf '%s\t%s\t%s\t%s\n' "${GH_TOKEN-unset}" "${GITHUB_TOKEN-unset}" \
  "${SECURITY_SLACK_WEBHOOK_URL-unset}" "$*" >>"$FAKE_GH_LOG"
if [[ ${1:-} != api ]]; then
  echo "fake gh: only gh api is faked" >&2
  exit 1
fi
shift
if [[ ${1:-} == --paginate ]]; then
  shift
fi
reply=$FAKE_GH_DIR/$(printf '%s' "$1" | tr -c 'A-Za-z0-9' '_')
if [[ ! -f $reply ]]; then
  echo "gh: Not Found (HTTP 404): $1" >&2
  exit 1
fi
cat -- "$reply"
"""

FAKE_NOTIFY = r"""#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$@" >"$FAKE_NOTIFY_DIR/args"
printf 'webhook=%s\ngh_token=%s\ngithub_token=%s\n' "${SECURITY_SLACK_WEBHOOK_URL-unset}" \
  "${GH_TOKEN-unset}" "${GITHUB_TOKEN-unset}" >"$FAKE_NOTIFY_DIR/env"
cp -- "$3" "$FAKE_NOTIFY_DIR/body"
echo "::notice::fake notify ran"
exit "${FAKE_NOTIFY_EXIT:-0}"
"""

FAKE_CURL = r"""printf '%s\n' "$*" >>"$FAKE_CURL_LOG"
echo "fake curl: the tests use no network" >&2
exit 7
"""


def iso(days_ago: float) -> str:
    """The time some days before NOW, as GitHub's API writes times."""
    return (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def pull(
    number: int, days_ago: float, login: str = "dependabot[bot]", title: str = ""
) -> dict:
    return {
        "number": number,
        "title": title or f"Bump package {number}",
        "html_url": f"https://github.com/{REPO}/pull/{number}",
        "created_at": iso(days_ago),
        "user": {"login": login},
    }


def run_of(run_id: int, event: str, days_ago: float) -> dict:
    return {"id": run_id, "event": event, "created_at": iso(days_ago)}


def job(
    run_id: int, name: str = "security-scan", conclusion: str | None = "success"
) -> dict:
    return {
        "name": name,
        "conclusion": conclusion,
        "html_url": f"https://github.com/{REPO}/actions/runs/{run_id}/job/{run_id}0",
        "completed_at": iso(1) if conclusion else None,
    }


def release(
    tag: str, days_ago: float, draft: bool = False, prerelease: bool = False
) -> dict:
    return {
        "tag_name": tag,
        "draft": draft,
        "prerelease": prerelease,
        "published_at": iso(days_ago),
    }


def sections(body: str) -> dict[str, list[str]]:
    """Split a digest into its sections: each title, without its stars, and its lines."""
    found: dict[str, list[str]] = {}
    title = ""
    for line in body.splitlines():
        if line.startswith("*") and line.endswith("*"):
            title = line.strip("*")
            found[title] = []
        else:
            found[title].append(line)
    return found


class Digest:
    """A throwaway repository with digest.sh, a fake gh, a fake notify.sh and a
    fake curl.

    It starts with replies in which nothing needs attention: a Dependabot pull request 3 days old,
    a security scan that succeeded a day ago, and alpha at its newest release.
    """

    def __init__(self, repo, tmp_path: Path) -> None:
        self.repo = repo
        self.gh_dir = tmp_path / "gh"
        self.gh_dir.mkdir()
        self.gh_log = tmp_path / "gh.log"
        self.curl_log = tmp_path / "curl.log"
        self.notify_dir = tmp_path / "notify"
        self.notify_dir.mkdir()
        self.summary = tmp_path / "summary.md"
        repo.copy(SCRIPT)
        repo.write(NOTIFY, FAKE_NOTIFY, executable=True)
        repo.write(".github/binaries.lock", LOCK)
        repo.stub("gh", FAKE_GH)
        repo.stub("curl", FAKE_CURL)
        self.pulls([pull(7, 3), pull(9, 30, login="someone")])
        self.runs("schedule", [run_of(101, "schedule", 1)])
        self.runs("workflow_dispatch", [])
        self.jobs(101, [job(101, name="digest", conclusion="skipped"), job(101)])
        self.releases(
            "example-org/alpha", [release("v1.2.3", 40), release("v1.2.2", 80)]
        )

    def reply(self, path: str, body) -> None:
        """Set the fake gh's reply for an API path: JSON, or text as it is."""
        text = body if isinstance(body, str) else json.dumps(body)
        (self.gh_dir / re.sub(r"[^A-Za-z0-9]", "_", path)).write_text(text)

    def no_reply(self, path: str) -> None:
        """Make the fake gh fail for an API path."""
        (self.gh_dir / re.sub(r"[^A-Za-z0-9]", "_", path)).unlink()

    def pulls(self, *pages: list[dict]) -> None:
        self.reply(
            f"repos/{REPO}/pulls?state=open&per_page=100",
            "".join(json.dumps(page) for page in pages),
        )

    def runs(self, event: str, runs: list[dict]) -> None:
        self.reply(
            RUNS.format(event), {"total_count": len(runs), "workflow_runs": runs}
        )

    def jobs(self, run_id: int, jobs: list[dict]) -> None:
        self.reply(
            f"repos/{REPO}/actions/runs/{run_id}/jobs?per_page=100", {"jobs": jobs}
        )

    def releases(self, project: str, releases) -> None:
        self.reply(f"repos/{project}/releases?per_page=30", releases)

    def run(self, *args: str, **changes: str | None):
        """Run digest.sh.

        Args:
            *args: Its arguments.
            **changes: Variables to set, or to leave out with None, besides GITHUB_REPOSITORY,
                DIGEST_NOW, GH_TOKEN, SECURITY_SLACK_WEBHOOK_URL and what the fakes read.

        Returns:
            The exit code and the output.
        """
        path = changes.pop("PATH", None)
        env: dict[str, str | None] = {
            "GITHUB_REPOSITORY": REPO,
            "DIGEST_NOW": str(int(NOW.timestamp())),
            "GH_TOKEN": GH_TOKEN,
            "SECURITY_SLACK_WEBHOOK_URL": WEBHOOK,
            "FAKE_GH_DIR": str(self.gh_dir),
            "FAKE_GH_LOG": str(self.gh_log),
            "FAKE_CURL_LOG": str(self.curl_log),
            "FAKE_NOTIFY_DIR": str(self.notify_dir),
        }
        env.update(changes)
        return self.repo.run(
            SCRIPT,
            *args,
            env={k: v for k, v in env.items() if v is not None},
            path=path,
        )

    @property
    def notified(self) -> list[str] | None:
        """The arguments notify.sh ran with, or None when it did not run."""
        args = self.notify_dir / "args"
        return args.read_text().splitlines() if args.exists() else None

    @property
    def notify_env(self) -> dict[str, str]:
        lines = (self.notify_dir / "env").read_text().splitlines()
        return dict(line.split("=", 1) for line in lines)

    @property
    def body(self) -> str:
        return (self.notify_dir / "body").read_text()

    @property
    def gh_calls(self) -> list[list[str]]:
        """Each gh run: its GH_TOKEN, GITHUB_TOKEN, webhook and arguments."""
        if not self.gh_log.exists():
            return []
        return [line.split("\t") for line in self.gh_log.read_text().splitlines()]

    def use_the_real_notify(self) -> None:
        self.repo.copy(NOTIFY)


@pytest.fixture
def digest(throwaway_repo, tmp_path):
    return Digest(throwaway_repo, tmp_path)


def test_nothing_needs_attention(digest):
    result = digest.run()

    assert result.returncode == 0, result.output
    assert digest.notified is not None
    assert digest.notified[:2] == ["security digest", "nothing needs attention"]
    assert digest.body == (
        "*Dependabot pull requests*\n"
        f"• <https://github.com/{REPO}/pull/7|#7> Bump package 7: open 3 days\n"
        "*Last security scan*\n"
        f"• <https://github.com/{REPO}/actions/runs/101/job/1010|success> on 2026-11-08\n"
        "*Release binaries*\n"
        "• alpha 1.2.3 is the newest release.\n"
    )
    assert digest.body in result.stdout


def test_each_secret_reaches_only_the_command_that_needs_it(digest):
    result = digest.run(GITHUB_TOKEN="github-token-for-tests")

    assert result.returncode == 0, result.output
    assert digest.gh_calls
    for token, github_token, webhook, _ in digest.gh_calls:
        assert (token, github_token, webhook) == (GH_TOKEN, "unset", "unset")
    assert digest.notify_env == {
        "webhook": WEBHOOK,
        "gh_token": "unset",
        "github_token": "unset",
    }
    for secret in (GH_TOKEN, WEBHOOK, "github-token-for-tests"):
        assert secret not in result.output


@pytest.mark.parametrize(
    ("days", "line", "result_line"),
    [
        (13, "open 13 days", "nothing needs attention"),
        (14, "open 14 days, *14 days or more*", "1 items need attention"),
        (40.5, "open 40 days, *14 days or more*", "1 items need attention"),
    ],
)
def test_a_dependabot_pull_request_open_14_days_needs_attention(
    digest, days, line, result_line
):
    digest.pulls([pull(7, days)])

    result = digest.run()

    assert result.returncode == 0, result.output
    assert sections(digest.body)["Dependabot pull requests"] == [
        f"• <https://github.com/{REPO}/pull/7|#7> Bump package 7: {line}"
    ]
    assert digest.notified[1] == result_line


def test_lists_the_dependabot_pull_requests_of_every_page_oldest_first(digest):
    digest.pulls([pull(7, 3), pull(5, 1, login="someone")], [pull(8, 20), pull(6, 3)])

    result = digest.run()

    assert result.returncode == 0, result.output
    assert sections(digest.body)["Dependabot pull requests"] == [
        f"• <https://github.com/{REPO}/pull/8|#8> Bump package 8: open 20 days, *14 days or more*",
        f"• <https://github.com/{REPO}/pull/6|#6> Bump package 6: open 3 days",
        f"• <https://github.com/{REPO}/pull/7|#7> Bump package 7: open 3 days",
    ]
    assert digest.notified[1] == "1 items need attention"
    assert any(call[3].startswith("api --paginate repos/") for call in digest.gh_calls)


def test_no_open_dependabot_pull_request(digest):
    digest.pulls([pull(9, 30, login="someone")])

    result = digest.run()

    assert result.returncode == 0, result.output
    assert sections(digest.body)["Dependabot pull requests"] == ["• None open."]


def test_escapes_the_values_from_outside(digest):
    digest.pulls([pull(7, 3, title="Bump <x> & <!channel>")])

    result = digest.run()

    assert result.returncode == 0, result.output
    assert sections(digest.body)["Dependabot pull requests"] == [
        f"• <https://github.com/{REPO}/pull/7|#7> Bump &lt;x&gt; &amp; &lt;!channel&gt;: "
        "open 3 days"
    ]


@pytest.mark.parametrize("conclusion", ["failure", "cancelled", "timed_out"])
def test_a_security_scan_that_did_not_succeed_needs_attention(digest, conclusion):
    digest.jobs(101, [job(101, conclusion=conclusion)])

    result = digest.run()

    assert result.returncode == 0, result.output
    assert sections(digest.body)["Last security scan"] == [
        f"• <https://github.com/{REPO}/actions/runs/101/job/1010|{conclusion}> on 2026-11-08"
    ]
    assert digest.notified[1] == "1 items need attention"


def test_takes_the_newest_finished_security_scan_job_of_scheduled_and_manual_runs(
    digest,
):
    digest.runs("schedule", [run_of(10, "schedule", 1), run_of(8, "schedule", 4)])
    digest.runs(
        "workflow_dispatch",
        [run_of(12, "workflow_dispatch", 2), run_of(11, "workflow_dispatch", 3)],
    )
    digest.jobs(10, [job(10, name="digest"), job(10, conclusion="skipped")])
    digest.jobs(12, [job(12, conclusion=None)])
    digest.jobs(11, [job(11, name="other", conclusion="failure"), job(11)])
    digest.jobs(8, [job(8, conclusion="failure")])

    result = digest.run()

    assert result.returncode == 0, result.output
    assert sections(digest.body)["Last security scan"] == [
        f"• <https://github.com/{REPO}/actions/runs/11/job/110|success> on 2026-11-08"
    ]
    looked_up = [
        run_id.group(1)
        for call in digest.gh_calls
        if "/jobs?" in call[3]
        and (run_id := re.search(r"/runs/([0-9]+)/jobs", call[3]))
    ]
    assert looked_up == ["10", "12", "11"]
    assert digest.notified[1] == "nothing needs attention"


@pytest.mark.parametrize(
    "runs",
    [
        pytest.param([], id="no runs"),
        pytest.param(
            [run_of(10, "schedule", 1)], id="no security-scan job that finished"
        ),
    ],
)
def test_no_security_scan_job_needs_attention(digest, runs):
    digest.runs("schedule", runs)
    digest.jobs(10, [job(10, name="digest"), job(10, conclusion="skipped")])

    result = digest.run()

    assert result.returncode == 0, result.output
    assert sections(digest.body)["Last security scan"] == [
        "• No security-scan job in the 30 newest scheduled runs or the 30 newest manual runs of"
        " security.yml on master."
    ]
    assert digest.notified[1] == "1 items need attention"


@pytest.mark.parametrize(
    ("releases", "lines", "attention"),
    [
        pytest.param(
            [release("v1.3.0", 10), release("v1.2.3", 40)],
            ["• alpha 1.2.3: 1.3.0, published 2026-10-30, can be adopted."],
            True,
            id="a newer release 10 days old",
        ),
        pytest.param(
            [release("v1.3.0", 7)],
            ["• alpha 1.2.3: 1.3.0, published 2026-11-02, can be adopted."],
            True,
            id="a newer release exactly 7 days old",
        ),
        pytest.param(
            [release("v1.3.0", 2)],
            [
                "• alpha 1.2.3: 1.3.0, published 2026-11-07, can be adopted from 2026-11-14."
            ],
            False,
            id="a newer release 2 days old",
        ),
        pytest.param(
            [release("v1.4.0", 2), release("v1.3.0", 10)],
            [
                "• alpha 1.2.3: 1.3.0, published 2026-10-30, can be adopted.",
                "• alpha 1.2.3: 1.4.0, published 2026-11-07, can be adopted from 2026-11-14.",
            ],
            True,
            id="one to adopt and a newer one to wait for",
        ),
        pytest.param(
            [release("v1.3.0", 20), release("v1.3.1", 10)],
            ["• alpha 1.2.3: 1.3.1, published 2026-10-30, can be adopted."],
            True,
            id="the newest of two to adopt",
        ),
        pytest.param(
            [release("1.10.0", 10)],
            ["• alpha 1.2.3: 1.10.0, published 2026-10-30, can be adopted."],
            True,
            id="versions compare as numbers",
        ),
        pytest.param(
            [
                release("v1.4.0", 30, draft=True),
                release("v1.5.0-rc1", 30, prerelease=True),
                release("v1.2.2", 60),
            ],
            ["• alpha 1.2.3 is the newest release."],
            False,
            id="drafts, prereleases and older releases",
        ),
        pytest.param(
            [], ["• alpha 1.2.3 is the newest release."], False, id="no releases"
        ),
    ],
)
def test_release_binaries(digest, releases, lines, attention):
    digest.releases("example-org/alpha", releases)

    result = digest.run()

    assert result.returncode == 0, result.output
    assert sections(digest.body)["Release binaries"] == lines
    assert digest.notified[1] == (
        "1 items need attention" if attention else "nothing needs attention"
    )


def test_checks_every_entry_of_the_lock(digest):
    digest.repo.write(
        ".github/binaries.lock",
        LOCK
        + "\n[beta]\nversion=0.9.0\n"
        + "url = https://github.com/example-org/beta/releases/download/{version}/b.tar.gz\n"
        + "\n[gamma]\nversion = 2.0\nurl = https://downloads.example.invalid/gamma.tar.gz\n",
    )
    digest.releases("example-org/beta", [release("0.10.0", 10)])

    result = digest.run()

    assert result.returncode == 0, result.output
    assert sections(digest.body)["Release binaries"] == [
        "• alpha 1.2.3 is the newest release.",
        "• beta 0.9.0: 0.10.0, published 2026-10-30, can be adopted.",
        "• gamma 2.0: its url is not a GitHub release, so check it by hand.",
    ]
    assert digest.notified[1] == "2 items need attention"


@pytest.mark.parametrize(
    ("section", "break_it"),
    [
        pytest.param(
            "Dependabot pull requests",
            lambda d: d.no_reply(f"repos/{REPO}/pulls?state=open&per_page=100"),
            id="pull requests: gh fails",
        ),
        pytest.param(
            "Dependabot pull requests",
            lambda d: d.reply(
                f"repos/{REPO}/pulls?state=open&per_page=100",
                {"message": "Bad credentials"},
            ),
            id="pull requests: not a list",
        ),
        pytest.param(
            "Dependabot pull requests",
            lambda d: d.reply(f"repos/{REPO}/pulls?state=open&per_page=100", ""),
            id="pull requests: nothing",
        ),
        pytest.param(
            "Last security scan",
            lambda d: d.no_reply(RUNS.format("schedule")),
            id="runs: gh fails",
        ),
        pytest.param(
            "Last security scan",
            lambda d: d.reply(
                RUNS.format("workflow_dispatch"), {"message": "Not Found"}
            ),
            id="runs: no list of runs",
        ),
        pytest.param(
            "Last security scan",
            lambda d: d.no_reply(f"repos/{REPO}/actions/runs/101/jobs?per_page=100"),
            id="jobs: gh fails",
        ),
        pytest.param(
            "Release binaries",
            lambda d: d.no_reply("repos/example-org/alpha/releases?per_page=30"),
            id="releases: gh fails",
        ),
        pytest.param(
            "Release binaries",
            lambda d: d.releases(
                "example-org/alpha", {"message": "API rate limit exceeded"}
            ),
            id="releases: not a list",
        ),
        pytest.param(
            "Release binaries",
            lambda d: d.repo.write(".github/binaries.lock", "# no entries\n"),
            id="a lock without entries",
        ),
    ],
)
def test_a_section_that_cannot_be_read_does_not_complete(digest, section, break_it):
    break_it(digest)

    result = digest.run()

    assert result.returncode == 2
    assert f"digest: {section} could not be read:" in result.stdout
    assert result.stdout.splitlines()[-1] == (
        "digest: DID NOT COMPLETE: 1 sections could not be read"
    )
    assert digest.notified is not None, "the digest is posted all the same"
    assert digest.notified[1] == "did not complete: 1 sections could not be read"
    found = sections(digest.body)
    assert list(found) == [
        "Dependabot pull requests",
        "Last security scan",
        "Release binaries",
    ]
    assert found[section][-1] == "• Could not be read; the run's log says why."
    for other in set(found) - {section}:
        assert "• Could not be read; the run's log says why." not in found[other]


def test_counts_each_section_that_cannot_be_read(digest):
    digest.no_reply(f"repos/{REPO}/pulls?state=open&per_page=100")
    digest.no_reply("repos/example-org/alpha/releases?per_page=30")

    result = digest.run()

    assert result.returncode == 2
    assert digest.notified[1] == "did not complete: 2 sections could not be read"


@pytest.mark.parametrize(("broken", "code"), [(False, 1), (True, 2)])
def test_a_digest_that_could_not_be_posted(digest, broken, code):
    if broken:
        digest.no_reply(RUNS.format("schedule"))

    result = digest.run(FAKE_NOTIFY_EXIT="1")

    assert result.returncode == code


def test_writes_the_job_summary(digest):
    result = digest.run(GITHUB_STEP_SUMMARY=str(digest.summary))

    assert result.returncode == 0, result.output
    assert digest.summary.read_text() == (
        f"## Security digest\n\nnothing needs attention\n\n~~~\n{digest.body}~~~\n"
    )


def test_a_job_summary_that_cannot_be_written(digest, tmp_path):
    summary = tmp_path / "missing" / "summary.md"

    result = digest.run(GITHUB_STEP_SUMMARY=str(summary))

    assert result.returncode == 2
    assert "digest: writing the job summary failed" in result.stdout
    assert digest.notified is None


def test_a_temporary_directory_that_cannot_be_made(digest, tmp_path):
    result = digest.run(RUNNER_TEMP=str(tmp_path / "missing"))

    assert result.returncode == 2
    assert "digest: creating a temporary directory failed" in result.stdout
    assert digest.gh_calls == []
    assert digest.notified is None


def test_without_a_webhook_the_digest_is_not_posted_and_passes(digest):
    digest.use_the_real_notify()

    result = digest.run(
        SECURITY_SLACK_WEBHOOK_URL=None, GITHUB_STEP_SUMMARY=str(digest.summary)
    )

    assert result.returncode == 0, result.output
    assert digest.summary.read_text().startswith(
        "## Security digest\n\nnothing needs attention\n\n~~~\n*Dependabot pull requests*\n"
    )
    assert not digest.curl_log.exists()


def test_a_webhook_that_is_not_https_fails(digest):
    digest.use_the_real_notify()
    webhook = "http://hooks.example.invalid/services/plain-http-webhook"

    result = digest.run(SECURITY_SLACK_WEBHOOK_URL=webhook)

    assert result.returncode == 2
    assert "plain-http-webhook" not in result.output
    assert not digest.curl_log.exists()


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({"GITHUB_REPOSITORY": None}, id="no GITHUB_REPOSITORY"),
        pytest.param(
            {"GITHUB_REPOSITORY": "opal"}, id="GITHUB_REPOSITORY without an owner"
        ),
        pytest.param(
            {"GITHUB_REPOSITORY": "example/opal/x"}, id="GITHUB_REPOSITORY of 3 parts"
        ),
        pytest.param(
            {"GITHUB_REPOSITORY": "exa mple/opal"}, id="GITHUB_REPOSITORY with a space"
        ),
        pytest.param(
            {"GITHUB_REPOSITORY": "example/op$al"}, id="GITHUB_REPOSITORY with a $"
        ),
        pytest.param({"DIGEST_NOW": "yesterday"}, id="DIGEST_NOW is a word"),
        pytest.param({"DIGEST_NOW": "-1"}, id="DIGEST_NOW is negative"),
        pytest.param({"DIGEST_NOW": "1.5"}, id="DIGEST_NOW is a fraction"),
    ],
)
def test_wrong_settings_do_not_run(digest, changes):
    result = digest.run(**changes)

    assert result.returncode == 2
    assert result.stdout.splitlines()[-2] == "digest: DID NOT RUN"
    assert digest.gh_calls == []
    assert digest.notified is None


def test_an_argument_does_not_run(digest):
    result = digest.run("--now")

    assert result.returncode == 2
    assert "digest: usage: digest.sh (it takes no arguments)" in result.stdout
    assert digest.gh_calls == []
    assert digest.notified is None


@pytest.mark.parametrize("missing", ["jq", "gh", "curl"])
def test_a_missing_tool_does_not_run(digest, missing):
    for stub in ("gh", "curl"):
        if stub == missing:
            (digest.repo.stubs / stub).unlink()
    tools = [tool for tool in ("bash", "od", "tr", "jq") if tool != missing]

    result = digest.run(PATH=digest.repo.path_with_only(*tools))

    assert result.returncode == 2
    assert f"digest: {missing} is not installed" in result.stdout
    assert digest.notified is None


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({}, id="a digest"),
        pytest.param({"DIGEST_NOW": "x"}, id="a digest that fails"),
    ],
)
def test_workflow_commands_are_stopped_until_notify_runs(digest, changes):
    result = digest.run(**changes)

    lines = result.stdout.splitlines()
    start = re.fullmatch(r"::stop-commands::([0-9a-f]{32})", lines[0])
    assert start, f"the first line does not stop workflow commands: {lines[0]!r}"
    resume = lines.index(f"::{start.group(1)}::")
    assert result.stdout.count(start.group(1)) == 2
    if digest.notified is None:
        assert resume == len(lines) - 1
        return
    assert lines.index("*Release binaries*") < resume
    assert lines.index("::notice::fake notify ran") > resume
