"""Local backend entrypoint.

Uses the selector event loop (``app.devloop``) so the Windows Proactor
accept-socket failure (WinError 64) cannot wedge the server. Run from the
``backend`` directory::

    .\\.venv\\Scripts\\python.exe run.py
"""

from __future__ import annotations

import uvicorn

HOST = "127.0.0.1"
PORT = 8000


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=HOST,
        port=PORT,
        loop="app.devloop:selector_loop_factory",
    )
