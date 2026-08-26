"""HiAgent Knowledge Engine OpenAPI tool.

``CallKnowledgeEngineTool`` is a dispatcher: ``ToolName`` selects a sub-tool and
the request carries a same-named parameter object (oneof). This module fully
implements the verified ``knowledge_search`` sub-tool; the remaining sub-tools
are recognized but not yet supported (their argument schemas are pending IDL
confirmation) and are rejected with a clear error instead of issuing an invalid
request.
"""

from __future__ import annotations

from collections.abc import Sequence

from fastmcp import FastMCP

from mcp_server_hiagent.versions.v3_1_0.tools._common import (
    OPENAPI_SERVICE,
    OPENAPI_VERSION,
    OpenAPIClient,
)


# Sub-tools known to exist on CallKnowledgeEngineTool (from the real IDL).
KNOWN_TOOL_NAMES = (
    "knowledge_search",
    "list_knowledge_chunks",
    "grep_chunks",
    "get_doc_info",
    "wiki_search",
    "wiki_read_page",
    "wiki_read_source_doc",
)

# Sub-tools whose argument object is fully implemented in this MCP.
SUPPORTED_TOOL_NAMES = ("knowledge_search",)

# Valid values for the optional KnowledgeRunMode field.
KNOWLEDGE_RUN_MODES = ("quick", "smart_search", "wiki_search")


def knowledge_search(
    client: OpenAPIClient,
    *,
    workspace_id: str,
    dataset_ids: Sequence[str],
    queries: Sequence[str],
    top_k: int | None = None,
    score_threshold: float | None = None,
    rerank_id: str | None = None,
    knowledge_run_mode: str | None = None,
) -> dict[str, object]:
    """Call CallKnowledgeEngineTool with ToolName=knowledge_search."""

    if not workspace_id:
        raise ValueError("workspace_id is required")
    if not dataset_ids:
        raise ValueError("dataset_ids must contain at least one dataset id")
    if not queries:
        raise ValueError("queries must contain at least one query")
    if score_threshold is not None and not 0 <= score_threshold <= 1:
        raise ValueError("score_threshold must be between 0 and 1")
    if knowledge_run_mode is not None and knowledge_run_mode not in KNOWLEDGE_RUN_MODES:
        raise ValueError(
            f"knowledge_run_mode must be one of {KNOWLEDGE_RUN_MODES}"
        )

    search: dict[str, object] = {"Queries": list(queries)}
    if top_k is not None:
        search["TopK"] = top_k
    if score_threshold is not None:
        search["ScoreThreshold"] = score_threshold
    if rerank_id:
        search["RerankID"] = rerank_id

    body: dict[str, object] = {
        "WorkspaceID": workspace_id,
        "DatasetIDs": list(dataset_ids),
        "ToolName": "knowledge_search",
        "KnowledgeSearch": search,
    }
    if knowledge_run_mode is not None:
        body["KnowledgeRunMode"] = knowledge_run_mode

    return client.call(
        action="CallKnowledgeEngineTool",
        version=OPENAPI_VERSION,
        service=OPENAPI_SERVICE,
        body=body,
    )


def call_knowledge_engine_tool(
    client: OpenAPIClient,
    *,
    workspace_id: str,
    dataset_ids: Sequence[str],
    tool_name: str,
    queries: Sequence[str] | None = None,
    top_k: int | None = None,
    score_threshold: float | None = None,
    rerank_id: str | None = None,
    knowledge_run_mode: str | None = None,
) -> dict[str, object]:
    """Dispatch a HiAgent knowledge engine tool call by ``tool_name``."""

    if not tool_name:
        raise ValueError("tool_name is required")
    if tool_name not in KNOWN_TOOL_NAMES:
        raise ValueError(
            f"unknown tool_name {tool_name!r}; known tools: {KNOWN_TOOL_NAMES}"
        )
    if tool_name not in SUPPORTED_TOOL_NAMES:
        raise ValueError(
            f"tool_name {tool_name!r} is not supported yet; "
            f"currently supported: {SUPPORTED_TOOL_NAMES}"
        )

    # Only knowledge_search is supported at present.
    return knowledge_search(
        client,
        workspace_id=workspace_id,
        dataset_ids=dataset_ids,
        queries=queries or [],
        top_k=top_k,
        score_threshold=score_threshold,
        rerank_id=rerank_id,
        knowledge_run_mode=knowledge_run_mode,
    )


def register_knowledge_tools(mcp: FastMCP, client: OpenAPIClient) -> None:
    """Register the knowledge engine tool on a FastMCP server."""

    @mcp.tool(name="call_knowledge_engine_tool")
    def call_knowledge_engine_tool_tool(
        workspace_id: str,
        dataset_ids: list[str],
        tool_name: str = "knowledge_search",
        queries: list[str] | None = None,
        top_k: int | None = None,
        score_threshold: float | None = None,
        rerank_id: str | None = None,
        knowledge_run_mode: str | None = None,
    ) -> dict[str, object]:
        """Call the HiAgent knowledge engine over one or more datasets.

        Only ``tool_name="knowledge_search"`` is supported at present; it
        retrieves knowledge chunks for the given ``queries``. Other known
        sub-tools (list_knowledge_chunks, grep_chunks, get_doc_info,
        wiki_search, wiki_read_page, wiki_read_source_doc) are not yet
        supported and will be rejected.
        """

        return call_knowledge_engine_tool(
            client,
            workspace_id=workspace_id,
            dataset_ids=dataset_ids,
            tool_name=tool_name,
            queries=queries,
            top_k=top_k,
            score_threshold=score_threshold,
            rerank_id=rerank_id,
            knowledge_run_mode=knowledge_run_mode,
        )
