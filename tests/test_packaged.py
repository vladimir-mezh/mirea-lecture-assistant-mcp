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

APP = Path(os.environ.get("MIREA_APP_SOURCE", r"D:\MIREA Lecture Assistant"))
EXE = Path(__file__).resolve().parents[1] / "dist" / "MireaAssistantMcp.exe"


@pytest.mark.skipif(not EXE.exists() or not (APP / "src").exists(),
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
        install_archive(tmp_path / "mcp", archive.read_bytes(), "0.1.0")
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
