"""Build separate Windows release artifacts; no app credentials/profile are used."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mirea_assistant_mcp import __version__

MARKER = "mirea-assistant-mcp.runtime"  # the name Lecture Assistant looks for


def main():
    # Lets Lecture Assistant tell this program's unpacked %TEMP%\_MEI… folder,
    # left behind when an AI client kills the process, from other programs'.
    marker = ROOT / "build" / MARKER
    marker.parent.mkdir(exist_ok=True)
    marker.write_text("MIREA Lecture Assistant MCP runtime\n", encoding="ascii")
    for entry, name in [("entry.py", "MireaAssistantMcp"), ("launcher.py", "McpLauncher")]:
        subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--onefile",
                        "--console", "--paths", "src", "--name", name,
                        "--add-data", f"{marker}{os.pathsep}.", entry],
                       cwd=ROOT, check=True)
    manifest = {"version": __version__, "app_protocol": 1, "sha256": {
        name: hashlib.sha256((ROOT / "dist" / name).read_bytes()).hexdigest()
        for name in ["MireaAssistantMcp.exe", "McpLauncher.exe"]
    }}
    archive = ROOT / "dist" / "MireaAssistantMcp-windows-x64.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for name in ["MireaAssistantMcp.exe", "McpLauncher.exe"]:
            bundle.write(ROOT / "dist" / name, name)
        bundle.writestr("manifest.json", json.dumps(manifest))
        bundle.write(ROOT / "README.md", "README.md")
        bundle.write(ROOT / "LICENSE", "LICENSE")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(".zip.sha256").write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    print(f"Release {__version__}: {archive.name}")


if __name__ == "__main__":
    main()
