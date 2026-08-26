# HiAgent MCP Server

This MCP server wraps HiAgent Platform OpenAPI capabilities as MCP tools. It currently provides knowledge-engine tools — listing knowledge bases (datasets) in a workspace, inspecting a dataset, and calling the HiAgent knowledge engine to retrieve knowledge chunks — and will keep adding more HiAgent OpenAPI capabilities over time.

## Features

- List knowledge bases (datasets) in a workspace
- Inspect a single dataset, including its default retrieval parameters
- Search knowledge in one or more datasets via the knowledge engine (`knowledge_search`)
- Report MCP server and OpenAPI configuration state

## Setup

### Prerequisites

- Python 3.11 or higher
- API credentials (AK/SK)

### Installation

Run directly from the repository with uvx (recommended):

```bash
uvx --from "git+https://github.com/volcengine/mcp-server#subdirectory=server/mcp_server_hiagent" mcp-server-hiagent
```

Or with uv, from the compatibility path:

```bash
cd mcp-server/server/mcp_server_hiagent
uv run mcp-server-hiagent
```

### Configuration

The server requires the following environment variables:

- `HIAGENT_TOP_HOST`: HiAgent Platform API (volc-top) gateway address, including scheme and port
- `HIAGENT_ACCESS_KEY_ID`: Your HiAgent access key id
- `HIAGENT_SECRET_ACCESS_KEY`: Your HiAgent secret access key

Optional environment variables:

- `HIAGENT_VERSION`: HiAgent OpenAPI compatibility version to use. Defaults to the latest registered version (currently `v3.1.0`). Can also be set per-run with the `--hiagent-version` CLI flag, which takes precedence. Selects a self-contained implementation under `versions/`; supported values: `v3.1.0`
- `HIAGENT_ACCOUNT_ID`: Main account id sent as the `X-Account-Id` query parameter, defaults to `1000000000`
- `HIAGENT_REGION`: Region used in AK/SK V4 signing (not a network address), defaults to `cn-north-1`
- `FASTMCP_CHECK_FOR_UPDATES`: Set to `off` to skip FastMCP's startup update check, which otherwise makes an outbound request and can fail startup in restricted networks
- `MCP_SERVER_HOST`: Bind host for the FastMCP server, streamable-http only (default: `127.0.0.1`)
- `MCP_SERVER_PORT`: Bind port for the FastMCP server, streamable-http only (default: `8000`)
- `STREAMABLE_HTTP_PATH`: Streamable HTTP endpoint path (default: `/mcp`)

## Usage

### Running the Server

The server can be run with either stdio transport (for MCP integration, e.g. the HiAgent STDIO plugin) or streamable-http transport:

```bash
python -m mcp_server_hiagent.main --transport stdio
```

Or:

```bash
python -m mcp_server_hiagent.main --transport streamable-http
```

Select a specific HiAgent OpenAPI version explicitly with `--hiagent-version`
(overrides the `HIAGENT_VERSION` environment variable; defaults to the latest
registered version):

```bash
python -m mcp_server_hiagent.main --hiagent-version v3.1.0
```

### Available Tools

#### health_check

Report the MCP server and OpenAPI configuration state.

```python
health_check()
```

#### list_datasets

List knowledge bases (datasets) in a workspace, so callers can obtain the `DatasetIDs` required by the knowledge engine.

```python
list_datasets(
    workspace_id="workspace_id",
    page_number=1,
    page_size=20,
)
```

Parameters:
- `workspace_id` (required): the workspace id to list datasets for.
- `page_number` (optional): page number (default: 1).
- `page_size` (optional): page size (default: 20).

#### get_dataset

Get information about a single dataset, including its default retrieval parameters.

```python
get_dataset(
    workspace_id="workspace_id",
    dataset_id="dataset_id",
)
```

Parameters:
- `workspace_id` (required): the workspace id the dataset belongs to.
- `dataset_id` (required): the id of the dataset to inspect.

#### call_knowledge_engine_tool

Call the HiAgent knowledge engine over one or more datasets. Only `tool_name="knowledge_search"` is supported at present.

```python
call_knowledge_engine_tool(
    workspace_id="workspace_id",
    dataset_ids=["dataset_id"],
    tool_name="knowledge_search",
    queries=["How to reset my password?"],
    top_k=3,
    score_threshold=0.2,
)
```

Parameters:
- `workspace_id` (required): the workspace id the datasets belong to.
- `dataset_ids` (required): list of dataset ids to search, at least one.
- `tool_name` (optional): sub-tool name, defaults to `knowledge_search`. Only `knowledge_search` is supported at present; other known sub-tools (`list_knowledge_chunks`, `grep_chunks`, `get_doc_info`, `wiki_search`, `wiki_read_page`, `wiki_read_source_doc`) are recognized but rejected.
- `queries` (optional): list of query strings (required for `knowledge_search`).
- `top_k` (optional): maximum number of results to return.
- `score_threshold` (optional): relevance score threshold (0~1).
- `rerank_id` (optional): rerank model id.
- `knowledge_run_mode` (optional): run mode, one of `quick` / `smart_search` / `wiki_search`.

## Best Practices & Test Prompts

Recommended usage pattern and, for each exposed tool, a natural-language prompt you can give an MCP-enabled agent to exercise it plus the expected result. These prompts double as a manual smoke test after wiring the server into a client.

**Recommended flow:** `health_check` (confirm config) → `list_datasets` (discover `DatasetIDs`) → optionally `get_dataset` (read default retrieval params) → `call_knowledge_engine_tool` (retrieve). `WorkspaceID` is not discoverable via this server — take it from the HiAgent console URL (`.../workspace/<id>/...`).

#### health_check

- **Best practice:** call it first, before any credentialed tool, to confirm the server sees your AK/SK and top host. It never calls the OpenAPI and never echoes secrets — only booleans.
- **Test prompt:** "Check whether the HiAgent MCP server is healthy and properly configured."
- **Expected result:** `status="ok"`, `auth="aksk"`, and `configured=true` with each `*_configured` flag true when env vars are set; no credential values are returned.

#### list_datasets

- **Best practice:** use it to discover the `DatasetIDs` required by `call_knowledge_engine_tool`; page with `page_number`/`page_size` (1–100) instead of requesting everything at once. `dataset` == knowledge base.
- **Test prompt:** "List the knowledge bases in workspace `<workspace_id>`."
- **Expected result:** a paged list of datasets, each with its id and name, that you can feed into the knowledge engine.

#### get_dataset

- **Best practice:** call it when you want a dataset's default retrieval parameters (e.g. `RetrievalTopK`, `RetrievalScoreThreshold`) so your `call_knowledge_engine_tool` arguments match how the base was configured.
- **Test prompt:** "Show the details and default retrieval settings of dataset `<dataset_id>` in workspace `<workspace_id>`."
- **Expected result:** the dataset's metadata including its default retrieval parameters.

#### call_knowledge_engine_tool

- **Best practice:** pass 1–5 short, self-contained `queries` (not a whole conversation); start with a small `top_k` (e.g. 3) and a modest `score_threshold` (e.g. 0.2), then tune. Only `tool_name="knowledge_search"` is supported in this version.
- **Test prompt:** "Search datasets `[<dataset_id>]` in workspace `<workspace_id>` for \"How do I reset my password?\" and return the top 3 chunks."
- **Expected result:** a `Result.KnowledgeSearch.Hits[]` payload where each hit carries `DatasetID` / `DocumentID` / `SegmentID` / `Content`; an unsupported `tool_name` is rejected with a clear error, and invalid arguments (empty `queries`, `score_threshold` outside 0–1) raise a validation error.

## MCP Integration

To add this server to your MCP configuration, add the following to your MCP settings file:

```json
{
  "mcpServers": {
    "hiagent": {
      "command": "uvx",
        "args": [
          "--from",
          "git+https://github.com/volcengine/mcp-server#subdirectory=server/mcp_server_hiagent",
          "mcp-server-hiagent"
        ],
      "env": {
        "HIAGENT_TOP_HOST": "http://your-top-host:30040",
        "HIAGENT_ACCESS_KEY_ID": "your-access-key",
        "HIAGENT_SECRET_ACCESS_KEY": "your-secret-key",
        "HIAGENT_ACCOUNT_ID": "1000000000",
        "HIAGENT_REGION": "cn-north-1",
        "FASTMCP_CHECK_FOR_UPDATES": "off"
      }
    }
  }
}
```

This uses the STDIO transport (the default), which the HiAgent MCP plugin launches locally and injects credentials into via its environment-variable table.

## Troubleshooting

### Common Issues

1. **Authentication Errors**
   - Verify your AK/SK credentials are correct
   - Check that you have the necessary permissions for the workspace and datasets

2. **Startup Failure in Restricted Networks**
   - Set `FASTMCP_CHECK_FOR_UPDATES=off` to skip FastMCP's outbound update check

3. **Empty or Denied Results**
   - Verify the `workspace_id` and `dataset_ids` are correct
   - Confirm `HIAGENT_TOP_HOST` points to the HiAgent Platform API (volc-top) gateway, not the web or Agent API address

### Logging

The server uses Python's logging module with INFO level by default. You can see detailed logs in the console when running the server.

## License

volcengine/mcp-server is licensed under the [MIT License](https://github.com/volcengine/mcp-server/blob/main/LICENSE).
