import os
import ssl
from typing import Optional
from loguru import logger

from opal_common.config import opal_common_config


def get_custom_ssl_context() -> Optional[ssl.SSLContext]:
    """Potentially (if enabled), returns a custom ssl context that respect
    self-signed certificates or mutual TLS (mTLS).

    More accurately, may return an ssl context that respects a local CA
    as a valid issuer and may also provide a client certificate to authenticate the client against the server.
    """
    if (
        opal_common_config.MTLS_CLIENT_CERT is not None
        and opal_common_config.MTLS_CLIENT_KEY is not None
    ):
        return get_custom_ssl_context_for_mtls(
            client_cert_file=opal_common_config.MTLS_CLIENT_CERT,
            client_key_file=opal_common_config.MTLS_CLIENT_KEY,
            ca_file=opal_common_config.MTLS_CA_CERT,
        )

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


def get_custom_ssl_context_for_mtls(
    client_cert_file: str, client_key_file: str, ca_file: Optional[str]
) -> Optional[ssl.SSLContext]:
    try:
        client_cert_file = get_verified_expanded_filename(client_cert_file)
        client_key_file = get_verified_expanded_filename(client_key_file)
        ca_file = get_verified_expanded_filename(ca_file)

        custom_ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        custom_ssl_context.load_cert_chain(
            certfile=client_cert_file, keyfile=client_key_file
        )
        if ca_file is not None:
            custom_ssl_context.load_verify_locations(ca_file)

        return custom_ssl_context
    except ValueError:
        return None


def get_verified_expanded_filename(filename: Optional[str]) -> Optional[str]:
    if filename is None:
        return None

    filename = os.path.expanduser(filename)
    if not os.path.isfile(filename):
        logger.error("provided file does not exist: {path}", path=filename)
        raise ValueError("file does not exist")

    return filename
