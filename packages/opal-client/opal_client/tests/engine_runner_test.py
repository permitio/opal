import pytest
from opal_client.engine.options import (
    AuthenticationScheme,
    AuthorizationScheme,
    CedarServerOptions,
    LogLevel,
    OpaServerOptions,
)


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


@pytest.mark.parametrize(
    "options",
    [
        # the default production path - INLINE_OPA_CONFIG resolves to
        # OpaServerOptions.model_validate({}), so every option is a default
        OpaServerOptions.model_validate({}),
        OpaServerOptions(),
        OpaServerOptions(log_level="debug"),
        OpaServerOptions(log_level=LogLevel.debug),
        OpaServerOptions(authentication=AuthenticationScheme.token),
        OpaServerOptions(authorization=AuthorizationScheme.basic),
    ],
)
def test_opa_cli_options_are_all_exactly_str(options: OpaServerOptions):
    """Every value handed to the OPA cli must be exactly ``str``.

    ``runner.py`` builds argv with ``f"{k}={v}"``, so an enum member surviving
    the dump renders as ``LogLevel.info`` on python 3.11+ (``Enum.__format__``
    changed there) and OPA rejects the flag at parse time.

    Note this asserts ``type(value) is str`` rather than ``isinstance``: these
    enums are ``str`` mixins, so ``isinstance(LogLevel.info, str)`` is True and
    an ``isinstance`` check would pass on exactly the broken value. Guards the
    whole class of regression, not just the fields set above.
    """
    for key, value in options.get_cli_options_dict().items():
        assert type(value) is str, f"{key} is {type(value).__name__}, not str"


@pytest.mark.parametrize(
    "options",
    [
        OpaServerOptions.model_validate({}),
        OpaServerOptions(),
        OpaServerOptions(log_level="debug"),
        OpaServerOptions(log_level=LogLevel.debug),
        OpaServerOptions(authentication=AuthenticationScheme.token),
    ],
)
def test_opa_cli_argv_never_renders_an_enum_repr(options: OpaServerOptions):
    """The rendered argv is what OPA actually parses - assert on that.

    Comparing the dict values to ``"off"`` would *also* pass on a broken value,
    since a ``str`` mixin compares equal to its own value; only formatting
    exposes the difference.
    """
    argv = [f"{k}={v}" for k, v in options.get_cli_options_dict().items()]

    for arg in argv:
        assert "." not in arg.split("=", 1)[1] or arg.startswith(
            "--addr="
        ), f"enum repr leaked into argv: {arg}"


def test_opa_cli_argv_for_all_defaults():
    """The default production path: ``OpaServerOptions.model_validate({})``."""
    options = OpaServerOptions.model_validate({})

    argv = [f"{k}={v}" for k, v in options.get_cli_options_dict().items()]

    assert argv == [
        "--addr=0.0.0.0:8181",
        "--authentication=off",
        "--authorization=off",
        "--log-level=info",
    ]


def test_opa_cli_explicit_value_does_not_leak_other_defaults():
    """Setting one option must not leave the untouched ones as enum members."""
    options = OpaServerOptions(log_level=LogLevel.debug)

    argv = [f"{k}={v}" for k, v in options.get_cli_options_dict().items()]

    assert argv == [
        "--addr=0.0.0.0:8181",
        "--authentication=off",
        "--authorization=off",
        "--log-level=debug",
    ]
