from opal_common.authentication.deps import JWTAuthenticator
from opal_common.authentication.types import JWTClaims
from opal_common.authentication.verifier import Unauthorized
from opal_common.schemas.data import DataUpdate
from opal_common.schemas.security import PeerType


def require_peer_type(
    authenticator: JWTAuthenticator, claims: JWTClaims, required_type: PeerType
):
    if not authenticator.enabled:
        return

    peer_type = claims.get("peer_type", None)
    if peer_type is None:
        raise Unauthorized(description="Missing 'peer_type' claim for OPAL jwt token")
    try:
        type = PeerType(peer_type)
    except ValueError:
        raise Unauthorized(
            description=f"Invalid 'peer_type' claim for OPAL jwt token: {peer_type}"
        )

    if type != required_type:
        raise Unauthorized(
            description=f"Incorrect 'peer_type' claim for OPAL jwt token: {str(type)}, expected: {str(required_type)}"
        )


def restrict_optional_topics_to_publish(
    authenticator: JWTAuthenticator, claims: JWTClaims, update: DataUpdate
):
    if not authenticator.enabled:
        return

    if "permitted_topics" not in claims:
        return

    for entry in update.entries:
        unauthorized_topics = set(entry.topics).difference(claims["permitted_topics"])
        if unauthorized_topics:
            raise Unauthorized(
                description=f"Invalid 'topics' to publish {unauthorized_topics}"
            )
