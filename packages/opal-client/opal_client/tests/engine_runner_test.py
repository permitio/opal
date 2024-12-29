import pytest
from opal_client.engine.options import AuthenticationScheme, CedarServerOptions


@pytest.mark.parametrize(
    "options,expected",
    [
        (CedarServerOptions(), "--addr 0.0.0.0 --port 8180"),
        (CedarServerOptions(addr=":1234"), "--addr 0.0.0.0 --port 1234"),
        (CedarServerOptions(addr="1.2.3.4:1234"), "--addr 1.2.3.4 --port 1234"),
        (
            CedarServerOptions(
                authentication=AuthenticationScheme.token,
                authentication_token="mytoken",
            ),
            "-a mytoken --addr 0.0.0.0 --port 8180",
        ),
    ],
)
def test_cedar_arguments(options: CedarServerOptions, expected: str):
    expected_args = expected.split(" ")
    assert list(options.get_args()) == expected_args
