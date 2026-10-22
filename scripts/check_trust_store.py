"""Build-time check that the image no longer trusts the compromised eMudhra
CAs.

The private keys of eight eMudhra intermediate CAs can be recovered from their
certificates (CVE-2026-111943), so anyone can mint a certificate for any host
that a client trusting their roots accepts. Browsers are covered by Certificate
Transparency; OPAL's clients are not, and trust whatever the image carries.
docker/Dockerfile bind-mounts and runs this in both common stages, so every
image fails to build if a trust store its TLS clients read still holds either
root those intermediates chain to:

* certifi's bundle - requests and httpx verify against it by default.
* the system bundle and certificate directory (from Debian's or Alpine's
  ca-certificates) - aiohttp, websockets, git and the stdlib ssl module through
  OpenSSL, and the bundled OPA through Go's crypto/x509.

The fix is certifi >= 2026.10.19 (floored in opal-common's requires.txt) and
the patched ca-certificates the Dockerfile upgrades to. This check is what
notices when either goes missing, e.g. a layer replayed from a cache older than
the fix.
"""

import hashlib
import re
import ssl
import sys
from pathlib import Path

import certifi

# SHA-256 of each root's DER encoding.
DISTRUSTED_ROOTS = {
    "86a1ecba089c4a8d3bbe2734c612ba341d813e043cf9e8a862cd5c57a36bbe6b": "emSign ECC Root CA - G3",
    # Signs a Sectigo cross-sign of each intermediate.
    "d7a7a0fb5d7e2731d771e9484ebcdef71d5f0c3e0a2948782bc83ee0ea699ef4": "AAA Certificate Services",
}
PEM_BLOCK = re.compile(
    r"-----BEGIN CERTIFICATE-----.+?-----END CERTIFICATE-----", re.DOTALL
)


def fingerprints(path: Path) -> set:
    return {
        hashlib.sha256(ssl.PEM_cert_to_DER_cert(block)).hexdigest()
        for block in PEM_BLOCK.findall(path.read_text(errors="replace"))
    }


def trust_store_files() -> list:
    """The two bundles, which must exist and hold certificates, then the
    certificate directory."""
    paths = ssl.get_default_verify_paths()
    bundles = [Path(certifi.where()), Path(paths.cafile or "")]
    for bundle in bundles:
        # A missing or empty bundle would pass the check below without checking anything.
        if not bundle.is_file() or not fingerprints(bundle):
            sys.exit(f"check_trust_store: no certificates in trust store '{bundle}'")
    certs_dir = Path(paths.capath or "")
    if not certs_dir.is_dir():
        return bundles
    return bundles + sorted(p for p in certs_dir.iterdir() if p.is_file())


if __name__ == "__main__":
    hits = {
        path: sorted(DISTRUSTED_ROOTS[fp] for fp in found)
        for path in trust_store_files()
        if (found := fingerprints(path) & DISTRUSTED_ROOTS.keys())
    }
    if hits:
        found = "; ".join(f"{path}: {', '.join(roots)}" for path, roots in hits.items())
        sys.exit(
            f"check_trust_store: compromised eMudhra roots are still trusted: {found}"
        )
