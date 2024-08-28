import functools
import os
import random

import pytest
from fastapi import Response, status
from opal_client.policy_store.opa_client import OpaClient, should_ignore_path
from opal_client.policy_store.schemas import PolicyStoreAuth

TEST_CA_CERT = """-----BEGIN CERTIFICATE-----
MIIBdjCCAR2gAwIBAgIUaQ/M1qL0GzsTMChEAJsLLFgz7a4wCgYIKoZIzj0EAwIw
EDEOMAwGA1UEAwwFbXktY2EwIBcNMjMwNTE1MDkzMDI2WhgPMjg0NDA5MjcwOTMw
MjZaMBAxDjAMBgNVBAMMBW15LWNhMFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE
NKA1Q8QEl9/jA1/e4EZmrJpX3qprKOQ26H6aoFkqLF4UN43R/hG+sLnqlxWK5Eis
iqm4AY7UIUMbL+UmzccXt6NTMFEwHQYDVR0OBBYEFHLLeNFR/WQCn/t7gDa8jC/A
UHmAMB8GA1UdIwQYMBaAFHLLeNFR/WQCn/t7gDa8jC/AUHmAMA8GA1UdEwEB/wQF
MAMBAf8wCgYIKoZIzj0EAwIDRwAwRAIgNAP8VQsRoEeiUzLUr3I3+AiRWesnLnPg
okEOHA1r6hQCIH4jaSUrDN51u9uTvYw0UPmGk5TqaBtWpEuzgCKzOjy+
-----END CERTIFICATE-----"""


def parse_nested_tuple(tuple, key):
    if tuple[0] == key:
        return tuple[1]
    p = [parse_nested_tuple(item, key) for item in tuple]
    return p[1]


def test_constuctor_should_panic_tls_configured_without_all_parts():
    with pytest.raises(Exception, match="required variables for tls are not set"):
        OpaClient(
            "http://example.com",
            opa_auth_token=None,
            auth_type=PolicyStoreAuth.TLS,
            oauth_client_id=None,
            oauth_client_secret=None,
            oauth_server=None,
            data_updater_enabled=None,
            tls_client_cert=None,
            tls_client_key=None,
            tls_ca=None,
        )


def test_constructor_should_set_up_ca_certificate_even_without_tls_auth_type(tmpdir):
    ca_path = os.path.join(tmpdir, "ca.pem")
    with open(ca_path, "w") as ca:
        ca.write(TEST_CA_CERT)

    c = OpaClient(
        "http://example.com",
        opa_auth_token=None,
        auth_type=PolicyStoreAuth.NONE,
        oauth_client_id=None,
        oauth_client_secret=None,
        oauth_server=None,
        data_updater_enabled=None,
        tls_client_cert=None,
        tls_client_key=None,
        tls_ca=ca_path,
    )
    assert c._custom_ssl_context != None
    certs = c._custom_ssl_context.get_ca_certs(binary_form=False)
    assert len(certs) == 1


@pytest.mark.asyncio
async def test_attempt_operations_with_postponed_failure_retry():
    class OrderStrictOps:
        def __init__(self, loadable=True):
            self.next_allowed_module = 0
            self.badly_ordered_bundle = list(range(random.randint(5, 25)))

            if not loadable:
                # Remove a random module from the bundle, so dependent modules won't be able to ever load
                self.badly_ordered_bundle.pop(
                    random.randint(0, len(self.badly_ordered_bundle) - 2)
                )

            random.shuffle(self.badly_ordered_bundle)

        async def _policy_op(self, module: int) -> Response:
            if self.next_allowed_module == module:
                self.next_allowed_module += 1
                return Response(status_code=status.HTTP_200_OK)
            else:
                return Response(
                    status_code=random.choice(
                        [status.HTTP_400_BAD_REQUEST, status.HTTP_404_NOT_FOUND]
                    ),
                    content=f"Module {module} is in bad order, can't load before {self.next_allowed_module}",
                )

        def get_badly_ordered_ops(self):
            return [
                functools.partial(self._policy_op, module)
                for module in self.badly_ordered_bundle
            ]

    order_strict_ops = OrderStrictOps()

    # Shouldn't raise
    await OpaClient._attempt_operations_with_postponed_failure_retry(
        order_strict_ops.get_badly_ordered_ops()
    )

    order_strict_ops = OrderStrictOps(loadable=False)

    # Should raise, can't complete all operations
    with pytest.raises(RuntimeError):
        await OpaClient._attempt_operations_with_postponed_failure_retry(
            order_strict_ops.get_badly_ordered_ops()
        )


def test_should_not_ignore_anything_with_no_ignore_paths():
    ignore_paths = []
    assert should_ignore_path("myFolder", ignore_paths) == False
    assert should_ignore_path("myFolder/file.txt", ignore_paths) == False
    assert should_ignore_path("otherFolder", ignore_paths) == False
    assert should_ignore_path("otherFolder/file.txt", ignore_paths) == False


def test_should_ignore_everything_with_root_as_ignore_paths():
    ignore_paths = ["/"]
    assert should_ignore_path("myFolder", ignore_paths) == True
    assert should_ignore_path("myFolder/file.txt", ignore_paths) == True
    assert should_ignore_path("otherFolder", ignore_paths) == True
    assert should_ignore_path("otherFolder/file.txt", ignore_paths) == True


def test_should_ignore_everything_with_root_and_asterisks_as_ignore_paths():
    ignore_paths = ["/**"]
    assert should_ignore_path("myFolder", ignore_paths) == True
    assert should_ignore_path("myFolder/file.txt", ignore_paths) == True
    assert should_ignore_path("otherFolder", ignore_paths) == True
    assert should_ignore_path("otherFolder/file.txt", ignore_paths) == True


def test_should_ignore_path_but_not_his_contents_when_path_is_defined_without_asterisks():
    ignore_paths = ["myFolder"]
    assert should_ignore_path("myFolder", ignore_paths) == True
    assert should_ignore_path("myFolder/file.txt", ignore_paths) == False
    assert should_ignore_path("otherFolder", ignore_paths) == False
    assert should_ignore_path("otherFolder/file.txt", ignore_paths) == False


def test_should_ignore_path_and_his_contents_when_path_is_defined_with_asterisks():
    ignore_paths = ["myFolder/**"]
    assert should_ignore_path("myFolder", ignore_paths) == True
    assert should_ignore_path("myFolder/file.txt", ignore_paths) == True
    assert should_ignore_path("otherFolder", ignore_paths) == False
    assert should_ignore_path("otherFolder/file.txt", ignore_paths) == False


def test_should_not_ignore_anything_with_not_ignore_paths_only():
    ignore_paths = ["!myFolder/**"]
    assert should_ignore_path("myFolder", ignore_paths) == False
    assert should_ignore_path("myFolder/file.txt", ignore_paths) == False
    assert should_ignore_path("otherFolder", ignore_paths) == False
    assert should_ignore_path("otherFolder/file.txt", ignore_paths) == False


def test_should_ignore_path_but_ones_specified_as_not_ignore_paths():
    ignore_paths = ["/", "!myFolder"]
    assert should_ignore_path("myFolder", ignore_paths) == False
    assert should_ignore_path("myFolder/file.txt", ignore_paths) == True
    assert should_ignore_path("otherFolder", ignore_paths) == True
    assert should_ignore_path("otherFolder/file.txt", ignore_paths) == True


def test_should_ignore_path_but_ones_specified_as_not_ignore_paths_and_his_contents_when_defined_with_asterisks():
    ignore_paths = ["/", "!myFolder/**"]
    assert should_ignore_path("myFolder", ignore_paths) == False
    assert should_ignore_path("myFolder/file.txt", ignore_paths) == False
    assert should_ignore_path("otherFolder", ignore_paths) == True
    assert should_ignore_path("otherFolder/file.txt", ignore_paths) == True


def test_should_ignore_path_keeping_higher_priority_to_ones_defined_as_not_to_ignore_A():
    ignore_paths = ["myFolder/**", "!myFolder/subFolder/**"]
    assert should_ignore_path("myFolder/file.txt", ignore_paths) == True
    assert should_ignore_path("myFolder/subFolder", ignore_paths) == False
    assert should_ignore_path("myFolder/subFolder/file.txt", ignore_paths) == False
    assert should_ignore_path("myFolder/anotherSubFolder", ignore_paths) == True
    assert (
        should_ignore_path("myFolder/anotherSubFolder/file.txt", ignore_paths) == True
    )
    assert should_ignore_path("otherFolder", ignore_paths) == False
    assert should_ignore_path("otherFolder/file.txt", ignore_paths) == False


def test_should_ignore_path_keeping_higher_priority_to_ones_defined_as_not_to_ignore_B():
    ignore_paths = ["/", "myFolder/**", "!myFolder/subFolder/**"]
    assert should_ignore_path("myFolder/file.txt", ignore_paths) == True
    assert should_ignore_path("myFolder/subFolder", ignore_paths) == False
    assert should_ignore_path("myFolder/subFolder/file.txt", ignore_paths) == False
    assert should_ignore_path("myFolder/anotherSubFolder", ignore_paths) == True
    assert (
        should_ignore_path("myFolder/anotherSubFolder/file.txt", ignore_paths) == True
    )
    assert should_ignore_path("otherFolder", ignore_paths) == True
    assert should_ignore_path("otherFolder/file.txt", ignore_paths) == True


def test_should_ignore_path_keeping_higher_priority_to_ones_defined_as_not_to_ignore_C():
    ignore_paths = ["!myFolder/**", "myFolder/subFolder/**"]
    assert should_ignore_path("myFolder/file.txt", ignore_paths) == False
    assert should_ignore_path("myFolder/subFolder", ignore_paths) == False
    assert should_ignore_path("myFolder/subFolder/file.txt", ignore_paths) == False
    assert should_ignore_path("myFolder/anotherSubFolder", ignore_paths) == False
    assert (
        should_ignore_path("myFolder/anotherSubFolder/file.txt", ignore_paths) == False
    )
    assert should_ignore_path("otherFolder", ignore_paths) == False
    assert should_ignore_path("otherFolder/file.txt", ignore_paths) == False


def test_should_ignore_path_keeping_higher_priority_to_ones_defined_as_not_to_ignore_D():
    ignore_paths = ["/", "!myFolder/**", "myFolder/subFolder/**"]
    assert should_ignore_path("myFolder/file.txt", ignore_paths) == False
    assert should_ignore_path("myFolder/subFolder", ignore_paths) == False
    assert should_ignore_path("myFolder/subFolder/file.txt", ignore_paths) == False
    assert should_ignore_path("myFolder/anotherSubFolder", ignore_paths) == False
    assert (
        should_ignore_path("myFolder/anotherSubFolder/file.txt", ignore_paths) == False
    )
    assert should_ignore_path("otherFolder", ignore_paths) == True
    assert should_ignore_path("otherFolder/file.txt", ignore_paths) == True
