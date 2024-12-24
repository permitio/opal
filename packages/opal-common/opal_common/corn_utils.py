"""Utilities to run UVICORN / GUNICORN."""
import multiprocessing
from typing import Dict

import gunicorn.app.base


def calc_default_number_of_workers():
    return (multiprocessing.cpu_count() * 2) + 1


class GunicornApp(gunicorn.app.base.BaseApplication):
    def __init__(self, app, options: Dict[str, str] = None):
        self.options = options or {}
        self.application = app
        super().__init__()

    def load_config(self):
        config = {
            key: value
            for key, value in self.options.items()
            if key in self.cfg.settings and value is not None
        }
        for key, value in config.items():
            self.cfg.set(key.lower(), value)

    def load(self):
        return self.application


def run_gunicorn(app, number_of_workers=None, host=None, port=None, **kwargs):
    options = {
        "bind": "%s:%s" % (host or "127.0.0.1", port or "8080"),
        "workers": number_of_workers or calc_default_number_of_workers(),
        "worker_class": "uvicorn.workers.UvicornWorker",
    }
    options.update(kwargs)
    GunicornApp(app, options).run()


def run_uvicorn(
    app_path, number_of_workers=None, host=None, port=None, reload=False, **kwargs
):
    options = {
        "host": host or "127.0.0.1",
        "port": port or "8080",
        "reload": reload,
        "workers": number_of_workers or calc_default_number_of_workers(),
    }
    options.update(kwargs)
    import uvicorn

    uvicorn.run(app_path, **options)
