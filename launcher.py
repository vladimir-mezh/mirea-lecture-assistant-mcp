"""Stable stdio launcher: new client connections use the independently updated MCP."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def selected_executable(root: Path):
    manifest = json.loads((root / "current.json").read_text(encoding="utf-8"))
    version = manifest.get("version", "")
    if not re.fullmatch(r"\d+\.\d+\.\d+", version) or manifest.get("app_protocol") != 1:
        raise ValueError("Invalid MCP installation manifest")
    return root / "versions" / version / "MireaAssistantMcp.exe"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--client-name", default="MCP-клиент")
    args = parser.parse_args()
    try:
        executable = selected_executable(args.profile / "mcp")
        # The launcher is itself a PyInstaller onefile program: the adapter must
        # unpack into its own folder, not take this process's for its own.
        environment = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")
        # Inherit stdio exactly. Never print banners/status into the MCP transport.
        return subprocess.call([str(executable), "--profile", str(args.profile),
                                "--client-name", args.client_name], env=environment)
    except (OSError, ValueError):
        print("MCP is not installed; reinstall from Lecture Assistant's MCP tab.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
