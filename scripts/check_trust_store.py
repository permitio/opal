"""Build-time check that the image no longer trusts the compromised eMudhra
CAs.

The private keys of eight eMudhra intermediate CAs can be recovered from their
certificates (CVE-2026-111943), so anyone can mint a certificate for any host
that a client trusting their roots accepts. Browsers are covered by Certificate
Transparency; OPAL's clients are not, and trust whatever the image carries.
docker/Dockerfile bind-mounts and runs this in both common stages, so every
image fails to build if a trust store its TLS clients read still holds a root
those intermediates chain to:

* certifi's bundle - requests and httpx verify against it by default.
* the system bundle and certificate directory (from Debian's or Alpine's
  ca-certificates) - aiohttp, websockets, git and the stdlib ssl module through
  OpenSSL, and the bundled OPA through Go's crypto/x509.

The fix is certifi >= 2026.10.19 (floored in opal-common's requires.txt) and
the patched ca-certificates the Dockerfile upgrades to. This check is what
notices when either goes missing, e.g. a layer replayed from a cache older than
the fix. packages/opal-common/opal_common/tests/docker_trust_store_check_test.py
covers it.
"""

import base64
import hashlib
import re
import ssl
import sys
from pathlib import Path

import certifi

# Every root the eight intermediates and their Sectigo cross-signs chain to, by
# the SHA-256 of the root certificate's DER encoding: roots.json on
# https://emudhra.we-have-a-problem.com/. Debian's store still held the first
# two; the emSign Root TLS/CS CA - G3 roots are only in Microsoft's store today,
# and are denied so that no bundle can bring one back unnoticed.
DISTRUSTED_ROOTS = {
    "86a1ecba089c4a8d3bbe2734c612ba341d813e043cf9e8a862cd5c57a36bbe6b": "emSign ECC Root CA - G3",
    "d7a7a0fb5d7e2731d771e9484ebcdef71d5f0c3e0a2948782bc83ee0ea699ef4": "AAA Certificate Services",
    "7dd78d5f4f13459a83dff9abbba62edbaf6f2d102bf257fd712f4d9f2746ed8d": "emSign Root TLS CA - G3",
    "f2edaaff3d9b701fb4d14c9f285f8c0bad90fc3bcc1fa07d47f4718edaba34a5": "emSign Root CS CA - G3",
}
# OpenSSL loads both forms from a CA file or directory. A TRUSTED CERTIFICATE
# block is the certificate's DER followed by OpenSSL's trust settings.
PEM_BLOCK = re.compile(
    r"-----BEGIN (?:TRUSTED )?CERTIFICATE-----(.+?)"
    r"-----END (?:TRUSTED )?CERTIFICATE-----",
    re.DOTALL,
)
LONG_FORM_LENGTH = 0x80


def _first_der_element(der: bytes) -> bytes:
    """The leading DER element - the certificate, without any trust settings
    after it."""
    length = der[1]
    header = 2
    if length >= LONG_FORM_LENGTH:
        header += length - LONG_FORM_LENGTH
        length = int.from_bytes(der[2:header], "big")
    return der[: header + length]


def fingerprints(text: str) -> set:
    return {
        hashlib.sha256(_first_der_element(base64.b64decode(body))).hexdigest()
        for body in PEM_BLOCK.findall(text)
    }


def trust_stores() -> tuple:
    """Certifi's bundle and the system bundle, then the files of the
    certificate directory.

    Resolved, so a bundle and a link to it in the directory are read
    once.
    """
    paths = ssl.get_default_verify_paths()
    if not paths.cafile:
        sys.exit("check_trust_store: OpenSSL has no default CA file")
    bundles = [Path(certifi.where()).resolve(), Path(paths.cafile).resolve()]
    # get_default_verify_paths() reports capath as None when the directory does
    # not exist; Path("") would be the working directory.
    certs_dir = Path(paths.capath).iterdir() if paths.capath else []
    dir_files = {path.resolve() for path in certs_dir if path.is_file()}
    return bundles, sorted(dir_files - set(bundles))


def find_distrusted() -> dict:
    bundles, dir_files = trust_stores()
    hits = {}
    for path in bundles + dir_files:
        text = path.read_text(errors="replace") if path.is_file() else ""
        found = fingerprints(text)
        # A missing or empty bundle would pass without checking anything.
        if path in bundles and not found:
            sys.exit(f"check_trust_store: no certificates in trust store {path}")
        roots = sorted(DISTRUSTED_ROOTS[fp] for fp in found & DISTRUSTED_ROOTS.keys())
        if roots:
            hits[path] = roots
    return hits


if __name__ == "__main__":
    hits = find_distrusted()
    if hits:
        found = "; ".join(f"{path}: {', '.join(roots)}" for path, roots in hits.items())
        sys.exit(
            f"check_trust_store: compromised eMudhra roots are still trusted: {found}"
        )
