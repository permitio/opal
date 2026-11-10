from typing import ClassVar, Set

from pydantic import BaseModel, SerializerFunctionWrapHandler, model_serializer


class OmitNewFieldsWhenDefaultMixin(BaseModel):
    """Leaves fields added after the pydantic v1 wire contract out of dumps
    while they hold their default.

    Released clients are still pydantic v1, so a model they receive or
    send must serialize as it did then (see ``tests/wire_compat``). A new
    opt-in field listed in ``_omit_when_default_fields`` only appears on
    the wire once it is set; a reader that doesn't find it gets the
    default, so nothing is lost.

    The field sets are the union across the MRO, like
    ``RedactedReprMixin``.
    """

    _omit_when_default_fields: ClassVar[Set[str]] = set()

    @classmethod
    def _all_omit_when_default_fields(cls) -> Set[str]:
        fields: Set[str] = set()
        for klass in cls.__mro__:
            fields |= vars(klass).get("_omit_when_default_fields", set())
        return fields

    @model_serializer(mode="wrap")
    def _omit_new_fields_when_default(self, handler: SerializerFunctionWrapHandler):
        # No return annotation on purpose: with one, pydantic would take it as
        # the serialization schema and the models' JSON/OpenAPI schema would
        # turn into "any".
        data = handler(self)
        if not isinstance(data, dict):
            return data
        for name in self._all_omit_when_default_fields():
            default = (
                type(self).model_fields[name].get_default(call_default_factory=True)
            )
            if name in data and getattr(self, name) == default:
                del data[name]
        return data
