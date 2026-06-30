from typing import ClassVar, Set

from opal_common.http_utils import redact_url


class RedactedReprMixin:
    """Mixin for pydantic (v1) models that may carry credentials.

    Overrides ``repr()`` / ``str()`` so that sensitive fields are masked instead
    of rendering their real value. Two flavours of masking are supported:

    - ``_redacted_repr_fields`` - the value is wholly replaced with
      ``<redacted>`` (use for opaque secret carriers such as ``config``/``data``).
    - ``_redacted_url_fields`` - the value is passed through ``redact_url`` so
      embedded credentials are stripped while the host/path stay visible for
      debugging (use for URL fields, which can embed ``user:token@`` or
      ``?token=`` credentials but are otherwise useful to see).

    Both apply on this class or *any* of its base classes.

    This is the central defense against credential leaks in logs: OPAL logs via
    loguru, and most leaks come from interpolating these models into log
    messages (e.g. ``logger.info("... {entry}", entry=entry)``) or from loguru's
    ``serialize=True`` sink, which dumps the record as JSON and falls back to
    ``str()`` for non-JSON objects such as pydantic models. Masking once at the
    model layer protects every such log site at once.

    Each redaction set is the **union** of its declarations across the whole
    MRO, so a subclass can only ever *add* fields to redact - it can never
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
    #: URL field names whose embedded credentials must be stripped via redact_url.
    _redacted_url_fields: ClassVar[Set[str]] = set()

    @classmethod
    def _union_over_mro(cls, attr: str) -> Set[str]:
        # Union across the MRO so subclasses are additive (never lose a parent's
        # protection, even if they redeclare the set).
        result: Set[str] = set()
        for klass in cls.__mro__:
            result |= klass.__dict__.get(attr, set())
        return result

    def __repr_args__(self):
        redacted = type(self)._union_over_mro("_redacted_repr_fields")
        url_redacted = type(self)._union_over_mro("_redacted_url_fields")
        args = []
        for key, value in super().__repr_args__():
            if key in redacted:
                value = "<redacted>"
            elif key in url_redacted and isinstance(value, str):
                value = redact_url(value)
            args.append((key, value))
        return args
