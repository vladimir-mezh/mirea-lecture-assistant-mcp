from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from mirea_assistant_mcp.backend import Backend
from mirea_assistant_mcp.server import create_server


def test_backend_unavailable_does_not_expose_profile_path_or_secrets(tmp_path):
    backend = Backend(tmp_path / "sensitive-profile")
    with pytest.raises(RuntimeError) as exc:
        backend.call("get_settings")
    assert "sensitive-profile" not in str(exc.value)


def test_tools_only_expose_the_bounded_configuration_api():
    class Fake:
        def call(self, method, params=None, **kwargs):
            return {"method": method}
    server = create_server(Fake())
    names = asyncio.run(server.list_tools())
    assert {tool.name for tool in names} == {
        "get_status", "get_settings", "get_schedule", "get_subject_rules",
        "update_settings", "set_subject_rule",
    }


@pytest.mark.parametrize("packaged", [False, True])
def test_real_stdio_handshake_lists_tools_and_handles_app_absence(tmp_path, packaged):
    root = Path(__file__).resolve().parents[1]
    executable = root / "dist" / "MireaAssistantMcp.exe"
    if packaged and not executable.exists():
        pytest.skip("Executable not built yet")
    async def check():
        params = StdioServerParameters(command=str(executable) if packaged else sys.executable,
            args=[] if packaged else [str(root / "entry.py")])
        params.args.extend(["--profile", str(tmp_path)])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                initialized = await session.initialize()
                assert "MIREA" in initialized.serverInfo.name
                tools = await session.list_tools()
                assert len(tools.tools) == 6
                result = await session.call_tool("get_status", {})
                assert result.isError
                assert "unavailable" in result.content[0].text
                assert str(tmp_path) not in result.content[0].text
    asyncio.run(check())


def test_launcher_rejects_path_traversal(tmp_path):
    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location("launcher", Path(__file__).resolve().parents[1] / "launcher.py")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    (tmp_path / "current.json").write_text(json.dumps({"version": "../outside", "app_protocol": 1}))
    with pytest.raises(ValueError):
        module.selected_executable(tmp_path)
