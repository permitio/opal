"""Stdlib records routed through ``InterceptHandler`` keep their caller's
identity.

``ModuleFilter`` and everything that reads ``record["name"]`` or
``record["function"]`` downstream depend on it.
"""

import asyncio
import logging
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, List, Optional

import pytest
from loguru import logger
from opal_common.logging_utils.filter import ModuleFilter
from opal_common.logging_utils.intercept import InterceptHandler

Record = Dict[str, Any]


@contextmanager
def _intercepted(logger_name: str) -> Iterator[logging.Logger]:
    """Routes one stdlib logger through the handler, as ``configure_logs``
    does, and restores it after."""
    stdlib = logging.getLogger(logger_name)
    handler = InterceptHandler()
    saved_level, saved_propagate = stdlib.level, stdlib.propagate
    stdlib.addHandler(handler)
    stdlib.setLevel(logging.DEBUG)
    stdlib.propagate = False
    try:
        yield stdlib
    finally:
        stdlib.removeHandler(handler)
        stdlib.setLevel(saved_level)
        stdlib.propagate = saved_propagate


@pytest.fixture
def stdlib_logger() -> Iterator[logging.Logger]:
    with _intercepted("intercept_handler_test") as stdlib:
        yield stdlib


@contextmanager
def _captured_records(
    module_filter: Optional[ModuleFilter] = None,
) -> Iterator[List[Record]]:
    records: List[Record] = []
    sink_id = logger.add(
        lambda message: records.append(message.record),
        level="DEBUG",
        diagnose=False,
        filter=module_filter.filter if module_filter else None,
    )
    try:
        yield records
    finally:
        logger.remove(sink_id)


def _log_exception(stdlib: logging.Logger) -> None:
    try:
        raise ValueError("probe")
    except ValueError:
        stdlib.exception("probe")


@pytest.mark.parametrize(
    "call_site",
    [
        lambda stdlib: stdlib.info("probe"),
        lambda stdlib: stdlib.log(logging.INFO, "probe"),
        lambda stdlib: logging.LoggerAdapter(stdlib, {}).info("probe"),
    ],
    ids=["info", "log", "adapter"],
)
def test_record_keeps_its_callers_module_and_function(
    stdlib_logger: logging.Logger, call_site: Callable[[logging.Logger], None]
):
    with _captured_records() as records:
        call_site(stdlib_logger)

    (record,) = records
    assert record["name"] == __name__
    assert record["function"] == "<lambda>"
    assert record["message"] == "probe"


def test_exception_record_keeps_its_caller_and_traceback(
    stdlib_logger: logging.Logger,
):
    with _captured_records() as records:
        _log_exception(stdlib_logger)

    (record,) = records
    assert record["name"] == __name__
    assert record["function"] == "_log_exception"
    assert record["exception"].type is ValueError


def test_library_record_keeps_the_librarys_module_name():
    """A real library call site, not one in this file: the case the module
    lists and log-index filters are written for."""
    with _intercepted("asyncio"), _captured_records() as records:
        asyncio.new_event_loop().close()

    selector_records = [r for r in records if "Using selector" in r["message"]]
    assert selector_records, records
    assert {r["name"] for r in selector_records} == {"asyncio.selector_events"}


@pytest.mark.parametrize(
    "module_filter, delivered",
    [
        pytest.param(ModuleFilter(exclude_list=[__name__]), False, id="excluded"),
        pytest.param(
            ModuleFilter(exclude_list=[__name__], include_list=[__name__]),
            True,
            id="included-over-excluded",
        ),
        pytest.param(ModuleFilter(exclude_list=["other"]), True, id="other-excluded"),
        pytest.param(
            ModuleFilter(exclude_list=["logging"]), True, id="logging-excluded"
        ),
    ],
)
def test_module_filter_acts_on_the_callers_name(
    stdlib_logger: logging.Logger, module_filter: ModuleFilter, delivered: bool
):
    with _captured_records(module_filter) as records:
        stdlib_logger.info("probe")

    assert bool(records) is delivered
