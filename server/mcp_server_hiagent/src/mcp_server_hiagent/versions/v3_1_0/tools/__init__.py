"""Business-domain tool registration for HiAgent MCP Server."""

from mcp_server_hiagent.versions.v3_1_0.tools._common import OpenAPIClient
from mcp_server_hiagent.versions.v3_1_0.tools.dataset import register_dataset_tools
from mcp_server_hiagent.versions.v3_1_0.tools.knowledge import register_knowledge_tools


__all__ = [
    "OpenAPIClient",
    "register_dataset_tools",
    "register_knowledge_tools",
]
