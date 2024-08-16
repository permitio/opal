from typing import Optional

from opal_common.authentication.signer import JWTSigner


class Authenticator:
    @property
    def enabled(self) -> bool:
        raise NotImplementedError()

    def signer(self) -> Optional[JWTSigner]:
        raise NotImplementedError()

    async def authenticate(self, headers):
        raise NotImplementedError()
