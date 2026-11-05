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
    rotation/retention) opens the file itself, so it is scrubbed by
    ``CredentialScrubbingFileSink`` instead.
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


class CredentialScrubbingFileSink:
    """Loguru's rotating file sink, with credentials masked in every fully-
    formatted record before it is written.

    ``logger.add(path, rotation=..., retention=..., compression=...)`` builds
    the file sink from a path, so there is no stream to wrap with
    ``CredentialScrubbingStream``. This builds the same loguru ``FileSink`` and
    is added to loguru as a stream sink instead, so the file gets the same
    masking as the stream: message, extra values of any type, and rendered
    tracebacks.
    """

    def __init__(self, path, **file_sink_kwargs):
        # FileSink is private loguru API. Imported here, not at module level,
        # so a loguru release that moves it breaks only LOG_TO_FILE.
        from loguru._file_sink import FileSink

        self._sink = FileSink(path, **file_sink_kwargs)
        #: loguru reads these from a stream sink; a path sink gets them the
        #: same way (the FileSink's encoding, the path as the handler's name).
        self.encoding = self._sink.encoding
        self.name = repr(str(path))

    def write(self, message):
        # loguru's Message is a str carrying its record; time-based rotation
        # reads message.record["time"], so the masked text keeps it.
        scrubbed = type(message)(redact_sensitive_text(message))
        scrubbed.record = message.record
        self._sink.write(scrubbed)

    def stop(self):
        # loguru calls this on logger.remove(); it closes the file.
        self._sink.stop()
