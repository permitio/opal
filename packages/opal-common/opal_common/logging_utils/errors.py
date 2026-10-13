from opal_common.http_utils import redact_sensitive_text
from pydantic import ValidationError


def describe_validation_error(err: ValidationError) -> str:
    """Summarize a pydantic ValidationError without the rejected input.

    pydantic v2 renders ``input_value=...`` into the error text, and the
    rejected input is often a whole config or payload carrying auth headers.
    This keeps only what is needed to fix it: the model, the error count, and
    each error's location and type.

    Args:
        err: The validation error to summarize.

    Returns:
        The summary, e.g. ``"2 validation errors for DataSourceEntry: url
        (missing); topics (list_type)"``.
    """
    locations = "; ".join(
        f"{'.'.join(str(part) for part in error['loc']) or '<root>'} ({error['type']})"
        for error in err.errors(
            include_url=False, include_context=False, include_input=False
        )
    )
    count = err.error_count()
    noun = "error" if count == 1 else "errors"
    return f"{count} validation {noun} for {err.title}: {locations}"


def describe_error(err: BaseException, url: str = "") -> str:
    """Render an exception for a log line or an error string.

    Use instead of ``repr(err)``: aiohttp's ``ClientResponseError`` and
    ``ContentTypeError`` reprs include the request headers (and with them the
    Authorization header), and ``ClientConnectorError`` can include proxy auth.
    ``str()`` of those omits the headers; any URL credentials, sensitive query
    params or auth header values left in the message are masked too.

    Args:
        err: The exception to describe.
        url: A URL the message may quote (e.g. the one being fetched), redacted
            as a whole before the generic masking runs.

    Returns:
        ``"<ExceptionType>: <redacted message>"``, or just the type name when the
        exception has no message (e.g. a ``TimeoutError``).
    """
    if isinstance(err, ValidationError):
        message = describe_validation_error(err)
    else:
        message = redact_sensitive_text(str(err), url)
    name = type(err).__name__
    return f"{name}: {message}" if message else name
