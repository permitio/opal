from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from opal_common.authentication.deps import StaticBearerAuthenticator
from opal_common.authentication.signer import JWTSigner
from opal_common.logger import logger
from opal_common.schemas.security import AccessToken, AccessTokenRequest, TokenDetails


def init_security_router(signer: JWTSigner, authenticator: StaticBearerAuthenticator):
    router = APIRouter()

    @router.post(
        "/token",
        status_code=status.HTTP_200_OK,
        response_model=AccessToken,
        dependencies=[Depends(authenticator)],
    )
    async def generate_new_access_token(req: AccessTokenRequest):
        if not signer.enabled:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="opal server was not configured with security, cannot generate tokens!",
            )

        claims = {"peer_type": req.type.value, **req.claims}
        token = signer.sign(sub=req.id, token_lifetime=req.ttl, custom_claims=claims)
        logger.info(f"Generated opal token: peer_type={req.type.value}")
        return AccessToken(
            token=token,
            details=TokenDetails(
                id=req.id,
                type=req.type,
                expired=datetime.utcnow() + req.ttl,
                claims=claims,
            ),
        )

    return router
