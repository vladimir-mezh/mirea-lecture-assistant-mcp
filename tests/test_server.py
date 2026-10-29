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
        "get_status",
        "get_settings",
        "get_schedule",
        "get_subject_rules",
        "update_settings",
        "set_subject_rule",
        "check_health",
        "wait_and_check",
        "repair",
        "get_recent_problems",
        "get_attendance_history",
        "get_vpn_help",
        "report_fix",
    }
    prompts = asyncio.run(server.list_prompts())
    assert {prompt.name for prompt in prompts} == {"duty_check", "setup_lecture_watch"}


@pytest.mark.parametrize("packaged", [False, True])
def test_real_stdio_handshake_lists_tools_and_handles_app_absence(tmp_path, packaged):
    root = Path(__file__).resolve().parents[1]
    executable = root / "dist" / "MireaAssistantMcp.exe"
    if packaged and not executable.exists():
        pytest.skip("Executable not built yet")

    async def check():
        params = StdioServerParameters(
            command=str(executable) if packaged else sys.executable,
            args=[] if packaged else [str(root / "entry.py")],
        )
        params.args.extend(["--profile", str(tmp_path)])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                initialized = await session.initialize()
                assert "MIREA" in initialized.serverInfo.name
                tools = await session.list_tools()
                assert len(tools.tools) == 13
                result = await session.call_tool("get_status", {})
                assert result.isError
                assert "unavailable" in result.content[0].text
                assert str(tmp_path) not in result.content[0].text

    asyncio.run(check())


def test_launcher_rejects_path_traversal(tmp_path):
    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location(
        "launcher", Path(__file__).resolve().parents[1] / "launcher.py"
    )
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    (tmp_path / "current.json").write_text(
        json.dumps({"version": "../outside", "app_protocol": 1})
    )
    with pytest.raises(ValueError):
        module.selected_executable(tmp_path)


def test_launcher_gives_the_adapter_its_own_pyinstaller_folder(tmp_path, monkeypatch):
    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location(
        "launcher", Path(__file__).resolve().parents[1] / "launcher.py"
    )
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path / "mcp"
    (root / "versions" / "0.1.0").mkdir(parents=True)
    (root / "current.json").write_text(
        json.dumps({"version": "0.1.0", "app_protocol": 1})
    )
    calls = []
    monkeypatch.setattr(
        module.subprocess,
        "call",
        lambda args, **kwargs: calls.append((args, kwargs)) or 0,
    )
    monkeypatch.setattr(sys, "argv", ["McpLauncher.exe", "--profile", str(tmp_path)])
    assert module.main() == 0
    args, kwargs = calls[0]
    assert args[0] == str(root / "versions" / "0.1.0" / "MireaAssistantMcp.exe")
    assert kwargs["env"]["PYINSTALLER_RESET_ENVIRONMENT"] == "1"


def test_an_older_app_gets_a_plain_ask_to_update(tmp_path, monkeypatch):
    import io

    import mirea_assistant_mcp.backend as backend_module

    (tmp_path / "mcp-connection.json").write_text(
        json.dumps({"protocol": 1, "port": 5000, "token": "t" * 40}), encoding="utf-8"
    )

    class Reply(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    class Opener:
        def open(self, *_args, **_kwargs):
            return Reply(json.dumps({"error": "Unsupported MCP method"}).encode())

    monkeypatch.setattr(
        backend_module.urllib.request, "build_opener", lambda *_: Opener()
    )
    with pytest.raises(RuntimeError) as exc:
        Backend(tmp_path).call("check_health", tool=True)
    assert "update" in str(exc.value)


def test_waiting_check_gives_the_app_time_to_answer(monkeypatch):
    calls = []

    class Fake:
        def call(self, method, params=None, **kwargs):
            calls.append((method, params, kwargs))
            return {}

    server = create_server(Fake())
    asyncio.run(server.call_tool("wait_and_check", {"seconds": 90}))
    method, params, kwargs = calls[-1]
    assert (method, params) == ("wait_and_check", {"seconds": 90})
    assert kwargs["timeout"] > 90


@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[1] / "dist/MireaAssistantMcp.exe").exists(),
    reason="Native executable has not been built",
)
def test_native_and_python_servers_expose_the_same_contract(tmp_path):
    class Fake:
        def call(self, *_a, **_kw):
            return {}

    reference = create_server(Fake())

    async def check():
        executable = Path(__file__).resolve().parents[1] / "dist/MireaAssistantMcp.exe"
        params = StdioServerParameters(
            command=str(executable), args=["--profile", str(tmp_path)]
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                initialized = await session.initialize()
                expected = {
                    t.name: t.model_dump(mode="json", exclude_none=True)
                    for t in await reference.list_tools()
                }
                actual = {
                    t.name: t.model_dump(mode="json", exclude_none=True)
                    for t in (await session.list_tools()).tools
                }
                assert actual == expected
                expected_prompts = {
                    p.name: p.model_dump(mode="json", exclude_none=True)
                    for p in await reference.list_prompts()
                }
                actual_prompts = {
                    p.name: p.model_dump(mode="json", exclude_none=True)
                    for p in (await session.list_prompts()).prompts
                }
                # MCP treats an omitted optional argument list and [] identically.
                for prompts in (actual_prompts, expected_prompts):
                    for prompt in prompts.values():
                        prompt.setdefault("arguments", [])
                assert actual_prompts == expected_prompts
                assert initialized.instructions == reference._mcp_server.instructions
                for name in expected_prompts:
                    actual_prompt = await session.get_prompt(name, {})
                    expected_prompt = await reference.get_prompt(name, {})
                    assert actual_prompt.model_dump(
                        mode="json", exclude_none=True
                    ) == expected_prompt.model_dump(mode="json", exclude_none=True)

    asyncio.run(check())
