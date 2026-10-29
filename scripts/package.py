"""Build separate Windows release artifacts; no app credentials/profile are used."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mirea_assistant_mcp import __version__


def main():
    go = shutil.which("go")
    if not go:
        sys.exit("Go 1.27.3 is required to build the native Windows adapters")
    if (
        subprocess.check_output([go, "env", "GOVERSION"], encoding="utf-8").strip()
        != "go1.27.3"
    ):
        sys.exit("Use the pinned Go 1.27.3 toolchain for reproducible release builds")
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/export_contract.py"), "--check"],
        cwd=ROOT,
        check=True,
    )
    destination = ROOT / "dist"
    destination.mkdir(exist_ok=True)
    environment = dict(
        os.environ,
        GOOS="windows",
        GOARCH="amd64",
        GOAMD64="v1",
        CGO_ENABLED="0",
        GOTOOLCHAIN="local",
    )
    flags = (
        "-X github.com/vladimir-mezh/mirea-lecture-assistant-mcp/native/internal/buildinfo.Version="
        + __version__
    )
    for entry, name in [("adapter", "MireaAssistantMcp"), ("launcher", "McpLauncher")]:
        subprocess.run(
            [
                go,
                "build",
                "-trimpath",
                "-ldflags",
                flags,
                "-o",
                str(destination / (name + ".exe")),
                "./cmd/" + entry,
            ],
            cwd=ROOT / "native",
            env=environment,
            check=True,
        )
    manifest = {
        "version": __version__,
        "app_protocol": 1,
        "sha256": {
            name: hashlib.sha256((ROOT / "dist" / name).read_bytes()).hexdigest()
            for name in ["MireaAssistantMcp.exe", "McpLauncher.exe"]
        },
    }
    archive = ROOT / "dist" / "MireaAssistantMcp-windows-x64.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for name in ["MireaAssistantMcp.exe", "McpLauncher.exe"]:
            bundle.write(ROOT / "dist" / name, name)
        bundle.writestr("manifest.json", json.dumps(manifest))
        bundle.write(ROOT / "README.md", "README.md")
        bundle.writestr("LICENSE", third_party_notices(go))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(".zip.sha256").write_text(
        f"{digest}  {archive.name}\n", encoding="ascii"
    )
    print(f"Release {__version__}: {archive.name}")


def third_party_notices(go):
    """The five-file archive remains compatible with existing app installers."""
    notices = [(ROOT / "LICENSE").read_text(encoding="utf-8")]
    goroot = subprocess.check_output([go, "env", "GOROOT"], encoding="utf-8").strip()
    notices.extend(
        [
            "\n--- Go standard library/runtime ---\n",
            (Path(goroot) / "LICENSE").read_text(encoding="utf-8"),
        ]
    )
    if (Path(goroot) / "PATENTS").exists():
        notices.append((Path(goroot) / "PATENTS").read_text(encoding="utf-8"))
    modules = subprocess.check_output(
        [go, "list", "-deps", "-json=Module", "./cmd/adapter", "./cmd/launcher"],
        cwd=ROOT / "native",
        encoding="utf-8",
    )
    decoder, offset, seen = json.JSONDecoder(), 0, set()
    while modules[offset:].strip():
        offset += len(modules[offset:]) - len(modules[offset:].lstrip())
        package, size = decoder.raw_decode(modules[offset:])
        offset += size
        module = package.get("Module")
        if not module or module.get("Main") or module["Path"] in seen:
            continue
        seen.add(module["Path"])
        folder = Path(module["Dir"])
        licenses = [
            folder / name
            for name in ("LICENSE", "LICENSE.txt", "LICENSE.md", "COPYING", "PATENTS")
            if (folder / name).is_file()
        ]
        if not licenses:
            raise RuntimeError("Missing license for " + module["Path"])
        notices.append("\n--- " + module["Path"] + " " + module["Version"] + " ---\n")
        notices.extend(path.read_text(encoding="utf-8") for path in licenses)
    return "\n".join(notices)


if __name__ == "__main__":
    main()
