from __future__ import annotations

import asyncio
from typing import Any

from mcp_server_hiagent.versions.v3_1_0.server import create_mcp_server


class RecordingClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def call(self, **kwargs: Any) -> dict[str, object]:
        self.calls.append(kwargs)
        return {"ResponseMetadata": {"Action": kwargs["action"]}, "Result": {}}


def test_server_registers_knowledge_engine_tools() -> None:
    server = create_mcp_server(client=RecordingClient())

    names = {tool.name for tool in asyncio.run(server.list_tools())}

    assert names == {
        "health_check",
        "call_knowledge_engine_tool",
        "list_datasets",
        "get_dataset",
    }


def test_injected_client_is_used_without_headers() -> None:
    # With an injected client, tools must work without any request headers
    # (the provider bypasses header parsing).
    client = RecordingClient()
    server = create_mcp_server(client=client)

    async def run() -> None:
        await server.call_tool("list_datasets", {"workspace_id": "ws-1"})

    asyncio.run(run())

    assert client.calls
    assert client.calls[0]["action"] == "ListDatasets"
    assert client.calls[0]["body"]["WorkspaceID"] == "ws-1"
