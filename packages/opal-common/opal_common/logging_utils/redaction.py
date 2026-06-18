from typing import ClassVar, Set


class RedactedReprMixin:
    """Mixin for pydantic (v1) models that may carry credentials.

    Overrides ``repr()`` / ``str()`` so that any field listed in
    ``_redacted_repr_fields`` (on this class or *any* of its base classes)
    renders as ``<redacted>`` instead of its real value.

    This is the central defense against credential leaks in logs: OPAL logs via
    loguru, and most leaks come from interpolating these models into log
    messages (e.g. ``logger.info("... {entry}", entry=entry)``) or from loguru's
    ``serialize=True`` sink, which dumps the record as JSON and falls back to
    ``str()`` for non-JSON objects such as pydantic models. Masking once at the
    model layer protects every such log site at once.

    The redaction set is the **union** of ``_redacted_repr_fields`` across the
    whole MRO, so a subclass can only ever *add* fields to redact - it can never
    accidentally drop protection inherited from a parent. Each subclass that
    introduces a new secret-bearing field must still list it here.

    Note: this only affects human / log rendering. Wire serialization uses
    ``.dict()`` / ``.json()``, which are untouched, so transport is unaffected.

    Caveat: this masks whole *fields* of the model. It does not protect a secret
    that is logged by reaching *into* the model (e.g. ``logger.info("{h}",
    h=config.headers)``); avoid logging credential-bearing attributes directly.
    """

    #: Field names whose values may carry secrets and must be masked in repr/str.
    _redacted_repr_fields: ClassVar[Set[str]] = set()

    def __repr_args__(self):
        # Union across the MRO so subclasses are additive (never lose a parent's
        # protection, even if they redeclare ``_redacted_repr_fields``).
        redacted: Set[str] = set()
        for klass in type(self).__mro__:
            redacted |= klass.__dict__.get("_redacted_repr_fields", set())
        return [
            (key, "<redacted>" if key in redacted else value)
            for key, value in super().__repr_args__()
        ]
