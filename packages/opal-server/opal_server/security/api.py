from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from opal_common.authentication.deps import StaticBearerAuthenticator
from opal_common.authentication.signer import JWTSigner
from opal_common.config import opal_common_config
from opal_common.logger import logger
from opal_common.monitoring.otel_metrics import get_meter
from opal_common.schemas.security import AccessToken, AccessTokenRequest, TokenDetails

_token_requested_counter = None
_token_generated_counter = None


def get_token_requested_counter():
    global _token_requested_counter
    if _token_requested_counter is None:
        if not opal_common_config.ENABLE_OPENTELEMETRY_METRICS:
            return None
        meter = get_meter()
        _token_requested_counter = meter.create_counter(
            name="opal_server_token_requested", description="Number of token requests"
        )
    return _token_requested_counter


def get_token_generated_counter():
    global _token_generated_counter
    if _token_generated_counter is None:
        if not opal_common_config.ENABLE_OPENTELEMETRY_METRICS:
            return None
        meter = get_meter()
        _token_generated_counter = meter.create_up_down_counter(
            name="opal_client_token_generated", description="Number of tokens generated"
        )
    return _token_generated_counter


def init_security_router(signer: JWTSigner, authenticator: StaticBearerAuthenticator):
    router = APIRouter()

    @router.post(
        "/token",
        status_code=status.HTTP_200_OK,
        response_model=AccessToken,
        dependencies=[Depends(authenticator)],
    )
    async def generate_new_access_token(req: AccessTokenRequest):
        token_requested_counter = get_token_requested_counter()
        if token_requested_counter is not None:
            token_requested_counter.add(
                1, attributes={"token_type": req.type.value, "status": "received"}
            )

        if not signer.enabled:
            if token_requested_counter is not None:
                token_requested_counter.add(
                    1, attributes={"token_type": req.type.value, "status": "error"}
                )

            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="opal server was not configured with security, cannot generate tokens!",
            )
        try:
            claims = {"peer_type": req.type.value, **req.claims}
            token = signer.sign(
                sub=req.id, token_lifetime=req.ttl, custom_claims=claims
            )
            logger.info(f"Generated opal token: peer_type={req.type.value}")
            token_generated_counter = get_token_generated_counter()
            if token_generated_counter is not None:
                token_generated_counter.add(
                    1,
                    attributes={
                        "peer_type": req.type.value,
                        "ttl": req.ttl.total_seconds() if req.ttl else None,
                    },
                )

            if token_requested_counter is not None:
                token_requested_counter.add(
                    1, attributes={"token_type": req.type.value, "status": "success"}
                )

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
            error_type = (
                "TokenGenerationFailed"
                if "token" in str(ex).lower()
                else "UnexpectedError"
            )
            if token_requested_counter is not None:
                token_requested_counter.add(
                    1, attributes={"token_type": req.type.value, "status": "error"}
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate token due to server error.",
            )

    return router
