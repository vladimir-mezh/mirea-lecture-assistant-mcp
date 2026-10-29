"""Keep the native Windows adapter's contract identical to the Python SDK server."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mirea_assistant_mcp.server import create_server


class Recorder:
    def __init__(self):
        self.calls = 0

    def call(self, method, params=None, **kwargs):
        self.calls += 1
        self.method, self.timeout = method, kwargs.get("timeout", 10)
        return {"fixture": True}


async def contract():
    recorder = Recorder()
    server = create_server(recorder)
    tools = []
    for tool in await server.list_tools():
        arguments = {}
        for name, schema in tool.inputSchema.get("properties", {}).items():
            arguments[name] = {
                "object": {},
                "boolean": False,
                "integer": 0,
                "string": "fixture",
            }[schema["type"]]
        before = recorder.calls
        await server.call_tool(tool.name, arguments)
        if recorder.calls != before + 1:
            raise RuntimeError(
                "Native contract requires an explicit handler for " + tool.name
            )
        tools.append(
            {
                "definition": tool.model_dump(mode="json", exclude_none=True),
                "method": recorder.method,
                "timeout": recorder.timeout,
            }
        )
    prompts = []
    for prompt in await server.list_prompts():
        result = await server.get_prompt(prompt.name, {})
        prompts.append(
            {
                "definition": prompt.model_dump(mode="json", exclude_none=True),
                "result": result.model_dump(mode="json", exclude_none=True),
            }
        )
    return {
        "instructions": server._mcp_server.instructions,
        "tools": tools,
        "prompts": prompts,
    }


if __name__ == "__main__":
    target = ROOT / "native" / "internal" / "adapter" / "contract.json"
    data = json.dumps(asyncio.run(contract()), ensure_ascii=False, indent=2) + "\n"
    if "--check" in sys.argv:
        if not target.exists() or target.read_text(encoding="utf-8") != data:
            sys.exit("Native MCP contract is stale: run scripts/export_contract.py")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(data, encoding="utf-8")
