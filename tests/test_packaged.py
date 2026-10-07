"""Real SDK/stdio + the app's HTTP API on a synthetic temporary profile."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# A checkout of Lecture Assistant; CI clones it, locally set the variable.
APP = Path(os.environ.get("MIREA_APP_SOURCE", "lecture-assistant"))
EXE = Path(__file__).resolve().parents[1] / "dist" / "MireaAssistantMcp.exe"


@pytest.mark.skipif(not EXE.exists() or not (APP / "src" / "mirea_lecture_assistant" / "mcp_install.py").exists(),
                    reason="Local packaged compatibility check requires both projects")
@pytest.mark.parametrize("use_launcher", [False, True])
def test_packaged_mcp_works_against_app_v1_api_without_real_profile(tmp_path, use_launcher):
    spec = importlib.util.spec_from_file_location("isolated_app_api",
        APP / "src" / "mirea_lecture_assistant" / "mcp_access.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    settings = {"mute_lecture": True}
    allowed = [False]
    def dispatch(job):
        if job.method == "status":
            job.result = {"result": {"protocol": 1, "fixture": True}}
        elif job.method == "get_settings":
            job.result = {"result": dict(settings)}
        elif job.method == "update_settings" and allowed[0]:
            values = module.validate_settings(job.params["settings"])
            settings.update(values)
            job.result = {"result": {"updated": sorted(values)}}
        else:
            job.result = {"error": "Changes are disabled"}
        job.done.set()
    access = module.McpAccess(tmp_path, dispatch)
    access.start()
    command = EXE
    if use_launcher:
        sys.path.insert(0, str(APP / "src"))
        from mirea_lecture_assistant.mcp_install import install_archive

        archive = EXE.with_name("MireaAssistantMcp-windows-x64.zip")
        from mirea_assistant_mcp import __version__

        install_archive(tmp_path / "mcp", archive.read_bytes(), __version__)
        command = tmp_path / "mcp" / "McpLauncher.exe"
    async def check():
        params = StdioServerParameters(command=str(command), args=["--profile", str(tmp_path)])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                assert len((await session.list_tools()).tools) == 6
                status = await session.call_tool("get_status", {})
                assert not status.isError
                assert json.loads(status.content[0].text)["fixture"]
                assert access.connected_clients()[0]["state"] == "connected"
                denied = await session.call_tool("update_settings", {"settings": {"mute_lecture": False}})
                assert denied.isError and settings["mute_lecture"]
                allowed[0] = True
                applied = await session.call_tool("update_settings", {"settings": {"mute_lecture": False}})
                assert not applied.isError and not settings["mute_lecture"]
    try:
        asyncio.run(check())
    finally:
        access.stop()


def _release(version: str, launcher: bytes) -> bytes:
    """The real adapter, packed as another release with its own launcher bytes."""
    import hashlib
    import io
    import zipfile

    files = {"MireaAssistantMcp.exe": EXE.read_bytes(), "McpLauncher.exe": launcher}
    manifest = {"version": version, "app_protocol": 1,
                "sha256": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as bundle:
        for name, data in files.items():
            bundle.writestr(name, data)
        bundle.writestr("manifest.json", json.dumps(manifest))
        bundle.writestr("README.md", "Packaged update check")
        bundle.writestr("LICENSE", "MIT")
    return out.getvalue()


@pytest.mark.skipif(not EXE.exists() or not (APP / "src" / "mirea_lecture_assistant" / "mcp_install.py").exists(),
                    reason="Local packaged compatibility check requires both projects")
def test_update_while_a_client_runs_the_old_version_then_cleanup(tmp_path):
    """Windows keeps running programs locked: the old version and launcher go later."""
    import time

    sys.path.insert(0, str(APP / "src"))
    from mirea_lecture_assistant.mcp_install import clean_leftovers, install_archive, installed

    launcher = EXE.with_name("McpLauncher.exe").read_bytes()
    root = tmp_path / "mcp"
    install_archive(root, _release("1.0.0", launcher), "1.0.0")
    # A different launcher build; it is only placed, never started.
    newer_launcher = launcher[:-64] + b"\0" * 64

    async def update_while_connected():
        params = StdioServerParameters(command=str(root / "McpLauncher.exe"),
                                       args=["--profile", str(tmp_path)])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                install_archive(root, _release("1.0.1", newer_launcher), "1.0.1")
                assert installed(root)["version"] == "1.0.1"
                assert (root / "McpLauncher.exe").read_bytes() == newer_launcher
                # Both still run: neither may be gone yet.
                assert (root / "versions" / "1.0.0" / "MireaAssistantMcp.exe").exists()
                assert list(root.glob("McpLauncher.exe.*.old"))
                assert not clean_leftovers(root)
                assert len((await session.list_tools()).tools) == 6

    asyncio.run(update_while_connected())
    deadline = time.monotonic() + 30
    while not clean_leftovers(root) and time.monotonic() < deadline:
        time.sleep(0.5)
    assert clean_leftovers(root)
    assert sorted(p.name for p in (root / "versions").iterdir()) == ["1.0.1"]
    assert not list(root.glob("McpLauncher.exe.*"))


@pytest.mark.skipif(sys.platform != "win32" or not EXE.exists()
                    or not (APP / "src" / "mirea_lecture_assistant" / "leftovers.py").exists(),
                    reason="Real onefile unpacking needs Windows, the build and the app")
def test_folder_left_by_a_killed_adapter_is_removed_by_the_app(tmp_path):
    """An AI client kills the process: its unpacked folder stays until the app removes it."""
    import subprocess
    import time

    sys.path.insert(0, str(APP / "src"))
    from mirea_lecture_assistant import leftovers

    temp = tmp_path / "temp"
    temp.mkdir()
    environment = dict(os.environ, TMP=str(temp), TEMP=str(temp))
    process = subprocess.Popen([str(EXE), "--profile", str(tmp_path)], env=environment,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL)
    later = lambda: time.time() + 3600  # noqa: E731 - past the "still unpacking" guard
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline and not list(temp.glob(f"_MEI*/{leftovers.MCP_MARKER}")):
            time.sleep(0.2)
        assert list(temp.glob(f"_MEI*/{leftovers.MCP_MARKER}")), "marker not bundled"
        time.sleep(3)  # Python is loaded by now
        assert leftovers.clean_runtime_folders(temp, now=later()) == 0
        assert list(temp.glob(f"_MEI*/{leftovers.MCP_MARKER}"))
    finally:
        process.kill()
        process.stdin.close()
        process.wait(timeout=30)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline and list(temp.glob("_MEI*")):
        leftovers.clean_runtime_folders(temp, now=later())
        time.sleep(0.5)
    assert not list(temp.glob("_MEI*"))
