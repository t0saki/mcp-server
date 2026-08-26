from __future__ import annotations

from typing import Any

import pytest

from mcp_server_hiagent.versions.v3_1_0.tools.knowledge import (
    SUPPORTED_TOOL_NAMES,
    call_knowledge_engine_tool,
    knowledge_search,
)


class RecordingClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def call(self, **kwargs: Any) -> dict[str, object]:
        self.calls.append(kwargs)
        return {
            "ResponseMetadata": {"Action": kwargs["action"]},
            "Result": {"ToolName": "knowledge_search", "KnowledgeSearch": {"Hits": []}},
        }


def test_knowledge_search_builds_oneof_request() -> None:
    client = RecordingClient()

    knowledge_search(
        client,
        workspace_id="ws-1",
        dataset_ids=["ds-1", "ds-2"],
        queries=["hello"],
        top_k=3,
        score_threshold=0.2,
        rerank_id="rk-1",
    )

    assert client.calls[0] == {
        "action": "CallKnowledgeEngineTool",
        "version": "2023-08-01",
        "service": "app",
        "body": {
            "WorkspaceID": "ws-1",
            "DatasetIDs": ["ds-1", "ds-2"],
            "ToolName": "knowledge_search",
            "KnowledgeSearch": {
                "Queries": ["hello"],
                "TopK": 3,
                "ScoreThreshold": 0.2,
                "RerankID": "rk-1",
            },
        },
    }


def test_knowledge_search_omits_optional_fields() -> None:
    client = RecordingClient()

    knowledge_search(client, workspace_id="ws-1", dataset_ids=["ds-1"], queries=["q"])

    assert client.calls[0]["body"]["KnowledgeSearch"] == {"Queries": ["q"]}
    assert "KnowledgeRunMode" not in client.calls[0]["body"]


def test_knowledge_search_run_mode() -> None:
    client = RecordingClient()

    knowledge_search(
        client,
        workspace_id="ws-1",
        dataset_ids=["ds-1"],
        queries=["q"],
        knowledge_run_mode="smart_search",
    )

    assert client.calls[0]["body"]["KnowledgeRunMode"] == "smart_search"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"workspace_id": "", "dataset_ids": ["ds-1"], "queries": ["q"]},
        {"workspace_id": "ws-1", "dataset_ids": [], "queries": ["q"]},
        {"workspace_id": "ws-1", "dataset_ids": ["ds-1"], "queries": []},
    ],
)
def test_knowledge_search_required_fields(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        knowledge_search(RecordingClient(), **kwargs)


@pytest.mark.parametrize("bad", [-0.1, 1.1])
def test_knowledge_search_score_threshold_range(bad: float) -> None:
    with pytest.raises(ValueError):
        knowledge_search(
            RecordingClient(),
            workspace_id="ws-1",
            dataset_ids=["ds-1"],
            queries=["q"],
            score_threshold=bad,
        )


def test_knowledge_search_invalid_run_mode() -> None:
    with pytest.raises(ValueError):
        knowledge_search(
            RecordingClient(),
            workspace_id="ws-1",
            dataset_ids=["ds-1"],
            queries=["q"],
            knowledge_run_mode="nope",
        )


def test_dispatch_defaults_to_knowledge_search() -> None:
    client = RecordingClient()

    call_knowledge_engine_tool(
        client,
        workspace_id="ws-1",
        dataset_ids=["ds-1"],
        tool_name="knowledge_search",
        queries=["q"],
    )

    assert client.calls[0]["body"]["ToolName"] == "knowledge_search"


def test_dispatch_rejects_unknown_tool() -> None:
    with pytest.raises(ValueError):
        call_knowledge_engine_tool(
            RecordingClient(),
            workspace_id="ws-1",
            dataset_ids=["ds-1"],
            tool_name="does_not_exist",
            queries=["q"],
        )


def test_dispatch_rejects_known_but_unsupported_tool() -> None:
    # wiki_search is a known sub-tool but not yet supported.
    assert "wiki_search" not in SUPPORTED_TOOL_NAMES
    with pytest.raises(ValueError):
        call_knowledge_engine_tool(
            RecordingClient(),
            workspace_id="ws-1",
            dataset_ids=["ds-1"],
            tool_name="wiki_search",
        )
