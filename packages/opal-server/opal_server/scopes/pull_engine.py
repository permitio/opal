from pathlib import Path

from opal_common.schemas.scopes import Scope


class CeleryPullEngine:
    def fetch_source(self, base_dir: Path, scope: Scope):
        from opal_server import worker
        worker.fetch_source.delay(str(base_dir), scope.json())

