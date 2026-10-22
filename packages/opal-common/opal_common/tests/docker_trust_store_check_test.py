"""Tests for scripts/check_trust_store.py, the Docker build's gate on the
compromised eMudhra CAs (CVE-2026-111943).

The image build runs the script against its real trust stores, where
none of the keys should be present, so a broken check passes there
silently. These tests feed it stores that do hold them. The script is a
standalone build helper, not part of a package, so it is loaded by path,
and the tests skip where it is not next to the package (an installed
opal-common).
"""

import base64
import hashlib
import importlib.util
import re
import ssl
import warnings
from pathlib import Path

import certifi
import pytest
from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_trust_store.py"
if not _SCRIPT.is_file():
    pytest.skip(f"{_SCRIPT} is not here", allow_module_level=True)
_spec = importlib.util.spec_from_file_location("check_trust_store", _SCRIPT)
check_trust_store = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_trust_store)

FIXTURE = Path(__file__).with_name("emudhra_compromised_cas.pem")
# A PEM block, and the first of the comment lines above it, if any.
BLOCK = re.compile(
    r"(?:^# ([^\n]+)\n)?(?:^#[^\n]*\n)*(-----BEGIN CERTIFICATE-----\n.+?-----END CERTIFICATE-----\n)",
    re.MULTILINE | re.DOTALL,
)
# The fixture's certificates by the name in the comment above each.
CAS = dict(BLOCK.findall(FIXTURE.read_text()))
G3 = "emSign ECC Root CA - G3"
CROSS_SIGN = "EM DV TLS CA - G3B, cross-signed by AAA Certificate Services"


def _blocks(text: str) -> list[str]:
    return [pem for _, pem in BLOCK.findall(text)]


def _key_hash(pem: str) -> str:
    """The SubjectPublicKeyInfo SHA-256, computed by cryptography rather than
    by the script."""
    with warnings.catch_warnings():
        warnings.simplefilter(
            "ignore"
        )  # a negative serial in a real root only warns, for now
        cert = x509.load_pem_x509_certificate(pem.encode())
    return hashlib.sha256(
        cert.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    ).hexdigest()


def _relabelled(pem: str, label: str, trailer: bytes = b"") -> str:
    """The same certificate under another PEM label, its DER followed by
    trailer."""
    body = base64.encodebytes(ssl.PEM_cert_to_DER_cert(pem) + trailer).decode()
    return f"-----BEGIN {label}-----\n{body}-----END {label}-----\n"


@pytest.fixture
def stores(tmp_path, monkeypatch):
    """A certifi bundle, a system bundle and a certificate directory, holding
    clean roots only."""
    certifi_pems = _blocks(Path(certifi.where()).read_text())
    clean = "".join(
        pem
        for pem in certifi_pems
        if _key_hash(pem) not in check_trust_store.DISTRUSTED_KEYS
    )
    certifi_bundle = tmp_path / "cacert.pem"
    system_bundle = tmp_path / "cert.pem"
    certs_dir = tmp_path / "certs"
    certs_dir.mkdir()
    certifi_bundle.write_text(clean)
    system_bundle.write_text(clean)
    monkeypatch.setattr(check_trust_store.certifi, "where", lambda: str(certifi_bundle))
    monkeypatch.setattr(
        check_trust_store.ssl,
        "get_default_verify_paths",
        lambda: ssl.DefaultVerifyPaths(
            str(system_bundle),
            str(certs_dir),
            "SSL_CERT_FILE",
            str(system_bundle),
            "SSL_CERT_DIR",
            str(certs_dir),
        ),
    )
    return certifi_bundle, system_bundle, certs_dir


def test_the_denied_keys_are_the_fixture_certificates():
    # A typo in a key hash would make that key's part of the gate silently do nothing: every key
    # but emSign ECC Root CA - G3's matches nothing in the image's stores.
    names = {_key_hash(pem): name for name, pem in CAS.items() if name != CROSS_SIGN}
    assert names == check_trust_store.DISTRUSTED_KEYS
    assert _key_hash(CAS[CROSS_SIGN]) == _key_hash(CAS["EM DV TLS CA - G3B"])


def test_the_key_walk_agrees_with_cryptography_on_every_real_root():
    pems = _blocks(Path(certifi.where()).read_text()) + list(CAS.values())
    assert len(pems) > 100
    for pem in pems:
        assert check_trust_store.key_hashes(pem) == {_key_hash(pem)}


def test_locked_certifi_does_not_trust_them():
    found = check_trust_store.key_hashes(Path(certifi.where()).read_text())
    assert found
    assert not found & check_trust_store.DISTRUSTED_KEYS.keys()


@pytest.mark.usefixtures("stores")
def test_clean_stores_pass():
    assert check_trust_store.find_distrusted() == {}


@pytest.mark.parametrize("name", sorted(CAS))
@pytest.mark.parametrize("store", [0, 1], ids=["certifi", "system"])
def test_any_certificate_for_a_denied_key_is_found(stores, store, name):
    bundle = stores[store]
    bundle.write_text(bundle.read_text() + CAS[name])
    expected = "EM DV TLS CA - G3B" if name == CROSS_SIGN else name
    assert check_trust_store.find_distrusted() == {bundle.resolve(): [expected]}


def test_root_in_the_certificate_directory_is_found(stores):
    _, _, certs_dir = stores
    (certs_dir / "14bc7599.0").write_text(CAS[G3])
    assert check_trust_store.find_distrusted() == {
        (certs_dir / "14bc7599.0").resolve(): [G3]
    }


@pytest.mark.parametrize(
    ("label", "trailer"),
    # A TRUSTED CERTIFICATE's DER is followed by OpenSSL's trust settings; any DER element stands in.
    [("TRUSTED CERTIFICATE", bytes.fromhex("3003020100")), ("X509 CERTIFICATE", b"")],
)
def test_every_label_openssl_loads_is_read(stores, label, trailer):
    _, system_bundle, _ = stores
    system_bundle.write_text(
        system_bundle.read_text() + _relabelled(CAS[G3], label, trailer)
    )
    assert check_trust_store.find_distrusted() == {system_bundle.resolve(): [G3]}


def test_a_link_to_a_bundle_is_reported_once(stores):
    _, system_bundle, certs_dir = stores
    system_bundle.write_text(system_bundle.read_text() + CAS[G3])
    (certs_dir / "ca-certificates.crt").symlink_to(system_bundle)
    assert check_trust_store.find_distrusted() == {system_bundle.resolve(): [G3]}


@pytest.mark.parametrize("store", [0, 1], ids=["certifi", "system"])
@pytest.mark.parametrize("state", ["empty", "missing"])
def test_an_empty_or_missing_bundle_fails(stores, store, state):
    bundle = stores[store]
    if state == "empty":
        bundle.write_text("")
    else:
        bundle.unlink()
    with pytest.raises(SystemExit, match="no certificates in trust store"):
        check_trust_store.find_distrusted()


@pytest.mark.parametrize(
    "body", ["", "not base64!\n", base64.encodebytes(b"\x30\x82\x01\x00").decode()]
)
def test_an_unparsable_certificate_fails_with_its_file(stores, body):
    _, _, certs_dir = stores
    (certs_dir / "broken.pem").write_text(
        f"-----BEGIN CERTIFICATE-----\n{body}-----END CERTIFICATE-----\n"
    )
    with pytest.raises(SystemExit, match=r"broken\.pem: unparsable certificate"):
        check_trust_store.find_distrusted()


def test_no_certificate_directory_does_not_scan_the_working_directory(
    stores, tmp_path, monkeypatch
):
    # get_default_verify_paths() reports capath as None when the directory does not exist. The
    # check must then skip it, not fall back to Path("") - the working directory.
    certifi_bundle, system_bundle, _ = stores
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    (cwd / "stray.pem").write_text(CAS[G3])
    monkeypatch.chdir(cwd)
    monkeypatch.setattr(
        check_trust_store.ssl,
        "get_default_verify_paths",
        lambda: ssl.DefaultVerifyPaths(
            str(system_bundle),
            None,  # what Python reports when the directory is missing
            "SSL_CERT_FILE",
            str(system_bundle),
            "SSL_CERT_DIR",
            "/nonexistent",
        ),
    )
    assert check_trust_store.trust_stores() == (
        [certifi_bundle.resolve(), system_bundle.resolve()],
        [],
    )
    assert check_trust_store.find_distrusted() == {}
