"""Build-time check that the image no longer trusts the compromised eMudhra
CAs.

The private keys of eight eMudhra intermediate CAs can be recovered from their
certificates (CVE-2026-111943), so anyone can mint a certificate for any host
that a client trusting their roots accepts. Browsers are covered by Certificate
Transparency; OPAL's clients are not, and trust whatever the image carries.
docker/Dockerfile runs this right after every step that installs or upgrades
OS packages, so every image fails to build if a trust store its TLS clients
read holds a certificate for one of those intermediates' keys or for a root
they chain to:

* certifi's bundle - requests and httpx verify against it by default.
* the system bundle and certificate directory (from Debian's or Alpine's
  ca-certificates) - aiohttp, websockets, git and the stdlib ssl module through
  OpenSSL, and the bundled OPA through Go's crypto/x509.

The fix is certifi >= 2026.10.19 (floored in opal-common's requires.txt) and
the patched ca-certificates the Dockerfile upgrades to. This check is what
notices when either is missing, e.g. a base image or package mirror without the
fix. A layer taken from the build cache does not re-run it, but was checked
when it was built: the check is part of the RUN that installs the packages.
The image keeps it at /opal/check_trust_store.py, so a built image can be
re-checked with `docker run --entrypoint python <image>
/opal/check_trust_store.py`.
packages/opal-common/opal_common/tests/docker_trust_store_check_test.py covers
it.
"""

import base64
import binascii
import hashlib
import re
import ssl
import sys
from pathlib import Path

import certifi

# By the SHA-256 of the certificate's DER SubjectPublicKeyInfo, from roots.json and
# impacted-intermediates.json on https://emudhra.we-have-a-problem.com/. Keys rather than
# certificates, because a trust store takes any certificate for a key as an anchor: a re-issued
# root, or a cross-sign, carries the same key under a different certificate hash.
DISTRUSTED_KEYS = {
    # The roots the eight intermediates and their Sectigo cross-signs chain to. Only the first
    # two were ever in Mozilla's store, which certifi and Alpine follow; the emSign Root TLS/CS
    # CA - G3 roots are only in Microsoft's.
    "8d417db2dd8bf5e3084d1e3f196d583849d81bdd4c00c70b9d39369e96b8c782": "emSign ECC Root CA - G3",
    "bd153ed7b0434f6886b17bce8bbe84ed340c7132d702a8f4fa318f756ecbd6f3": "AAA Certificate Services",
    "c619e4780ed8e0abeda24ad732567de4383a7ea941338f6d1a7d1b49ac792fe9": "emSign Root TLS CA - G3",
    "0a6c2b2ca5b364207954171987ac9d2178561569d8205457e77ca90c32ede282": "emSign Root CS CA - G3",
    # The compromised intermediates themselves.
    "ebed6475c2c2d80fcb199f3fe8dd6e6b3ce60b77eb15d4e42c3dec0c6f5b5105": "EM DV TLS CA - G3B",
    "43bffa19d6ef651451f6841e019931e96f6f2eaeff28ab4b6f1ce4576de2717b": "EM OV TLS CA - G3B",
    "e0254c7fcdc265e2f0f8a428dabb75ab4ae039b4872d62f5ee57f0877d5a8a41": "EM EV TLS CA - G3B",
    "49dd353dc2b919a3770645117d0e60c16115e7d1bc259eefe734b00ea434fe5f": "EM DV TLS CA - G3C",
    "63ecefee431d49523bc1136c4e72d0206a477086caf606cd5cf025686c109cf8": "EM OV TLS CA - G3C",
    "5c0660a2b164910d8ff589c18e14552e9e0ec237dcefe2cb736d41a4811f81a0": "EM EV TLS CA - G3C",
    "ec4ffa1ad0ac88081314b7aaffef6a91f97cd57291bb5ba686c5415f5eb4f6b6": "EM OV CS CA - G3B",
    "92c063d67e8f14db71d288e11266ffdaf69cbf115f7bab14f3bc2f68d25e0e30": "EM OV CS CA - G3C",
}
# Every label OpenSSL loads from a CA file or directory. TRUSTED CERTIFICATE is the certificate's
# DER followed by OpenSSL's trust settings; X509 CERTIFICATE is a legacy name for CERTIFICATE.
PEM_BLOCK = re.compile(
    r"-----BEGIN (?:TRUSTED |X509 )?CERTIFICATE-----(.+?)-----END (?:TRUSTED |X509 )?CERTIFICATE-----",
    re.DOTALL,
)
LONG_FORM = 0x80
MAX_LENGTH_OCTETS = 4  # 4 GiB; no certificate comes near it
SEQUENCE = 0x30
CONTEXT_TAG_0 = 0xA0  # TBSCertificate's optional [0] version
TBS_FIELDS_BEFORE_SPKI = 5  # serialNumber, signature, issuer, validity, subject
CERTIFI_FIX = "certifi must be >= 2026.10.19: check the floor in packages/opal-common/requires.txt"
SYSTEM_FIX = (
    "the system store comes from the ca-certificates upgrade in docker/Dockerfile (Debian "
    ">= 20250419~deb12u2 from bookworm-security, Alpine >= 20261020-r0): rebuild that layer without "
    "the cache (docker build --no-cache), and check the package mirror has the fixed version"
)


def _element(der: bytes, pos: int) -> tuple[int, int]:
    """Where the content of the DER element at pos starts, and where the
    element ends.

    Raises:
        ValueError: the element is truncated, or uses a length form DER does not allow (BER's
            indefinite length, which would otherwise read as an empty element and send the walk to
            the wrong field, or more length octets than a certificate can need).
    """
    length = der[pos + 1]
    start = pos + 2
    if length & LONG_FORM:
        size = length & ~LONG_FORM
        if not 0 < size <= MAX_LENGTH_OCTETS:
            raise ValueError("not DER: indefinite or oversized length")
        length = int.from_bytes(der[start : start + size], "big")
        start += size
    if start + length > len(der):
        raise ValueError("truncated DER")
    return start, start + length


def spki(der: bytes) -> bytes:
    """The certificate's DER SubjectPublicKeyInfo.

    A walk over the TBSCertificate fields rather than a parse with the cryptography package,
    which warns about (and in a later release will refuse to load) certificates the system
    bundle really holds, such as one with a negative serial number. v1 certificates, which have
    no [0] version field, are walked too.

    Raises:
        ValueError: the walk does not end on a SEQUENCE, i.e. the certificate is malformed.
    """
    tbs, _ = _element(der, 0)
    pos, _ = _element(der, tbs)
    if der[pos] == CONTEXT_TAG_0:
        pos = _element(der, pos)[1]
    for _ in range(TBS_FIELDS_BEFORE_SPKI):
        pos = _element(der, pos)[1]
    if der[pos] != SEQUENCE:
        raise ValueError("no SubjectPublicKeyInfo where the TBSCertificate walk ends")
    return der[pos : _element(der, pos)[1]]


def key_hashes(text: str) -> set[str]:
    """The SubjectPublicKeyInfo SHA-256 of every certificate in a PEM file.

    Raises:
        ValueError: a certificate block does not parse; the message gives its 1-based number.
    """
    hashes = set()
    for number, body in enumerate(PEM_BLOCK.findall(text), start=1):
        try:
            hashes.add(hashlib.sha256(spki(base64.b64decode(body))).hexdigest())
        except (binascii.Error, IndexError, ValueError) as e:
            raise ValueError(f"unparsable certificate (block {number}): {e!r}") from e
    return hashes


def trust_stores() -> tuple[list[Path], list[Path]]:
    """Certifi's bundle and the system bundle, then the files of the
    certificate directory.

    Resolved, so /etc/ssl/cert.pem and the /etc/ssl/certs/ca-certificates.crt it links to are
    read once. Of the directory, only top-level files are kept: subdirectories and dangling
    symlinks are skipped, and a file with no PEM certificate in it (a DER file, a README)
    contributes nothing. That is what OpenSSL's hashed-directory lookup, Go and
    rustls-native-certs load from it.

    Returns:
        (the two bundles, the directory's files other than those bundles).

    Exits:
        when OpenSSL reports no default CA file.
    """
    paths = ssl.get_default_verify_paths()
    if not paths.cafile:
        sys.exit("check_trust_store: OpenSSL has no default CA file")
    bundles = [Path(certifi.where()).resolve(), Path(paths.cafile).resolve()]
    # get_default_verify_paths() reports capath as None when the directory does not exist.
    certs_dir = Path(paths.capath).iterdir() if paths.capath else []
    dir_files = sorted(
        {path.resolve() for path in certs_dir if path.is_file()} - set(bundles)
    )
    return bundles, dir_files


def find_distrusted() -> dict[Path, list[str]]:
    """Every trust store file that holds a certificate for a compromised key.

    Returns:
        {resolved path: sorted names of the CAs whose keys it holds}; empty when the image is clean.

    Exits:
        when a bundle is missing or holds no certificate (the check would pass without checking
        anything), when a file holds a certificate that does not parse, and as trust_stores() does.
    """
    bundles, dir_files = trust_stores()
    hits = {}
    for path in bundles + dir_files:
        try:
            found = (
                key_hashes(path.read_text(errors="replace"))
                if path.is_file()
                else set()
            )
        except ValueError as e:
            sys.exit(f"check_trust_store: {path}: {e}")
        if path in bundles and not found:
            sys.exit(f"check_trust_store: no certificates in trust store {path}")
        if names := sorted(
            DISTRUSTED_KEYS[key] for key in found & DISTRUSTED_KEYS.keys()
        ):
            hits[path] = names
    return hits


def main() -> int:
    """The build gate: 1, with what to fix on stderr, if any store trusts a compromised key."""
    hits = find_distrusted()
    if not hits:
        return 0
    certifi_bundle = Path(certifi.where()).resolve()
    sys.stderr.write("check_trust_store: compromised eMudhra CAs are still trusted:\n")
    for path, names in hits.items():
        fix = CERTIFI_FIX if path == certifi_bundle else SYSTEM_FIX
        sys.stderr.write(f"  {path}: {', '.join(names)}\n    fix: {fix}\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
