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
import os
import re
import ssl
import subprocess
import sys
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
            None,  # it is None when the directory is missing
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


def _tlv(tag: int, content: bytes) -> bytes:
    """A DER element; long-form length when the content needs it."""
    if len(content) < 0x80:
        return bytes([tag, len(content)]) + content
    size = (len(content).bit_length() + 7) // 8
    return bytes([tag, 0x80 | size]) + len(content).to_bytes(size, "big") + content


def _children(der: bytes, element_start: int) -> list[bytes]:
    """The raw child elements of the constructed element at element_start."""
    pos, end = check_trust_store._element(der, element_start)
    children = []
    while pos < end:
        child_end = check_trust_store._element(der, pos)[1]
        children.append(der[pos:child_end])
        pos = child_end
    return children


def _rebuilt(pem: str, edit_tbs) -> str:
    """The certificate with its TBSCertificate's fields passed through
    edit_tbs; the signature no longer verifies, which the key walk never
    checks."""
    der = ssl.PEM_cert_to_DER_cert(pem)
    tbs, sig_alg, sig = _children(der, 0)
    tbs = _tlv(0x30, b"".join(edit_tbs(_children(tbs, 0))))
    return ssl.DER_cert_to_PEM_cert(_tlv(0x30, tbs + sig_alg + sig))


def test_a_v1_certificate_is_walked_without_the_version_field():
    # A v1 TBSCertificate has no [0] version (or [3] extensions); every certifi root is v3.
    v1 = _rebuilt(
        CAS[G3], lambda fields: [f for f in fields if f[0] not in (0xA0, 0xA3)]
    )
    assert ssl.PEM_cert_to_DER_cert(v1) != ssl.PEM_cert_to_DER_cert(CAS[G3])
    assert check_trust_store.key_hashes(v1) == {_key_hash(CAS[G3])}


def _reencoded(
    field: bytes,
    tag: bytes | None = None,
    length: bytes | None = None,
    trailer: bytes = b"",
) -> bytes:
    """A TBSCertificate field with its tag and/or length octets replaced; the
    content is kept."""
    content_start, end = check_trust_store._element(field, 0)
    header_length = field[1:content_start]
    return (
        (tag or field[:1])
        + (length if length is not None else header_length)
        + field[content_start:end]
        + trailer
    )


SERIAL, ISSUER, SUBJECT, KEY = (
    1,
    3,
    5,
    6,
)  # TBSCertificate field positions in a v3 certificate


def _field_content_length(field: bytes) -> int:
    content_start, end = check_trust_store._element(field, 0)
    return end - content_start


NON_DER = {
    # BER's indefinite length: read as empty, it would shift the walk.
    "indefinite issuer": lambda f: [
        *f[:ISSUER],
        _reencoded(f[ISSUER], length=b"\x80", trailer=b"\x00\x00"),
        *f[ISSUER + 1 :],
    ],
    # Five length octets: more than any certificate needs.
    "five length octets": lambda f: [
        *f[:ISSUER],
        _reencoded(
            f[ISSUER],
            length=b"\x85" + _field_content_length(f[ISSUER]).to_bytes(5, "big"),
        ),
        *f[ISSUER + 1 :],
    ],
    # The long form for a length below 128 (30 81 76 instead of 30 76), on the key itself.
    "long form for a short length": lambda f: [
        *f[:KEY],
        _reencoded(f[KEY], length=b"\x81" + bytes([_field_content_length(f[KEY])])),
        *f[KEY + 1 :],
    ],
    # A leading zero length octet (30 82 00 76).
    "leading zero length octet": lambda f: [
        *f[:KEY],
        _reencoded(f[KEY], length=b"\x82\x00" + bytes([_field_content_length(f[KEY])])),
        *f[KEY + 1 :],
    ],
    # A high-tag-number tag for the subject's SEQUENCE: a one-octet reading takes 0x10 as the length.
    "high-tag-number tag": lambda f: [
        *f[:SUBJECT],
        _reencoded(f[SUBJECT], tag=b"\x3f\x10"),
        *f[SUBJECT + 1 :],
    ],
    # A primitive one (1f, not 3f): a mask that only caught constructed forms would miss it.
    "primitive high-tag-number tag": lambda f: [
        *f[:SERIAL],
        _reencoded(f[SERIAL], tag=b"\x1f\x02"),
        *f[SERIAL + 1 :],
    ],
}


@pytest.mark.parametrize("encoding", sorted(NON_DER))
def test_a_non_der_certificate_fails_instead_of_hashing_the_wrong_bytes(
    stores, encoding
):
    # OpenSSL loads several of these as trust anchors with the root's real key, so the gate must
    # refuse the file rather than pass a hash of other bytes.
    _, system_bundle, _ = stores
    system_bundle.write_text(
        _rebuilt(CAS[G3], NON_DER[encoding]) + system_bundle.read_text()
    )
    with pytest.raises(
        SystemExit, match=r"unparsable certificate \(block 1\): .*not DER"
    ):
        check_trust_store.find_distrusted()


@pytest.mark.parametrize(
    ("header", "reason"),
    [
        # Lengths of 128 or more, so the long form is the right form and only the named rule applies.
        pytest.param(
            b"\x30\x85\x01\x00\x00\x00\x00", "oversized", id="five length octets"
        ),
        pytest.param(b"\x30\x82\x00\x80", "non-minimal", id="leading zero octet"),
        pytest.param(b"\x30\x80", "indefinite", id="indefinite"),
        pytest.param(b"\x3f\x10\x81\x80", "high-tag-number", id="high tag number"),
        pytest.param(
            b"\x1f\x02\x81\x80", "high-tag-number", id="primitive high tag number"
        ),
    ],
)
def test_each_non_der_length_rule_on_its_own(header, reason):
    with pytest.raises(ValueError, match=reason):
        check_trust_store._element(header + bytes(128), 0)


def test_a_der_long_form_length_is_read():
    assert check_trust_store._element(b"\x30\x81\x80" + bytes(128), 0) == (3, 131)


@pytest.mark.parametrize(
    "edit",
    [
        # subject removed: the walk ends on the [3] extensions.
        pytest.param(
            lambda f: [x for i, x in enumerate(f) if i != SUBJECT], id="no subject"
        ),
        # issuer duplicated: the walk ends on the subject Name, a SEQUENCE too.
        pytest.param(
            lambda f: [*f[: ISSUER + 1], f[ISSUER], *f[ISSUER + 1 :]], id="issuer twice"
        ),
    ],
)
def test_a_walk_that_does_not_end_on_the_key_fails(stores, edit):
    _, system_bundle, _ = stores
    system_bundle.write_text(_rebuilt(CAS[G3], edit) + system_bundle.read_text())
    with pytest.raises(SystemExit, match=r"block 1\): .*no SubjectPublicKeyInfo"):
        check_trust_store.find_distrusted()


def _key_edited(edit_children):
    """A TBSCertificate edit that rebuilds the SubjectPublicKeyInfo from edited
    children."""

    def edit(fields):
        algorithm, bits = _children(fields[KEY], 0)
        return [
            *fields[:KEY],
            _tlv(0x30, b"".join(edit_children(algorithm, bits))),
            *fields[KEY + 1 :],
        ]

    return edit


def _algorithm_oid_retagged(algorithm: bytes) -> bytes:
    oid, *rest = _children(algorithm, 0)
    return _tlv(0x30, _reencoded(oid, tag=b"\x0d") + b"".join(rest))


# One case per _is_spki condition: each is refused by exactly that condition.
NOT_SPKI = {
    "key tagged SET": lambda f: [
        *f[:KEY],
        _reencoded(f[KEY], tag=b"\x31"),
        *f[KEY + 1 :],
    ],
    "algorithm tagged SET": _key_edited(lambda a, b: [_reencoded(a, tag=b"\x31"), b]),
    "algorithm without OID": _key_edited(lambda a, b: [_algorithm_oid_retagged(a), b]),
    "key bits as OCTET STRING": _key_edited(
        lambda a, b: [a, _reencoded(b, tag=b"\x04")]
    ),
    "element after the key bits": _key_edited(lambda a, b: [a, b, b"\x05\x00"]),
}


@pytest.mark.parametrize("shape", sorted(NOT_SPKI))
def test_a_key_without_spki_shape_fails(stores, shape):
    _, system_bundle, _ = stores
    system_bundle.write_text(
        _rebuilt(CAS[G3], NOT_SPKI[shape]) + system_bundle.read_text()
    )
    with pytest.raises(SystemExit, match=r"block 1\): .*no SubjectPublicKeyInfo"):
        check_trust_store.find_distrusted()


@pytest.mark.usefixtures("stores")
def test_no_default_ca_file_fails_with_its_message(monkeypatch):
    monkeypatch.setattr(
        check_trust_store.ssl,
        "get_default_verify_paths",
        lambda: ssl.DefaultVerifyPaths(
            None,  # it is None when the file is missing
            None,  # it is None when the directory is missing
            "SSL_CERT_FILE",
            "/nonexistent",
            "SSL_CERT_DIR",
            "/nonexistent",
        ),
    )
    with pytest.raises(SystemExit, match="OpenSSL has no default CA file"):
        check_trust_store.find_distrusted()


def test_the_directory_walk_reads_top_level_pem_files_only(stores):
    # What OpenSSL's hashed-directory lookup, Go and rustls-native-certs load: a DER file, a
    # README, a dangling symlink and a subdirectory are not trust anchors, and are skipped.
    _, _, certs_dir = stores
    (certs_dir / "root.der").write_bytes(ssl.PEM_cert_to_DER_cert(CAS[G3]))
    (certs_dir / "README").write_text("certificates are installed by ca-certificates\n")
    (certs_dir / "dangling.pem").symlink_to(certs_dir / "gone.pem")
    (certs_dir / "nested").mkdir()
    (certs_dir / "nested" / "root.pem").write_text(CAS[G3])
    assert check_trust_store.find_distrusted() == {}


@pytest.mark.parametrize("store", [0, 1], ids=["certifi", "system"])
def test_main_names_the_fix_for_each_store(stores, store, capsys):
    bundle = stores[store]
    bundle.write_text(bundle.read_text() + CAS[G3])
    assert check_trust_store.main() == 1
    err = capsys.readouterr().err
    assert f"{bundle.resolve()}: {G3}" in err
    assert (
        check_trust_store.CERTIFI_FIX if store == 0 else check_trust_store.SYSTEM_FIX
    ) in err


@pytest.mark.parametrize("trusted", [True, False], ids=["compromised", "clean"])
def test_the_script_exit_status_is_the_build_gate(stores, trusted):
    # What the Dockerfile runs. certifi's bundle is the installed (locked) one; the system store
    # comes from SSL_CERT_FILE / SSL_CERT_DIR, which get_default_verify_paths() honours.
    _, system_bundle, certs_dir = stores
    if trusted:
        system_bundle.write_text(system_bundle.read_text() + CAS[G3])
    result = subprocess.run(
        [sys.executable, str(Path(check_trust_store.__file__))],
        env={
            **os.environ,
            "SSL_CERT_FILE": str(system_bundle),
            "SSL_CERT_DIR": str(certs_dir),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == (1 if trusted else 0), result.stderr
    assert (G3 in result.stderr) is trusted
