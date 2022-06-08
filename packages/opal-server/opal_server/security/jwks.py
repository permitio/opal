import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from opal_common.authentication.signer import JWTSigner


class JwksStaticEndpoint:
    """configure a static files endpoint on a fastapi app, exposing JWKs."""

    def __init__(
        self,
        signer: JWTSigner,
        jwks_url: str,
        jwks_static_dir: str,
    ):
        self._signer = signer
        self._jwks_url = Path(jwks_url)
        self._jwks_static_dir = Path(jwks_static_dir)

    def configure_app(self, app: FastAPI):
        # create the directory in which the jwks.json file should sit
        self._jwks_static_dir.mkdir(parents=True, exist_ok=True)

        # get the jwks contents from the signer
        jwks_contents = {}
        if self._signer.enabled:
            jwk = json.loads(self._signer.get_jwk())
            jwks_contents = {"keys": [jwk]}

        # write the jwks.json file
        filename = self._jwks_static_dir / self._jwks_url.name
        with open(filename, "w") as f:
            f.write(json.dumps(jwks_contents))

        route_url = str(self._jwks_url.parent)
        app.mount(
            route_url,
            StaticFiles(directory=str(self._jwks_static_dir)),
            name="jwks_dir",
        )
