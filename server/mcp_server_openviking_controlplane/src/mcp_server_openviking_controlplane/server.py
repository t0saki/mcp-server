import argparse
import logging
import os
from typing import Any, Dict, Optional

from mcp.server import FastMCP

from mcp_server_openviking_controlplane.client import ControlPlaneError, get_client

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Create MCP server
mcp = FastMCP(
    "OpenViking Control Plane MCP Server",
    port=int(os.getenv("PORT", "8000")),
    streamable_http_path=os.getenv("STREAMABLE_HTTP_PATH", "/mcp"),
)


def _err(e: Exception) -> Dict[str, Any]:
    if isinstance(e, ControlPlaneError):
        return {"error": {"code": e.code, "message": e.message, "request_id": e.request_id}}
    return {"error": {"message": str(e)}}


@mcp.tool()
def list_collections(project: Optional[str] = None) -> Dict[str, Any]:
    """List OpenViking collections (OV libraries) under the configured account.

    Args:
        project: optional project filter; defaults to the configured project
                 (OPENVIKING_PROJECT, else "default").

    Returns:
        {"Collections": [ ...CollectionInfoData... ]}
    """
    try:
        return get_client().list_collections(project=project)
    except Exception as e:
        logger.error(f"list_collections failed: {e}")
        return _err(e)


@mcp.tool()
def get_collection(resource_id: str) -> Dict[str, Any]:
    """Get basic info of one OpenViking collection by ResourceID.

    Args:
        resource_id: target library ResourceID (the unique primary key).

    Returns:
        CollectionInfoData: Name, Creator, Project, ResourceID, Version, Source,
        Description, Status, OpenvikingVersion, VLM/Embedding (no secrets), CreateTime,
        UpdateTime (Unix seconds), etc.
    """
    try:
        return get_client().get_collection(resource_id)
    except Exception as e:
        logger.error(f"get_collection failed: {e}")
        return _err(e)


@mcp.tool()
def get_usage(resource_id: str) -> Dict[str, Any]:
    """Get overall usage / file counts for one OpenViking collection by ResourceID.

    Args:
        resource_id: target library ResourceID.

    Returns:
        {"CurContextFileNum", "ResourcesFileNum", "UserFileNum",
         "FreshTime" (Unix seconds), "EstimatedCosts"}. Counts are whole-library +
         the three top-level dirs only; per-uri breakdown is not supported.
    """
    try:
        return get_client().get_usage(resource_id)
    except Exception as e:
        logger.error(f"get_usage failed: {e}")
        return _err(e)


@mcp.tool()
def get_collection_api_key(resource_id: str) -> Dict[str, Any]:
    """Get the plaintext data-plane API Key of one collection by ResourceID.

    Backed by the action GetOpenVikingCollectionUserAccess. Returns the library's
    default-user credential. You can only query libraries under your own account;
    there is no cross-account / sudo lookup. NOTE: the ApiKey is plaintext — handle
    and surface it with care.

    Args:
        resource_id: target library ResourceID.

    Returns:
        {"UserID", "Role", "ApiKey"}
    """
    try:
        return get_client().get_user_access(resource_id)
    except Exception as e:
        logger.error(f"get_collection_api_key failed: {e}")
        return _err(e)


@mcp.tool()
def create_collection(
    name: str,
    vlm: Optional[Dict[str, Any]] = None,
    embedding: Optional[Dict[str, Any]] = None,
    source: str = "agentplan",
    version: str = "developer",
    project: Optional[str] = None,
    description: Optional[str] = None,
    openviking_version: Optional[str] = None,
) -> Dict[str, Any]:
    """⚠️ Creates a NEW, BILLABLE OpenViking collection (provisions a Helm release).

    CONFIRM WITH THE USER before calling — this consumes paid quota (max 20 libraries
    per account, returns QuotaExceeded beyond that). Requires the account to have
    AgentPlan deduction activated (otherwise ProductUnordered). Do NOT call
    speculatively.

    Args:
        name: library name, regex ^[a-zA-Z][a-zA-Z0-9_]*$, length <= 64.
        vlm: optional VLM model config, e.g. {"ModelName": "...", "ApiKeyID": "..."}.
             For source="agentplan" this can be omitted — the model name defaults
             to the AgentPlan VLM and the ApiKey falls back to the configured
             AgentPlan key. ApiKeyID and ApiKey are mutually exclusive.
        embedding: optional embedding model config, same shape/defaults as vlm.
        source: model source — "agentplan" (default), "volcengine", or "codeplan".
        version: library tier — "developer" (default) or "enterprise". The
                 enterprise tier has higher capacity and is billed at enterprise
                 rates (25 AFP baseline / 200k files, then tiered per 100k files
                 beyond). Any other value is rejected immediately with an error.
        project: project name; defaults to the configured project.
        description: optional, length <= 65535.
        openviking_version: optional image version.

    Returns:
        {"ResourceID": "...", "Success": true}
    """
    try:
        return get_client().create_collection(
            name=name,
            source=source,
            vlm=vlm,
            embedding=embedding,
            version=version,
            project=project,
            description=description,
            openviking_version=openviking_version,
        )
    except Exception as e:
        logger.error(f"create_collection failed: {e}")
        return _err(e)


@mcp.tool()
def update_collection(
    resource_id: str,
    description: Optional[str] = None,
    openviking_version: Optional[str] = None,
) -> Dict[str, Any]:
    """Update mutable fields of an OpenViking collection (UpdateOpenVikingCollection).

    Requires the AgentPlan key to be associated with the target library. CONFIRM WITH
    THE USER before calling — this mutates a live library. The backend re-validates
    model credentials on update, so VLM/Embedding are sent automatically using the
    configured AgentPlan key. NOTE: an empty/whitespace description is a server-side
    no-op — the description can only be overwritten with a non-empty value.

    Args:
        resource_id: target library ResourceID.
        description: new description, length <= 65535 (non-empty to take effect).
        openviking_version: new image version.

    Returns:
        {"Success": true}
    """
    try:
        return get_client().update_collection(
            resource_id,
            description=description,
            openviking_version=openviking_version,
        )
    except Exception as e:
        logger.error(f"update_collection failed: {e}")
        return _err(e)


@mcp.tool()
def list_collection_users(resource_id: str) -> Dict[str, Any]:
    """List the users registered under one OpenViking collection.

    Backed by ListOpenVikingCollectionUser. Requires the AgentPlan key to be
    associated with the target library. NOTE: the ApiKey in each entry is MASKED;
    to get a plaintext data-plane key use get_collection_api_key.

    Args:
        resource_id: target library ResourceID.

    Returns:
        {"UserList": [ {"UserID", "Role", "ApiKey" (masked)} ], "Total": N}
    """
    try:
        return get_client().list_collection_users(resource_id)
    except Exception as e:
        logger.error(f"list_collection_users failed: {e}")
        return _err(e)


@mcp.tool()
def register_collection_user(
    resource_id: str, user_id: str, role: Optional[str] = None
) -> Dict[str, Any]:
    """Register a NEW user under an OpenViking collection (RegisterOpenVikingUser).

    Requires the AgentPlan key to be associated with the target library. CONFIRM
    WITH THE USER before calling — this creates a new credentialed user.

    Args:
        resource_id: target library ResourceID.
        user_id: the UserID for the new user (unique within the library).
        role: optional role, e.g. "admin" or "user".

    Returns:
        {"Success": true}
    """
    try:
        return get_client().register_user(resource_id, user_id, role=role)
    except Exception as e:
        logger.error(f"register_collection_user failed: {e}")
        return _err(e)


@mcp.tool()
def update_collection_user(
    resource_id: str,
    user_id: str,
    role: Optional[str] = None,
) -> Dict[str, Any]:
    """Update a user under an OpenViking collection (UpdateOpenVikingUser).

    Only the fields you pass (non-None) are changed. Requires the AgentPlan key to be
    associated with the target library. CONFIRM WITH THE USER before calling.

    Args:
        resource_id: target library ResourceID.
        user_id: the UserID to update.
        role: optional new role, e.g. "admin" or "user".

    Returns:
        {"Success": true}
    """
    try:
        return get_client().update_user(resource_id, user_id, role=role)
    except Exception as e:
        logger.error(f"update_collection_user failed: {e}")
        return _err(e)


@mcp.tool()
def delete_collection_user(resource_id: str, user_id: str) -> Dict[str, Any]:
    """⚠️ Delete a user from an OpenViking collection (DeleteOpenVikingUser).

    CONFIRM WITH THE USER before calling. This revokes the user's credential and
    cannot be undone. Requires the AgentPlan key to be associated with the library.

    Args:
        resource_id: target library ResourceID.
        user_id: the UserID to delete.

    Returns:
        {"Success": true}
    """
    try:
        return get_client().delete_user(resource_id, user_id)
    except Exception as e:
        logger.error(f"delete_collection_user failed: {e}")
        return _err(e)


@mcp.tool()
def delete_collection(resource_id: str) -> Dict[str, Any]:
    """⚠️ IRREVERSIBLY deletes an OpenViking collection (uninstalls its Helm release).

    CONFIRM WITH THE USER before calling. This cannot be undone; all data in the
    library is lost.

    Args:
        resource_id: target library ResourceID.

    Returns:
        {"Success": true}
    """
    try:
        return get_client().delete_collection(resource_id)
    except Exception as e:
        logger.error(f"delete_collection failed: {e}")
        return _err(e)


def main():
    """Main entry point for the OpenViking Control Plane MCP server."""
    parser = argparse.ArgumentParser(description="Run the OpenViking Control Plane MCP Server")
    parser.add_argument(
        "--transport",
        "-t",
        choices=["sse", "stdio"],
        default="stdio",
        help="Transport protocol to use (sse or stdio)",
    )
    args = parser.parse_args()
    logger.info(f"Starting OpenViking Control Plane MCP Server with {args.transport} transport")

    try:
        mcp.run(transport=args.transport)
    except Exception as e:
        logger.error(f"Error starting OpenViking Control Plane MCP Server: {str(e)}")
        raise


if __name__ == "__main__":
    main()
