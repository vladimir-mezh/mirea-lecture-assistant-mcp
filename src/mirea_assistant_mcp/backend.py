"""Read the app's local pairing file, never its database/credential store."""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from . import __version__

UPDATE_APP = ("This needs a newer Lecture Assistant: ask the user to update the app "
              "(Настройки → Обновления).")


class Backend:
    def __init__(self, profile: Path, name="MCP-клиент"):
        self.profile = profile
        self.client = {"id": uuid.uuid4().hex, "name": name[:80],
                       "version": __version__, "state": "waiting"}
        self.closed = threading.Event()
        self.thread = None

    def call(self, method: str, params=None, *, tool=False, timeout=10):
        if tool:
            self.client["state"] = "connected"
        try:
            # Re-read after app restart: ephemeral port/key must not be cached.
            config = json.loads((self.profile / "mcp-connection.json").read_text(encoding="utf-8"))
            port, token = config.get("port"), config.get("token")
            if config.get("protocol") != 1 or type(port) is not int or not 1 <= port <= 65535:
                raise ValueError()
            if not isinstance(token, str) or len(token) < 32:
                raise ValueError()
            request = urllib.request.Request(
                f"http://127.0.0.1:{port}/rpc",
                data=json.dumps({"protocol": 1, "client": self.client,
                                 "method": method, "params": params or {}}).encode("utf-8"),
                headers={"Content-Type": "application/json", "Authorization": "Bearer " + token},
            )
            # Never route credentials through an environment HTTP proxy.
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(request, timeout=timeout) as response:
                data = response.read(262145)
                if len(data) > 262144:
                    raise ValueError()
                result = json.loads(data)
            if "error" in result:
                if result["error"] == "Unsupported MCP method":
                    raise RuntimeError(UPDATE_APP)
                raise RuntimeError(str(result["error"]))
            return result.get("result", result)
        except RuntimeError:
            raise
        except (OSError, ValueError, TypeError, KeyError, urllib.error.URLError):
            # No exception text, paths, headers or keys in MCP errors/stdout.
            raise RuntimeError("Lecture Assistant unavailable. Open the app, install MCP "
                               "and enable local access in its MCP tab.") from None

    def start(self):
        def heartbeat():
            while not self.closed.is_set():
                try:
                    self.call("heartbeat")
                except RuntimeError:
                    pass
                self.closed.wait(10)
        self.thread = threading.Thread(target=heartbeat, daemon=True)
        self.thread.start()

    def stop(self):
        self.closed.set()
        try:
            self.call("disconnect")
        except RuntimeError:
            pass
