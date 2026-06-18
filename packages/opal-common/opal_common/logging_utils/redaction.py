from typing import ClassVar, Set


class RedactedReprMixin:
    """Mixin for pydantic (v1) models that may carry credentials.

    Overrides ``repr()`` / ``str()`` so that any field listed in
    ``_redacted_repr_fields`` renders as ``<redacted>`` instead of its real
    value.

    This is the central defense against credential leaks in logs: OPAL logs via
    loguru, and most leaks come from interpolating these models into log
    messages (e.g. ``logger.info("... {entry}", entry=entry)``) or from loguru's
    ``serialize=True`` sink, which falls back to ``str()`` for non-JSON objects.
    Both paths go through ``__repr_args__`` here, so masking once at the model
    layer protects every current and future log site at once.

    Note: this only affects human / log rendering. Wire serialization uses
    ``.dict()`` / ``.json()``, which are untouched, so transport is unaffected.
    """

    #: Field names whose values may carry secrets and must be masked in repr/str.
    _redacted_repr_fields: ClassVar[Set[str]] = set()

    def __repr_args__(self):
        return [
            (key, "<redacted>" if key in self._redacted_repr_fields else value)
            for key, value in super().__repr_args__()
        ]
