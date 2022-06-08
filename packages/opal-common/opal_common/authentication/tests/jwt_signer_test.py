import os
import sys

import pytest

# Add root opal dir to use local src as package for tests (i.e, no need for python -m pytest)
root_dir = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        os.path.pardir,
        os.path.pardir,
        os.path.pardir,
    )
)
sys.path.append(root_dir)

# -----------------------------------------------------------------------------
import asyncio
from datetime import timedelta
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from opal_common.authentication.casting import cast_private_key, cast_public_key
from opal_common.authentication.signer import JWTSigner
from opal_common.authentication.types import (
    EncryptionKeyFormat,
    JWTAlgorithm,
    JWTClaims,
    PrivateKey,
    PublicKey,
)
from opal_common.authentication.verifier import JWTVerifier
from opal_common.logger import logger

KEY_FILENAME = "opal_test_crypto_key"
PASSPHRASE = "whiterabbit"

AUTH_JWT_AUDIENCE = "https://api.opal.ac/v1/"
AUTH_JWT_ISSUER = "https://opal.ac/"
CUSTOM_CLAIMS = {"color": "red"}


async def run_subprocess(command: str):
    process = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    return_code = await process.wait()
    assert return_code == 0


async def run_commands(commands: List[str]):
    # the await inside the for-loop is intentional, these commands should not run in parallel
    for command in commands:
        logger.info(f"running command: {command}")
        await run_subprocess(command)


async def verify_crypto_keys(
    private_key_filename: Path,
    public_key_filename: Path,
    private_key_format: EncryptionKeyFormat,
    public_key_format: EncryptionKeyFormat,
    algorithm: JWTAlgorithm,
    passphrase: Optional[str] = None,
):
    # assert keys created
    assert private_key_filename.exists()
    assert public_key_filename.exists()

    logger.info("trying to cast private key from string...")
    private_key: Optional[PrivateKey] = cast_private_key(
        private_key_filename, private_key_format, passphrase
    )
    assert private_key is not None

    logger.info("trying to cast public key from string...")
    public_key: Optional[PublicKey] = cast_public_key(
        public_key_filename, public_key_format
    )
    assert public_key is not None

    logger.info("trying to init JWT Verifier...")
    verifier = JWTVerifier(public_key, algorithm, AUTH_JWT_AUDIENCE, AUTH_JWT_ISSUER)
    assert verifier.enabled

    logger.info("trying to init JWT Signer...")
    signer = JWTSigner(
        private_key, public_key, algorithm, AUTH_JWT_AUDIENCE, AUTH_JWT_ISSUER
    )
    assert signer.enabled

    logger.info("trying to sign a token...")
    token: str = signer.sign(uuid4(), timedelta(days=1), CUSTOM_CLAIMS)

    logger.info("trying to verify the signed token...")
    claims: JWTClaims = verifier.verify(token)

    logger.info("trying to verify all the claims on the token...")
    for k in CUSTOM_CLAIMS:
        assert k in claims.keys()
        assert CUSTOM_CLAIMS[k] == claims[k]

    logger.info("done.")


@pytest.mark.asyncio
async def test_encryption_keys_RFC_4253_ssh_format_with_passphrase(tmp_path):
    """Test key encryption format: RFC_4253.

    such keys can be generate by this command: ``` ssh-keygen -t rsa -b
    4096 -m pem ``` the private key is in PEM format the public key in
    in ssh format
    """
    logger.info("TEST: test_encryption_keys_RFC_4253_ssh_format_with_passphrase")
    # creates the keys under temp paths that are auto-deleted after the test
    private_key_filename = Path(os.path.join(tmp_path, KEY_FILENAME))
    public_key_filename = Path(f"{private_key_filename}.pub")

    # commands to generate crypto keys
    await run_commands(
        [
            f"ssh-keygen -t rsa -b 4096 -m pem -f {private_key_filename} -N {PASSPHRASE}",
        ]
    )

    await verify_crypto_keys(
        private_key_filename=private_key_filename,
        public_key_filename=public_key_filename,
        private_key_format=EncryptionKeyFormat.pem,
        public_key_format=EncryptionKeyFormat.ssh,
        algorithm=getattr(JWTAlgorithm, "RS256"),
        passphrase=PASSPHRASE,
    )


@pytest.mark.asyncio
async def test_encryption_keys_RFC_4253_ssh_format_no_passphrase(tmp_path):
    logger.info("TEST: test_encryption_keys_RFC_4253_ssh_format_no_passphrase")

    # creates the keys under temp paths that are auto-deleted after the test
    private_key_filename = Path(os.path.join(tmp_path, KEY_FILENAME))
    public_key_filename = Path(f"{private_key_filename}.pub")

    # commands to generate crypto keys
    await run_commands(
        [
            f"ssh-keygen -t rsa -b 4096 -m pem -f {private_key_filename} -N ''",
        ]
    )

    await verify_crypto_keys(
        private_key_filename=private_key_filename,
        public_key_filename=public_key_filename,
        private_key_format=EncryptionKeyFormat.pem,
        public_key_format=EncryptionKeyFormat.ssh,
        algorithm=getattr(JWTAlgorithm, "RS256"),
        passphrase=None,
    )


@pytest.mark.asyncio
async def test_encryption_keys_PKCS1_format_with_passphrase(tmp_path):
    logger.info("TEST: test_encryption_keys_PKCS1_format_with_passphrase")

    # creates the keys under temp paths that are auto-deleted after the test
    private_key_filename = Path(os.path.join(tmp_path, KEY_FILENAME))
    public_key_filename = Path(f"{private_key_filename}.pub")

    # commands to generate crypto keys
    await run_commands(
        [
            f"ssh-keygen -t rsa -b 4096 -m pem -f {private_key_filename} -N {PASSPHRASE}",
            f"ssh-keygen -e -m pem -f {private_key_filename} -P {PASSPHRASE} > {public_key_filename}",
        ]
    )

    await verify_crypto_keys(
        private_key_filename=private_key_filename,
        public_key_filename=public_key_filename,
        private_key_format=EncryptionKeyFormat.pem,
        public_key_format=EncryptionKeyFormat.pem,
        algorithm=getattr(JWTAlgorithm, "RS256"),
        passphrase=PASSPHRASE,
    )


@pytest.mark.asyncio
async def test_encryption_keys_X509_SPKI_format_with_passphrase(tmp_path):
    logger.info("TEST: test_encryption_keys_X509_SPKI_format_with_passphrase")

    # creates the keys under temp paths that are auto-deleted after the test
    private_key_filename = Path(os.path.join(tmp_path, KEY_FILENAME))
    public_key_filename = Path(f"{private_key_filename}.pub")

    # commands to generate crypto keys
    await run_commands(
        [
            f"ssh-keygen -t rsa -b 4096 -m pem -f {private_key_filename} -N {PASSPHRASE}",
            f"ssh-keygen -e -m pkcs8 -f {private_key_filename} -P {PASSPHRASE} > {public_key_filename}",
        ]
    )

    await verify_crypto_keys(
        private_key_filename=private_key_filename,
        public_key_filename=public_key_filename,
        private_key_format=EncryptionKeyFormat.pem,
        public_key_format=EncryptionKeyFormat.pem,
        algorithm=getattr(JWTAlgorithm, "RS256"),
        passphrase=PASSPHRASE,
    )


@pytest.mark.asyncio
async def test_encryption_keys_PKCS1_format_with_passphrase_hardcoded_keys(tmp_path):
    """
    these hardcoded keys are for test purposes only - NEVER use them!!!!
    """
    logger.info(
        "TEST: test_encryption_keys_PKCS1_format_with_passphrase_hardcoded_keys"
    )

    # creates the keys under temp paths that are auto-deleted after the test
    private_key_filename = Path(os.path.join(tmp_path, KEY_FILENAME))
    public_key_filename = Path(f"{private_key_filename}.pub")

    open(private_key_filename, "w").write(
        """
-----BEGIN RSA PRIVATE KEY-----
Proc-Type: 4,ENCRYPTED
DEK-Info: AES-128-CBC,76065A0C88ABA1D6B5B812ED6BE346B5

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
-----END RSA PRIVATE KEY-----"""
    )

    open(public_key_filename, "w").write(
        """
-----BEGIN RSA PUBLIC KEY-----
MIICCgKCAgEAoTtleKwCPQ4kUGAAk4uDnjZStr/LbzFaYTPrfFWbRmEFzVoWREST
STesIuoTgdLLiDY0wksC6IZ/wlvVvxbuRG4PljUPiOvfHTDI2giC7JoH40b0HNI+
1YlDWU+pnvS1SeoPzzVwC2uVP97g0Z0d7BlXZY8ufsvQPfHQP4sTuvFXiMNC18dQ
OVLZS8EpeNhORf+iTe43OgNNnD4KCl9w1VScUlR58K+N+glQ6qONZjayII9Qn0vP
IZfw/RseR5qprJuA30s+hPMtOhqwfoWwIP8dGRL/rbPoVb0tvLTWnmbDySQGDyof
7aWlW0LN+7/5wPlxhq8coaRcTxlCU0Iro1xL/TpOvOQb4Q+++qUphIc+t1a8j2Ge
X4/+N5kSSNU83NJpEGLLknaoiR9cYvNBJksJhAGHvu0kLmb5/91nK/CHJMsma82W
GR9TQAtoSOlOh8P3cpeLCEHdMd3iXHdMUQ7rzIRGjZyPPMv+JxumQ1MJ76vNHB4j
JgN5LRWeo+H17t7bnO/Ot6qmmp7ZN3dc3QBlsy09cCdQ4l4YWEa3VO6dXnIdoe/c
THdYobue6ft5E7d7Eez4is6++d8SuboxJMmzbDK9U++GoJVARk2FqUpXTqHSIqKt
y8eFhYJfV0a59E5TasHlIT/HLcdlvISQ0/lBoPOwtKDbFuZvqQwWKEsCAwEAAQ==
-----END RSA PUBLIC KEY-----
    """
    )

    await verify_crypto_keys(
        private_key_filename=private_key_filename,
        public_key_filename=public_key_filename,
        private_key_format=EncryptionKeyFormat.pem,
        public_key_format=EncryptionKeyFormat.pem,
        algorithm=getattr(JWTAlgorithm, "RS256"),
        passphrase=PASSPHRASE,
    )


@pytest.mark.asyncio
async def test_encryption_keys_X509_SPKI_format_with_passphrase_hardcoded_keys(
    tmp_path,
):
    """
    these hardcoded keys are for test purposes only - NEVER use them!!!!
    """
    logger.info(
        "TEST: test_encryption_keys_X509_SPKI_format_with_passphrase_hardcoded_keys"
    )

    # creates the keys under temp paths that are auto-deleted after the test
    private_key_filename = Path(os.path.join(tmp_path, KEY_FILENAME))
    public_key_filename = Path(f"{private_key_filename}.pub")

    open(private_key_filename, "w").write(
        """
-----BEGIN RSA PRIVATE KEY-----
Proc-Type: 4,ENCRYPTED
DEK-Info: AES-128-CBC,B0E9701EF36B6D18081BE93E446F7DAC

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
-----END RSA PRIVATE KEY-----"""
    )

    open(public_key_filename, "w").write(
        """
-----BEGIN PUBLIC KEY-----
MIICIjANBgkqhkiG9w0BAQEFAAOCAg8AMIICCgKCAgEA3dPvy1zGdxMRf06+KYbk
/OW73J8t1eX4Nb3E5w5GV6gdt1KKFMD7WOy9wPFNUS1k9o7WhW1giQGSIE1NuShH
Y8x3yvYnPHVptrWFmKZMTVb8jytmEtLT0tHfJjCJKjPUqUT2Xli/Lyg/MHz0zqPb
b+vlXFBujI+3u1em6DUMP5Qao3rq0qzdD2fmBVsXrcOhAL9GwgyHTFVON/PvBKXU
MvseZ+FAqydBdG95b+DKG4eEzjz0CV3SXhMx4orPUsa9VupAbve3MMGYyXB51yYh
lDyTnFiAChhIzU99pgg5Uhx8YX/hFEAoATwbv6pmliFmUzuTs5sLP9DP+56FGye8
s1wxIMBMAMzBTMKnsJlpIOyEBq8tI0UiSM76jP6cAdK/JgZ+tHi2HJXbtm+Gc02F
2syHJI7lryQNfbPqgn8QXJNVMiCSnmqmXfEoz2cWkqTn9siIovnrOsQDN4nfiLGs
tjxiX307tP6CjNFl24/olZdan6D4jxskI1cgXxL53tjdXASbJ5Z3M/xJmm5P/eGv
GKe4LpzupEUoDz4UnfgPUsOORe4p49NHm07S3KCouZOAslMAJDqe2qyyPhDnUaTG
0OAmlqa412uGUhmxYbKgyPNALED/9WksFEWDDqt+bq6zwYActCW2203gCRsTbSX9
wo0Src+YUGAdjomgzrt/6CECAwEAAQ==
-----END PUBLIC KEY-----
    """
    )

    await verify_crypto_keys(
        private_key_filename=private_key_filename,
        public_key_filename=public_key_filename,
        private_key_format=EncryptionKeyFormat.pem,
        public_key_format=EncryptionKeyFormat.pem,
        algorithm=getattr(JWTAlgorithm, "RS256"),
        passphrase=PASSPHRASE,
    )
