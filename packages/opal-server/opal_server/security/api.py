from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from opal_common.authentication.deps import StaticBearerAuthenticator
from opal_common.authentication.signer import JWTSigner
from opal_common.logger import logger
from opal_common.schemas.security import AccessToken, AccessTokenRequest, TokenDetails
from opal_common.monitoring.prometheus_metrics import (
    token_generation_errors,
    token_generated_count,
    token_request_count,
)


def init_security_router(signer: JWTSigner, authenticator: StaticBearerAuthenticator):
    router = APIRouter()

    @router.post(
        "/token",
        status_code=status.HTTP_200_OK,
        response_model=AccessToken,
        dependencies=[Depends(authenticator)],
    )
    async def generate_new_access_token(req: AccessTokenRequest):
        token_request_count.labels(token_type=req.type.value).inc()
        if not signer.enabled:
            token_generation_errors.labels(error_type="SignerDisabled").inc()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="opal server was not configured with security, cannot generate tokens!",
            )
        try:
            claims = {"peer_type": req.type.value, **req.claims}
            token = signer.sign(sub=req.id, token_lifetime=req.ttl, custom_claims=claims)
            logger.info(f"Generated opal token: peer_type={req.type.value}")
            token_generated_count.labels(peer_type=req.type.value).inc()
            return AccessToken(
                token=token,
                details=TokenDetails(
                    id=req.id,
                    type=req.type,
                    expired=datetime.utcnow() + req.ttl,
                    claims=claims,
                ),
         )
        except Exception as ex:
                logger.error(f"Failed to generate token: {str(ex)}")
                token_generation_errors.labels(error_type="TokenGenerationFailed").inc()
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to generate token due to server error.",
                )

    return router
