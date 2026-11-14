"""The gunicorn worker class the server and the client run under: the one
``run_gunicorn`` configures, and the one the images' ``scripts/start.sh``
passes with ``-k``.

Each is loaded in a fresh interpreter that turns DeprecationWarning into an
error, since a module imported once in the test process does not warn again.
"""

import re
import subprocess
import sys
from pathlib import Path

import gunicorn.app.base
from opal_common import corn_utils

START_SH = Path(__file__).resolve().parents[4] / "scripts" / "start.sh"

_LOAD = (
    "import importlib, sys\n"
    "from gunicorn.workers.base import Worker\n"
    "module, _, name = sys.argv[1].rpartition('.')\n"
    "worker = getattr(importlib.import_module(module), name)\n"
    "assert issubclass(worker, Worker), worker\n"
)


def _loads_cleanly(worker_class: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-W", "error::DeprecationWarning", "-c", _LOAD, worker_class],
        capture_output=True,
        text=True,
        timeout=60,
    )


def _run_gunicorn_worker_class(monkeypatch) -> str:
    started = []
    monkeypatch.setattr(
        gunicorn.app.base.BaseApplication, "run", lambda app: started.append(app)
    )
    corn_utils.run_gunicorn(app=object(), number_of_workers=1)
    (app,) = started
    return app.cfg.worker_class_str


def _start_sh_worker_class() -> str:
    (worker_class,) = re.findall(r"\s-k\s+(\S+)", START_SH.read_text())
    return worker_class


def test_run_gunicorn_runs_a_worker_class_that_loads_without_deprecation(
    monkeypatch,
):
    result = _loads_cleanly(_run_gunicorn_worker_class(monkeypatch))

    assert result.returncode == 0, result.stderr


def test_the_images_start_script_runs_a_worker_class_that_loads_without_deprecation():
    result = _loads_cleanly(_start_sh_worker_class())

    assert result.returncode == 0, result.stderr
