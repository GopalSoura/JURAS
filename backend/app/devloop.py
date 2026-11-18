"""Event loop factory for local Windows development.

uvicorn's default asyncio loop on Windows is ``ProactorEventLoop``. Under
browser connection churn its accept socket can fail with ``WinError 64``
("The specified network name is no longer available"). When that happens
uvicorn keeps running but stops accepting new connections, so the UI can no
longer reach the API until the process is restarted.

``SelectorEventLoop`` does not have that failure mode. Pass this factory with
``--loop app.devloop:selector_loop_factory`` (see ``run.py``).
"""

from __future__ import annotations

import asyncio


def selector_loop_factory() -> asyncio.AbstractEventLoop:
    return asyncio.SelectorEventLoop()
