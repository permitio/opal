"""Corpus payloads that must be built as model INSTANCES, not dicts.

Most cases in ``payloads.py`` are plain dicts fed to ``parse_obj`` /
``model_validate``, which is the right shape for a wire payload: it is what
arrives over HTTP. But a dict can only ever validate into the field's DECLARED
type, so a whole class of v1/v2 difference is invisible to it - the one where
code assigns a SUBCLASS instance to a parent-typed field.

That gap is not hypothetical. ``DataUpdateReport.reports[].entry`` is declared
``DataSourceEntry``; the client assigns the ``DataSourceEntryWithPollingInterval``
it was given. pydantic v1 serialized the runtime instance and kept
``periodic_update_interval``; v2 serializes with the declared type's serializer
and drops it, with no warning. The dict-built corpus case could not see it
because the dict validated to a plain ``DataSourceEntry`` and the subclass path
was never taken.

Builders here construct the real objects instead. They import opal models (both
trees have them) but never pydantic directly, so the same file runs under v1 and
v2 - the builder returns an instance, and the caller serializes it with whichever
API that version provides.
"""

from typing import Any, Callable, Dict


def data_update_report_with_polling_entry() -> Any:
    """A callback report whose entry is a SUBCLASS instance.

    Mirrors what ``CallbacksReporter`` actually POSTs: the entry comes from
    ``GET /data/config``, which serves ``DataSourceEntryWithPollingInterval``,
    and is assigned to a parent-typed field on the way out.
    """
    from opal_common.schemas.data import (
        DataEntryReport,
        DataSourceEntryWithPollingInterval,
        DataUpdateReport,
    )

    entry = DataSourceEntryWithPollingInterval(
        url="https://backend.example.com/v1/policy/data",
        topics=["policy_data"],
        dst_path="/acl",
        save_method="PUT",
        periodic_update_interval=30.0,
    )
    return DataUpdateReport(
        update_id="dddddddd-1111-1111-1111-111111111111",
        reports=[DataEntryReport(entry=entry, fetched=True, saved=True, hash="a" * 8)],
        policy_hash="b" * 40,
    )


def data_update_with_polling_entry() -> Any:
    """A publish payload whose entry is a SUBCLASS instance.

    The server-side sibling of the above: ``DataUpdate.entries`` is declared
    ``List[DataSourceEntry]`` and the polling publisher hands it
    ``DataSourceEntryWithPollingInterval``.
    """
    from opal_common.schemas.data import DataSourceEntryWithPollingInterval, DataUpdate

    entry = DataSourceEntryWithPollingInterval(
        url="https://backend.example.com/v1/policy/data",
        topics=["policy_data"],
        dst_path="/acl",
        save_method="PUT",
        periodic_update_interval=45.0,
    )
    return DataUpdate(
        id="eeeeeeee-1111-1111-1111-111111111111",
        entries=[entry],
        reason="corpus: subclass instance in a parent-typed field",
    )


BUILDERS: Dict[str, Callable[[], Any]] = {
    "data_update_report_with_polling_entry": data_update_report_with_polling_entry,
    "data_update_with_polling_entry": data_update_with_polling_entry,
}
