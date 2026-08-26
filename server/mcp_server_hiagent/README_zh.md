# HiAgent MCP Server

## 产品描述

HiAgent MCP Server 是一个模型上下文协议（Model Context Protocol）服务器，将 HiAgent 平台 OpenAPI 的能力封装为标准 MCP 工具，供 MCP 客户端（如 Claude Desktop、Cursor，以及 HiAgent 平台的 MCP 插件）使用。本 Server 持续接入 HiAgent 平台的各类 OpenAPI 能力，当前已提供知识引擎相关工具：列出指定 workspace 下的知识库、查看知识库详情，并调用知识引擎在指定知识库中检索知识片段；后续将陆续扩展更多能力。

## 分类

其他

## 功能

- 列出指定 workspace 下的知识库列表
- 查看单个知识库的详细信息（含默认检索参数）
- 调用知识引擎在指定知识库中检索知识片段（`knowledge_search`）
- 查看 MCP Server 与 OpenAPI 的配置状态

## 使用指南

### 前置准备

- Python 3.11+
- UV
- API credentials (AK/SK)

### 安装

克隆仓库：

```bash
git clone git@github.com:volcengine/mcp-server.git
```

### 使用方法

启动服务器：

#### UV

```bash
cd mcp-server/server/mcp_server_hiagent
uv run mcp-server-hiagent

# 使用 streamable-http 模式启动（默认为 stdio）
uv run mcp-server-hiagent -t streamable-http

# 显式指定 HiAgent OpenAPI 版本（覆盖 HIAGENT_VERSION 环境变量；不填默认用最新）
uv run mcp-server-hiagent --hiagent-version v3.1.0
```

使用客户端与服务器交互：

```
Trae | Cursor | Claude Desktop | Cline | HiAgent MCP 插件 | ...
```

## 配置

### 环境变量

以下环境变量可用于配置 MCP 服务器：

| 环境变量 | 描述 | 默认值 |
|---|---|---|
| `HIAGENT_TOP_HOST` | HiAgent Platform API（volc-top）网关地址，含 scheme 与端口 | - |
| `HIAGENT_ACCESS_KEY_ID` | HiAgent 账号 AccessKey ID | - |
| `HIAGENT_SECRET_ACCESS_KEY` | HiAgent 账号 SecretAccessKey | - |
| `HIAGENT_ACCOUNT_ID` | 作为 `X-Account-Id` 查询参数发送的主账号 ID | `1000000000` |
| `HIAGENT_VERSION` | 使用的 HiAgent OpenAPI 兼容版本，对应 `versions/` 下的自包含实现；不填默认使用最新已注册版本（当前为 `v3.1.0`）。也可用 `--hiagent-version` 命令行参数按次指定，且优先级更高；当前支持 `v3.1.0` | 最新（`v3.1.0`） |
| `HIAGENT_REGION` | 用于 AK/SK V4 签名的 Region（非网络地址） | `cn-north-1` |
| `FASTMCP_CHECK_FOR_UPDATES` | 设为 `off`，否则 FastMCP 启动时的联网版本检查在受限网络下可能导致启动失败 | - |
| `MCP_SERVER_HOST` | MCP server 绑定 host（streamable-http） | `127.0.0.1` |
| `MCP_SERVER_PORT` | MCP server 监听端口（streamable-http） | `8000` |

## 可用工具

HiAgent MCP Server 提供以下功能：

- `health_check`: 返回 MCP server 与 OpenAPI 的配置状态
- `list_datasets`: 列出指定 workspace 下的知识库列表
- `get_dataset`: 获取单个知识库的详细信息
- `call_knowledge_engine_tool`: 调用知识引擎在指定知识库中检索

#### health_check

```python
health_check()
```

#### list_datasets

```python
list_datasets(
    workspace_id="workspace_id",
    page_number=1,
    page_size=20,
)
```

Parameters:
- `workspace_id` (必须): 要列出知识库的 workspace ID
- `page_number` (可选): 页码（默认值：1）
- `page_size` (可选): 每页数量（默认值：20）

#### get_dataset

```python
get_dataset(
    workspace_id="workspace_id",
    dataset_id="dataset_id",
)
```

Parameters:
- `workspace_id` (必须): 知识库所属的 workspace ID
- `dataset_id` (必须): 要获取信息的知识库 ID

#### call_knowledge_engine_tool

```python
call_knowledge_engine_tool(
    workspace_id="workspace_id",
    dataset_ids=["dataset_id"],
    tool_name="knowledge_search",
    queries=["如何重置密码？"],
    top_k=3,
    score_threshold=0.2,
)
```

Parameters:
- `workspace_id` (必须): 知识库所属的 workspace ID
- `dataset_ids` (必须): 要检索的知识库 ID 列表，至少 1 个
- `tool_name` (可选): 子工具名称，默认 `knowledge_search`；当前仅支持 `knowledge_search`
- `queries` (可选): 检索查询词列表（`knowledge_search` 必填）
- `top_k` (可选): 返回的最大结果数
- `score_threshold` (可选): 相关性分数阈值（0~1）
- `rerank_id` (可选): 重排模型 ID
- `knowledge_run_mode` (可选): 运行模式，枚举 `quick` / `smart_search` / `wiki_search`

## 最佳实践与测试 Prompt

推荐的使用顺序，以及每个透出方法的自然语言测试 Prompt 与期望结果——这些 Prompt 也可作为接入 MCP 客户端后的手工冒烟测试。

**推荐流程：** `health_check`（确认配置）→ `list_datasets`（获取 `DatasetIDs`）→ 可选 `get_dataset`（读默认检索参数）→ `call_knowledge_engine_tool`（检索）。`WorkspaceID` 无法通过本 Server 列举，需从 HiAgent 控制台网页 URL（`.../workspace/<id>/...`）获取。

#### health_check

- **最佳实践：** 在任何需要凭证的工具之前先调用它，确认 Server 已读到 AK/SK 与 top host。它不调用 OpenAPI、不回显任何凭证，只返回布尔值。
- **测试 Prompt：** “检查 HiAgent MCP Server 是否健康、配置是否齐备。”
- **期望结果：** `status="ok"`、`auth="aksk"`，环境变量齐备时 `configured=true` 且各 `*_configured` 为 true；不返回任何凭证明文。

#### list_datasets

- **最佳实践：** 用它获取 `call_knowledge_engine_tool` 所需的 `DatasetIDs`；用 `page_number`/`page_size`（1~100）分页，不要一次性全量拉取。dataset 即知识库。
- **测试 Prompt：** “列出 workspace `<workspace_id>` 下的知识库。”
- **期望结果：** 分页的知识库列表，每项含 id 与名称，可用于后续知识引擎调用。

#### get_dataset

- **最佳实践：** 当需要某知识库的默认检索参数（如 `RetrievalTopK`、`RetrievalScoreThreshold`）时调用，使 `call_knowledge_engine_tool` 的入参与该库配置保持一致。
- **测试 Prompt：** “展示 workspace `<workspace_id>` 下知识库 `<dataset_id>` 的详情与默认检索设置。”
- **期望结果：** 该知识库的元数据，含默认检索参数。

#### call_knowledge_engine_tool

- **最佳实践：** 传入 1~5 条简短、可独立理解的 `queries`（不要传整段对话）；`top_k` 从较小值（如 3）起步、`score_threshold` 取适中值（如 0.2）再调优。本版本仅支持 `tool_name="knowledge_search"`。
- **测试 Prompt：** “在 workspace `<workspace_id>` 的知识库 `[<dataset_id>]` 中检索「如何重置密码？」，返回相关度最高的 3 个切片。”
- **期望结果：** `Result.KnowledgeSearch.Hits[]`，每个 hit 含 `DatasetID` / `DocumentID` / `SegmentID` / `Content`；不支持的 `tool_name` 返回明确错误，非法入参（`queries` 为空、`score_threshold` 越界）触发校验错误。

### uvx 启动

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

## 证书

volcengine/mcp-server is licensed under the [MIT License](https://github.com/volcengine/mcp-server/blob/main/LICENSE).
