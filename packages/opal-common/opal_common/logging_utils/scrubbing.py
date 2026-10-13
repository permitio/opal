from opal_common.http_utils import redact_sensitive_text


class CredentialScrubbingStream:
    """A writable-stream wrapper that masks credentials (URL userinfo,
    sensitive query params, Authorization header values, Bearer/Basic tokens)
    in every fully-formatted log record before it reaches the underlying
    stream.

    This is the catch-all that the model-layer redaction (``RedactedReprMixin``)
    cannot provide: third-party exceptions - most notably aiohttp
    ``ClientResponseError`` - render the full request URL
    (``https://user:pw@host/path?token=...``) inside the traceback that loguru
    formats into the ``{exception}`` slot. The leaking object is not an OPAL
    model, so masking ``repr()`` does nothing for it.

    Because loguru hands a stream sink the *final* formatted text (message +
    traceback, and the JSON blob when ``serialize=True``), scrubbing on
    ``write`` covers every record shape on this sink. ``redact_sensitive_text``
    is idempotent, so the explicit call-site redaction upstream is unaffected.

    Note: this wraps a *stream* sink. loguru's path-based file sink (with
    rotation/retention) opens the file itself and cannot be wrapped this way -
    for that sink only the record's message and top-level ``str`` extra values
    are scrubbed, by the loguru patcher in ``opal_common.logger``. Tracebacks and
    non-``str`` extra values written to the file sink are not scrubbed.
    """

    def __init__(self, stream):
        self._stream = stream

    def write(self, message: str):
        return self._stream.write(redact_sensitive_text(message))

    def flush(self):
        # loguru flushes the sink after each record when possible.
        flush = getattr(self._stream, "flush", None)
        if callable(flush):
            flush()

    def __getattr__(self, name):
        # Delegate everything else (isatty/fileno/encoding/...) to the wrapped
        # stream so loguru treats this exactly like the underlying stream.
        return getattr(self._stream, name)
