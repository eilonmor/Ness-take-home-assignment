"""Keep secrets out of Playwright traces."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from playwright.sync_api import BrowserContext

from core.constants import TRACE_START_OPTIONS


@contextmanager
def tracing_paused(context: BrowserContext, tracing_active: bool) -> Iterator[None]:
    """Record nothing inside the block, e.g. while a password is typed.

    A trace stores every ``fill()`` value in plain text, and the network log
    keeps request bodies, so a sign-in form's POST carries the password too;
    failing traces are attached to the report. Pausing stops tracing without
    saving (everything recorded so far is dropped) and starts it again
    afterwards - also on error - so the fixture's ``tracing.stop()`` still works.

    A full stop, not ``stop_chunk()``: the network log outlives chunks, so a
    request sent between ``stop_chunk()`` and ``start_chunk()`` still ends up
    in the saved trace.
    """
    if not tracing_active:
        yield
        return
    context.tracing.stop()
    try:
        yield
    finally:
        context.tracing.start(**TRACE_START_OPTIONS)


@contextmanager
def tracing_group(context: BrowserContext, name: str, tracing_active: bool) -> Iterator[None]:
    """Group the actions inside the block under ``name`` in the trace viewer, e.g. "Cart page"."""
    if not tracing_active:
        yield
        return
    context.tracing.group(name)
    try:
        yield
    finally:
        context.tracing.group_end()
