import os
import ssl
from typing import Optional

from opal_common.config import opal_common_config


def get_custom_ssl_context() -> Optional[ssl.SSLContext]:
    """Potentially (if enabled), returns a custom ssl context that respect
    self-signed certificates.

    More accurately, may return an ssl context that respects a local CA
    as a valid issuer.
    """
    if not opal_common_config.CLIENT_SELF_SIGNED_CERTIFICATES_ALLOWED:
        return None

    ca_file: Optional[str] = opal_common_config.CLIENT_SSL_CONTEXT_TRUSTED_CA_FILE

    if ca_file is None:
        return None

    if not ca_file:
        return None

    ca_file_path = os.path.expanduser(ca_file)
    if not os.path.isfile(ca_file_path):
        return None

    return ssl.create_default_context(cafile=ca_file_path)
