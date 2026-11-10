"""Tests for .github/scripts/notify.sh, which posts a notice to the security
Slack channel.

A fake curl first on PATH stands in for the webhook: it saves the JSON payload it was sent and
answers with the HTTP status or curl exit code the test asks for.
"""

import json

import pytest

NOTIFY = ".github/scripts/notify.sh"
WEBHOOK = "https://hooks.example.invalid/services/T0/B0/x"
FAKE_CURL = """\
payload=$(cat)
printf '%s' "$payload" >"$CURL_PAYLOAD"
if [[ -n ${CURL_EXIT:-} ]]; then
  exit "$CURL_EXIT"
fi
printf '%s' "${CURL_STATUS:-200}"
"""


@pytest.fixture
def repo(throwaway_repo):
    """A throwaway copy with notify.sh and a fake curl."""
    throwaway_repo.copy(NOTIFY)
    throwaway_repo.stub("curl", FAKE_CURL)
    return throwaway_repo


def run(repo, *args, **env):
    """Run notify.sh with the fake curl's payload file and the given
    variables."""
    variables = {
        "CURL_PAYLOAD": str(repo.tmp / "payload.json"),
        "GITHUB_REPOSITORY": "permitio/opal",
        "GITHUB_SERVER_URL": "https://github.com",
        "GITHUB_RUN_ID": "42",
    }
    variables.update(env)
    return repo.run(NOTIFY, *args, env=variables)


def posted_text(repo) -> str:
    """The text of the message the fake curl was sent."""
    return json.loads((repo.tmp / "payload.json").read_text())["text"]


def test_a_check_notice_has_the_repo_check_result_and_run_link(repo) -> None:
    body = repo.write("body.txt", "• first\n• second\n")
    result = run(repo, "digest", "PASS", str(body), SECURITY_SLACK_WEBHOOK_URL=WEBHOOK)
    assert result.returncode == 0, result.output
    assert posted_text(repo) == (
        "permitio/opal digest: PASS. <https://github.com/permitio/opal/actions/runs/42|Run>\n"
        "• first\n• second"
    )
    assert "notify: posted to the security channel (HTTP 200)" in result.stdout


def test_a_check_notice_escapes_its_result(repo) -> None:
    result = run(repo, "digest", "<!channel> & co", SECURITY_SLACK_WEBHOOK_URL=WEBHOOK)
    assert result.returncode == 0, result.output
    assert "digest: &lt;!channel&gt; &amp; co." in posted_text(repo)


def test_a_message_is_posted_as_it_is(repo) -> None:
    message = (
        ":warning: *permitio/opal: security scan incomplete*\n\n• *Trivy*: clean\n"
    )
    path = repo.write("message.txt", message)
    result = run(repo, "--message", str(path), SECURITY_SLACK_WEBHOOK_URL=WEBHOOK)
    assert result.returncode == 0, result.output
    assert posted_text(repo) == message.rstrip("\n")
    assert "permitio/opal: security scan incomplete" in result.stdout


def test_a_one_line_message_is_posted_as_it_is(repo) -> None:
    path = repo.write("message.txt", "only a headline\n")
    result = run(repo, "--message", str(path), SECURITY_SLACK_WEBHOOK_URL=WEBHOOK)
    assert result.returncode == 0, result.output
    assert posted_text(repo) == "only a headline"


def test_a_long_message_is_cut_after_a_line_with_a_note(repo) -> None:
    lines = [f"• line {n} " + "x" * 90 for n in range(600)]
    path = repo.write("message.txt", "headline\n" + "\n".join(lines) + "\n")
    result = run(repo, "--message", str(path), SECURITY_SLACK_WEBHOOK_URL=WEBHOOK)
    assert result.returncode == 0, result.output
    text = posted_text(repo)
    assert len(text.encode()) <= 39000
    assert text.startswith("headline\n• line 0 ")
    assert text.endswith(
        "• The report is cut here; the run's job summary has the rest."
    )
    kept = text.splitlines()[-2]
    assert kept in lines


@pytest.mark.parametrize("args", [["--message", "MESSAGE"], ["scan", "PASS"]])
def test_without_a_webhook_it_warns_and_passes(repo, args) -> None:
    path = repo.write("message.txt", "headline\n")
    args = [str(path) if arg == "MESSAGE" else arg for arg in args]
    summary = repo.tmp / "summary.md"
    result = run(repo, *args, GITHUB_STEP_SUMMARY=str(summary))
    assert result.returncode == 0, result.output
    assert (
        "::warning title=Slack::SECURITY_SLACK_WEBHOOK_URL is not set" in result.stdout
    )
    assert "SECURITY_SLACK_WEBHOOK_URL is not set" in summary.read_text()
    assert not (repo.tmp / "payload.json").exists()


def test_a_webhook_that_is_not_https_does_not_run(repo) -> None:
    result = run(
        repo, "scan", "PASS", SECURITY_SLACK_WEBHOOK_URL="http://hooks.example.invalid"
    )
    assert result.returncode == 2
    assert (
        "notify: DID NOT RUN: SECURITY_SLACK_WEBHOOK_URL is not an https URL"
        in result.stdout
    )
    assert "hooks.example.invalid" not in result.output


@pytest.mark.parametrize(
    ("env", "detail"),
    [({"CURL_EXIT": "7"}, "curl exit 7"), ({"CURL_STATUS": "410"}, "HTTP 410")],
    ids=["unreachable", "gone"],
)
def test_a_notice_that_is_not_delivered_fails(repo, env, detail) -> None:
    result = run(repo, "scan", "PASS", SECURITY_SLACK_WEBHOOK_URL=WEBHOOK, **env)
    assert result.returncode == 1
    assert "notify: FAIL: posting to the security channel failed" in result.stdout
    assert detail in result.stdout
    assert WEBHOOK not in result.output


@pytest.mark.parametrize(
    "args",
    [[], ["only-check"], ["a", "b", "c", "d"], ["--message"], ["--message", ""]],
    ids=["none", "one", "four", "message-without-file", "message-empty"],
)
def test_wrong_arguments_do_not_run(repo, args) -> None:
    result = run(repo, *args, SECURITY_SLACK_WEBHOOK_URL=WEBHOOK)
    assert result.returncode == 2
    assert "notify: DID NOT RUN: usage: notify.sh" in result.stdout


@pytest.mark.parametrize("mode", ["--message", "body"])
def test_a_file_that_cannot_be_read_does_not_run(repo, mode) -> None:
    missing = str(repo.tmp / "missing.txt")
    args = ["--message", missing] if mode == "--message" else ["scan", "PASS", missing]
    result = run(repo, *args, SECURITY_SLACK_WEBHOOK_URL=WEBHOOK)
    assert result.returncode == 2
    assert "cannot be read" in result.stdout
