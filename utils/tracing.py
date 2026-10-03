"""Keep secrets out of Playwright traces."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from playwright.sync_api import BrowserContext


@contextmanager
def tracing_paused(context: BrowserContext, tracing_active: bool) -> Iterator[None]:
    """Record nothing inside the block, e.g. while a password is typed.

    A trace stores every ``fill()`` value in plain text, and failing traces
    are attached to the report. Pausing ends the current trace chunk without
    saving it (everything recorded so far is dropped) and starts a new chunk
    afterwards - also on error - so the fixture's ``tracing.stop()`` still works.
    """
    if not tracing_active:
        yield
        return
    context.tracing.stop_chunk()
    try:
        yield
    finally:
        context.tracing.start_chunk()


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
