"""Command line entrypoint for the HiAgent MCP server."""

from __future__ import annotations

import argparse
import logging
import os

from mcp_server_hiagent.versions import (
    DEFAULT_VERSION,
    SUPPORTED_VERSIONS,
    load_version_module,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    """Run the HiAgent MCP server."""

    parser = argparse.ArgumentParser(description="Run the HiAgent MCP Server")
    parser.add_argument(
        "--transport",
        "-t",
        choices=["stdio", "streamable-http"],
        default="stdio",
        help="Transport protocol. 'stdio' (default) for local plugin hosts "
        "(e.g. HiAgent STDIO); 'streamable-http' for a long-running HTTP server.",
    )
    parser.add_argument(
        "--hiagent-version",
        help="HiAgent OpenAPI compatibility version to use (e.g. "
        f"{DEFAULT_VERSION}). Overrides the HIAGENT_VERSION environment "
        "variable. Defaults to the latest registered version. "
        f"Supported: {', '.join(SUPPORTED_VERSIONS)}.",
    )
    parser.add_argument(
        "--host",
        help="Server host (streamable-http only). Overrides MCP_SERVER_HOST.",
    )
    parser.add_argument(
        "--port",
        type=int,
        help="Server port (streamable-http only). Overrides MCP_SERVER_PORT.",
    )
    args = parser.parse_args()

    # Select the HiAgent OpenAPI compatibility implementation by version.
    # Precedence: --hiagent-version CLI flag > HIAGENT_VERSION env > latest.
    version = (
        args.hiagent_version
        or os.getenv("HIAGENT_VERSION", "").strip()
        or DEFAULT_VERSION
    )
    impl = load_version_module(version)
    logger.info("Using HiAgent version %s", version)

    mcp = impl.create_mcp_server()

    if args.transport == "stdio":
        logger.info("Starting HiAgent MCP Server with stdio transport")
        mcp.run(transport="stdio")
        return

    if args.host:
        os.environ["MCP_SERVER_HOST"] = args.host
    if args.port is not None:
        os.environ["MCP_SERVER_PORT"] = str(args.port)

    server_config = impl.load_server_config()
    logger.info("Starting HiAgent MCP Server with streamable-http transport")
    mcp.run(
        transport="streamable-http",
        host=server_config.host,
        port=server_config.port,
        path=server_config.streamable_http_path,
        stateless_http=os.getenv("STATELESS_HTTP", "true").lower() == "true",
    )


if __name__ == "__main__":
    main()
