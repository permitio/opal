from opal_common.http_utils import redact_sensitive_text
from pydantic import ValidationError


def describe_validation_error(err: ValidationError) -> str:
    """Summarize a pydantic ValidationError without the rejected input.

    The error text renders each error's context, and some contexts hold the
    input - a JSON decode error's ``doc`` is the whole rejected document, often
    a config or payload carrying auth headers. This keeps only what is needed
    to fix it: the model, the error count, and each error's location and type.

    Args:
        err: The validation error to summarize.

    Returns:
        The summary, e.g. ``"2 validation errors for DataSourceEntry: url
        (value_error.missing); topics (type_error.list)"``.
    """
    errors = err.errors()
    locations = "; ".join(
        f"{'.'.join(str(part) for part in error['loc'])} ({error['type']})"
        for error in errors
    )
    noun = "error" if len(errors) == 1 else "errors"
    return f"{len(errors)} validation {noun} for {err.model.__name__}: {locations}"


def describe_error(err: BaseException) -> str:
    """Render an exception for a log line or an error string.

    Use instead of ``repr(err)``: aiohttp's ``ClientResponseError`` and
    ``ContentTypeError`` reprs include the request headers (and with them the
    Authorization header), and ``ClientConnectorError`` can include proxy auth.
    ``str()`` of those omits the headers; any URL credentials, sensitive query
    params or auth header values left in the message are masked too.

    Args:
        err: The exception to describe.

    Returns:
        ``"<ExceptionType>: <redacted message>"``, or just the type name when the
        exception has no message.
    """
    if isinstance(err, ValidationError):
        message = describe_validation_error(err)
    else:
        message = redact_sensitive_text(str(err))
    name = type(err).__name__
    return f"{name}: {message}" if message else name
