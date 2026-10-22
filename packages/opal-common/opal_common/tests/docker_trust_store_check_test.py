"""Tests for scripts/check_trust_store.py, the Docker build's gate on the
compromised eMudhra roots (CVE-2026-111943).

The image build runs the script against its real trust stores, where
none of the roots should be present, so a broken check passes there
silently. These tests feed it stores that do hold them. The script is a
standalone build helper, not part of a package, so it is loaded by path.
"""

import base64
import hashlib
import importlib.util
import re
import ssl
from pathlib import Path

import certifi
import pytest

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_trust_store.py"
_spec = importlib.util.spec_from_file_location("check_trust_store", _SCRIPT)
check_trust_store = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_trust_store)

FIXTURE = Path(__file__).with_name("emudhra_distrusted_roots.pem")
ROOT_PEMS = re.findall(
    r"-----BEGIN CERTIFICATE-----.+?-----END CERTIFICATE-----\n",
    FIXTURE.read_text(),
    re.DOTALL,
)
G3 = "emSign ECC Root CA - G3"


def _pem(name):
    for pem in ROOT_PEMS:
        digest = hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest()
        if check_trust_store.DISTRUSTED_ROOTS.get(digest) == name:
            return pem
    raise AssertionError(f"no fixture certificate for {name}")


def _trusted_form(pem):
    """The same certificate as OpenSSL's TRUSTED CERTIFICATE: its DER, then
    trust settings."""
    aux = bytes.fromhex("3003020100")  # stands in for X509_CERT_AUX
    body = base64.encodebytes(ssl.PEM_cert_to_DER_cert(pem) + aux).decode()
    return (
        f"-----BEGIN TRUSTED CERTIFICATE-----\n{body}"
        "-----END TRUSTED CERTIFICATE-----\n"
    )


def _verify_paths(cafile, capath):
    return ssl.DefaultVerifyPaths(
        cafile, capath, "SSL_CERT_FILE", cafile, "SSL_CERT_DIR", capath or "/none"
    )


@pytest.fixture
def stores(tmp_path, monkeypatch):
    """A certifi bundle, a system bundle and a certificate directory, holding
    only clean roots: certifi's, without any distrusted one, whatever certifi
    is installed."""
    clean = "".join(
        block
        for block in re.findall(
            r"-----BEGIN CERTIFICATE-----.+?-----END CERTIFICATE-----\n",
            Path(certifi.where()).read_text(),
            re.DOTALL,
        )
        if hashlib.sha256(ssl.PEM_cert_to_DER_cert(block)).hexdigest()
        not in check_trust_store.DISTRUSTED_ROOTS
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
        lambda: _verify_paths(str(system_bundle), str(certs_dir)),
    )
    return certifi_bundle, system_bundle, certs_dir


def test_fingerprints_are_the_fixture_roots():
    # A typo in a fingerprint would make that root's part of the gate silently
    # do nothing.
    assert len(ROOT_PEMS) == len(check_trust_store.DISTRUSTED_ROOTS)
    digests = {
        hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest() for pem in ROOT_PEMS
    }
    assert digests == set(check_trust_store.DISTRUSTED_ROOTS)


@pytest.mark.usefixtures("stores")
def test_clean_stores_pass():
    assert check_trust_store.find_distrusted() == {}


@pytest.mark.parametrize("name", sorted(check_trust_store.DISTRUSTED_ROOTS.values()))
@pytest.mark.parametrize("store", [0, 1], ids=["certifi", "system"])
def test_root_in_a_bundle_is_found(stores, store, name):
    bundle = stores[store]
    bundle.write_text(bundle.read_text() + _pem(name))
    assert check_trust_store.find_distrusted() == {bundle.resolve(): [name]}


def test_root_in_the_certificate_directory_is_found(stores):
    _, _, certs_dir = stores
    (certs_dir / "14bc7599.0").write_text(_pem(G3))
    expected = {(certs_dir / "14bc7599.0").resolve(): [G3]}
    assert check_trust_store.find_distrusted() == expected


def test_trusted_certificate_form_is_found(stores):
    _, system_bundle, _ = stores
    system_bundle.write_text(system_bundle.read_text() + _trusted_form(_pem(G3)))
    assert check_trust_store.find_distrusted() == {system_bundle.resolve(): [G3]}


def test_a_link_to_a_bundle_is_reported_once(stores):
    _, system_bundle, certs_dir = stores
    system_bundle.write_text(system_bundle.read_text() + _pem(G3))
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


def test_no_certificate_directory_does_not_scan_the_working_directory(
    stores, tmp_path, monkeypatch
):
    # get_default_verify_paths() reports capath as None when the directory does
    # not exist. The check must skip it, not fall back to Path("") - the
    # working directory.
    certifi_bundle, system_bundle, _ = stores
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    (cwd / "stray.pem").write_text(_pem(G3))
    monkeypatch.chdir(cwd)
    monkeypatch.setattr(
        check_trust_store.ssl,
        "get_default_verify_paths",
        lambda: _verify_paths(str(system_bundle), None),
    )
    bundles = [certifi_bundle.resolve(), system_bundle.resolve()]
    assert check_trust_store.trust_stores() == (bundles, [])
    assert check_trust_store.find_distrusted() == {}
