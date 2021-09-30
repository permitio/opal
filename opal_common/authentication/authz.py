from opal_common.schemas.security import PeerType
from opal_common.authentication.deps import JWTAuthenticator
from opal_common.authentication.verifier import Unauthorized
from opal_common.authentication.types import JWTClaims

def require_peer_type(authenticator: JWTAuthenticator, claims: JWTClaims, required_type: PeerType):
    if not authenticator.enabled:
        return

    peer_type = claims.get('peer_type', None)
    if peer_type is None:
        raise Unauthorized(description="Missing 'peer_type' claim for OPAL jwt token")
    try:
        type = PeerType(peer_type)
    except ValueError:
        raise Unauthorized(description=f"Invalid 'peer_type' claim for OPAL jwt token: {peer_type}")

    if type != required_type:
        raise Unauthorized(description=f"Incorrect 'peer_type' claim for OPAL jwt token: {str(type)}, expected: {str(required_type)}")