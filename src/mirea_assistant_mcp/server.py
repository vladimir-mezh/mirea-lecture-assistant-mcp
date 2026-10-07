from __future__ import annotations

import argparse
import os
from contextlib import asynccontextmanager
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from . import __version__
from .backend import Backend


def create_server(backend: Backend):
    @asynccontextmanager
    async def lifespan(_server):
        backend.start()
        try:
            yield {}
        finally:
            backend.stop()

    mcp = FastMCP("MIREA Lecture Assistant MCP", lifespan=lifespan,
                  instructions="Configure and diagnose the local Lecture Assistant only at the "
                  "user's request. Ask before changing settings or subject rules. Credentials "
                  "must be entered by the user in the app; this server has no QR, attendance, "
                  "chat, shell or credential tools. Never infer a successful scan from a process.")

    @mcp.tool()
    def get_status() -> dict:
        """Read application version and scanner state without logging in or submitting anything."""
        return backend.call("status", tool=True)

    @mcp.tool()
    def get_settings() -> dict:
        """Read non-secret settings and their validation schema. No credentials or email codes."""
        return backend.call("get_settings", tool=True)

    @mcp.tool()
    def get_schedule() -> dict:
        """Read cached schedule, without refreshing websites or opening lectures."""
        return backend.call("get_schedule", tool=True)

    @mcp.tool()
    def get_subject_rules() -> dict:
        """Read AUTO/ASK/IGNORE rules for subjects in the cached schedule."""
        return backend.call("get_subject_rules", tool=True)

    @mcp.tool()
    def update_settings(settings: dict) -> dict:
        """Apply only settings listed by get_settings. Requires explicit app-side write permission
        and no unsaved UI edits. Ask the user first. Changes take effect in the running app.
        """
        return backend.call("update_settings", {"settings": settings}, tool=True)

    @mcp.tool()
    def set_subject_rule(subject: str, mode: str) -> dict:
        """Set AUTO/ASK/IGNORE for an existing subject, only at user's request and with app-side
        permission. AUTO affects future lecture opening; never change attendance rules silently.
        """
        return backend.call("set_subject_rule", {"subject": subject, "mode": mode}, tool=True)

    return mcp


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", type=Path,
                        default=Path(os.environ.get("LOCALAPPDATA", ".")) / "MireaLectureAssistant")
    parser.add_argument("--client-name", default="MCP-клиент")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args()
    server = create_server(Backend(args.profile, args.client_name))
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
