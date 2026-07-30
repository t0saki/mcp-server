import json
import logging
from typing import Any, Dict, List, Optional

import click
import typer

from mcp_server_openviking_controlplane.client import ControlPlaneClient, ControlPlaneError
from mcp_server_openviking_controlplane.config import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_VLM_MODEL,
    PAY_TYPE_CHOICES,
    VERSION_CHOICES,
    build_config,
    parse_extra_headers,
)

logging.basicConfig(
    level=logging.WARNING, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

app = typer.Typer(
    help=(
        "OpenViking control plane (topapi) CLI — manage OV collections. "
        "Shares the same core (client.py) as the MCP server."
    ),
    no_args_is_help=True,
    add_completion=True,
)


def _print(result: Any) -> None:
    typer.echo(json.dumps(result, indent=2, ensure_ascii=False))


def _fail(e: Exception) -> "typer.Exit":
    if isinstance(e, ControlPlaneError):
        suffix = f" (RequestId={e.request_id})" if e.request_id else ""
        typer.echo(f"Error [{e.code}]: {e.message}{suffix}", err=True)
    else:
        typer.echo(f"Error: {e}", err=True)
    raise typer.Exit(code=1)


def _client(ctx: typer.Context) -> ControlPlaneClient:
    """Build the shared client lazily so `--help` never needs valid config."""
    try:
        return ctx.obj()
    except Exception as e:
        raise _fail(e)


def _model_cfg(
    model_name: str,
    api_key_id: Optional[str],
    api_key: Optional[str],
    endpoint_id: Optional[str],
) -> Dict[str, Any]:
    """Assemble a VLM/Embedding model config from whatever the caller supplied.

    No key is required here: for the ``agentplan`` source the client fills in the
    configured AgentPlan ApiKey; other sources are validated server-side."""
    cfg: Dict[str, Any] = {"ModelName": model_name}
    if api_key_id:
        cfg["ApiKeyID"] = api_key_id
    if api_key:
        cfg["ApiKey"] = api_key
    if endpoint_id:
        cfg["EndpointID"] = endpoint_id
    return cfg


@app.callback()
def main_callback(
    ctx: typer.Context,
    endpoint: Optional[str] = typer.Option(
        None, "--endpoint", "-e",
        help="Control-plane base URL (overrides VIKING_ENDPOINT). "
             "For local testing point at a port-forward, e.g. http://localhost:18080",
    ),
    api_key: Optional[str] = typer.Option(
        None, "--api-key", "-k",
        help="Ark AgentPlan ApiKey, sent as 'Authorization: Bearer' (overrides AGENTPLAN_API_KEY).",
    ),
    project: Optional[str] = typer.Option(
        None, "--project", help="Default project (overrides OPENVIKING_PROJECT)."
    ),
    header: Optional[List[str]] = typer.Option(
        None, "--header", "-H",
        help="Extra request header as 'Key: Value'; repeatable. Merged over "
             "VIKING_EXTRA_HEADERS (CLI wins). E.g. -H 'x-tt-env: lujiakun' to "
             "route into a swim-lane.",
    ),
):
    """Stash a client factory on the context; commands build it on demand."""

    def _factory() -> ControlPlaneClient:
        extra_headers: Dict[str, str] = {}
        for item in header or []:
            extra_headers.update(parse_extra_headers(item))
        config = build_config(
            endpoint=endpoint,
            project=project,
            api_key=api_key,
            extra_headers=extra_headers,
        )
        return ControlPlaneClient(config)

    ctx.obj = _factory


@app.command("list")
def list_cmd(
    ctx: typer.Context,
    project: Optional[str] = typer.Option(None, "--project", help="Filter by project."),
):
    """List collections under the account."""
    client = _client(ctx)
    try:
        _print(client.list_collections(project=project))
    except Exception as e:
        raise _fail(e)


@app.command("get")
def get_cmd(ctx: typer.Context, resource_id: str = typer.Argument(..., help="Target library ResourceID.")):
    """Get basic info of a collection."""
    client = _client(ctx)
    try:
        _print(client.get_collection(resource_id))
    except Exception as e:
        raise _fail(e)


@app.command("usage")
def usage_cmd(ctx: typer.Context, resource_id: str = typer.Argument(..., help="Target library ResourceID.")):
    """Get overall usage / file counts of a collection."""
    client = _client(ctx)
    try:
        _print(client.get_usage(resource_id))
    except Exception as e:
        raise _fail(e)


@app.command("api-key")
def api_key_cmd(ctx: typer.Context, resource_id: str = typer.Argument(..., help="Target library ResourceID.")):
    """Get the plaintext data-plane API Key of a collection (default user)."""
    client = _client(ctx)
    try:
        _print(client.get_user_access(resource_id))
    except Exception as e:
        raise _fail(e)


@app.command("create")
def create_cmd(
    ctx: typer.Context,
    name: str = typer.Option(..., help="Library name ^[a-zA-Z][a-zA-Z0-9_]*$, <=64."),
    source: str = typer.Option("agentplan", help="Model source: agentplan | volcengine | codeplan."),
    version: str = typer.Option(
        "developer",
        help="Library tier: developer (default) | enterprise "
             "(higher capacity, billed at enterprise rates).",
        click_type=click.Choice(VERSION_CHOICES),
        metavar="[developer|enterprise]",
    ),
    vlm_model: str = typer.Option(DEFAULT_VLM_MODEL, help="VLM ModelName."),
    vlm_api_key_id: Optional[str] = typer.Option(None, help="VLM ApiKeyID (exclusive with --vlm-api-key)."),
    vlm_api_key: Optional[str] = typer.Option(None, help="VLM ApiKey (defaults to --api-key when source=agentplan)."),
    vlm_endpoint_id: Optional[str] = typer.Option(None, help="VLM EndpointID (volcengine source only)."),
    emb_model: str = typer.Option(DEFAULT_EMBEDDING_MODEL, help="Embedding ModelName."),
    emb_api_key_id: Optional[str] = typer.Option(None, help="Embedding ApiKeyID (exclusive with --emb-api-key)."),
    emb_api_key: Optional[str] = typer.Option(None, help="Embedding ApiKey (defaults to --api-key when source=agentplan)."),
    emb_endpoint_id: Optional[str] = typer.Option(None, help="Embedding EndpointID (volcengine source only)."),
    project: Optional[str] = typer.Option(None, help="Project name (defaults to configured)."),
    description: Optional[str] = typer.Option(None, help="Description, <=65535 chars."),
    openviking_version: Optional[str] = typer.Option(None, help="Image version (optional)."),
    pay_type: Optional[str] = typer.Option(
        None, "--pay-type",
        help="Billing: agentplan_personal (personal AgentPlan AFP deduction) | "
             "agentplan_enterprise (an enterprise seat's AFP pays; requires "
             "--seat-id) | volc_pay (Volcano pay-as-you-go). ⚠️ If omitted, the "
             "server defaults to volc_pay — REAL MONEY billed to the Volcano "
             "account, not AgentPlan AFP.",
        click_type=click.Choice(PAY_TYPE_CHOICES),
        metavar="[agentplan_personal|agentplan_enterprise|volc_pay]",
    ),
    seat_id: Optional[str] = typer.Option(
        None, "--seat-id",
        help="AgentPlan enterprise seat that pays (e.g. seat-2026...); required "
             "with --pay-type agentplan_enterprise. Copy it manually from the Ark "
             "console seat-management page — the server does NOT check the seat "
             "exists; a typo only surfaces at the next hourly deduction, which "
             "then disables the library.",
    ),
):
    """Create a new collection (consumes paid quota; max 20 per account).

    For source=agentplan you can pass just --name: the model names default to the
    AgentPlan models and the model ApiKey falls back to --api-key / AGENTPLAN_API_KEY.

    ⚠️ Billing: without --pay-type the server defaults the library to volc_pay
    (Volcano pay-as-you-go, real money). For AgentPlan AFP deduction pass
    --pay-type agentplan_personal, or --pay-type agentplan_enterprise --seat-id
    seat-xxx.
    """
    client = _client(ctx)
    if not (pay_type or seat_id):
        typer.echo(
            "warning: no --pay-type — the server will default this library to "
            "volc_pay (Volcano pay-as-you-go, REAL MONEY, not AgentPlan AFP). "
            "Pass --pay-type agentplan_personal or agentplan_enterprise for AFP "
            "deduction.",
            err=True,
        )
    vlm = _model_cfg(vlm_model, vlm_api_key_id, vlm_api_key, vlm_endpoint_id)
    embedding = _model_cfg(emb_model, emb_api_key_id, emb_api_key, emb_endpoint_id)
    try:
        _print(
            client.create_collection(
                name=name,
                source=source,
                vlm=vlm,
                embedding=embedding,
                version=version,
                project=project,
                description=description,
                openviking_version=openviking_version,
                pay_type=pay_type,
                seat_id=seat_id,
            )
        )
    except Exception as e:
        raise _fail(e)


@app.command("update")
def update_cmd(
    ctx: typer.Context,
    resource_id: str = typer.Argument(..., help="Target library ResourceID."),
    description: Optional[str] = typer.Option(None, help="New description, <=65535 chars."),
    openviking_version: Optional[str] = typer.Option(None, help="New image version."),
    pay_type: Optional[str] = typer.Option(
        None, "--pay-type",
        help="Switch billing: agentplan_personal (personal AgentPlan AFP) | "
             "agentplan_enterprise (an enterprise seat's AFP; requires --seat-id) "
             "| volc_pay (Volcano pay-as-you-go, real money). Omit to leave "
             "billing untouched.",
        click_type=click.Choice(PAY_TYPE_CHOICES),
        metavar="[agentplan_personal|agentplan_enterprise|volc_pay]",
    ),
    seat_id: Optional[str] = typer.Option(
        None, "--seat-id",
        help="AgentPlan enterprise seat that pays; required with --pay-type "
             "agentplan_enterprise (also how to re-bind after a seat was "
             "unbound). The server does NOT check the seat exists.",
    ),
):
    """Update mutable fields of a collection (only passed fields change).

    Also switches billing: e.g. `update <RID> --pay-type agentplan_enterprise
    --seat-id seat-xxx` moves the library to AFP deduction from that seat;
    `--pay-type volc_pay` moves it back to Volcano pay-as-you-go.
    """
    client = _client(ctx)
    try:
        _print(
            client.update_collection(
                resource_id,
                description=description,
                openviking_version=openviking_version,
                pay_type=pay_type,
                seat_id=seat_id,
            )
        )
    except Exception as e:
        raise _fail(e)


user_app = typer.Typer(
    help="Manage users under a collection (enterprise-tier libraries). "
    "All actions require the AgentPlan key to be associated with the library.",
    no_args_is_help=True,
)
app.add_typer(user_app, name="user")


@user_app.command("list")
def user_list_cmd(
    ctx: typer.Context,
    resource_id: str = typer.Argument(..., help="Target library ResourceID."),
):
    """List users under a collection (ApiKey is masked; use `api-key` for plaintext)."""
    client = _client(ctx)
    try:
        _print(client.list_collection_users(resource_id))
    except Exception as e:
        raise _fail(e)


@user_app.command("register")
def user_register_cmd(
    ctx: typer.Context,
    resource_id: str = typer.Argument(..., help="Target library ResourceID."),
    user_id: str = typer.Argument(..., help="UserID for the new user (unique in library)."),
    role: Optional[str] = typer.Option(None, help="Role, e.g. admin | user."),
):
    """Register a new user under a collection."""
    client = _client(ctx)
    try:
        _print(client.register_user(resource_id, user_id, role=role))
    except Exception as e:
        raise _fail(e)


@user_app.command("update")
def user_update_cmd(
    ctx: typer.Context,
    resource_id: str = typer.Argument(..., help="Target library ResourceID."),
    user_id: str = typer.Argument(..., help="Target UserID."),
    role: Optional[str] = typer.Option(None, help="New role, e.g. admin | user."),
):
    """Update a user under a collection (only passed fields change)."""
    client = _client(ctx)
    try:
        _print(client.update_user(resource_id, user_id, role=role))
    except Exception as e:
        raise _fail(e)


@user_app.command("delete")
def user_delete_cmd(
    ctx: typer.Context,
    resource_id: str = typer.Argument(..., help="Target library ResourceID."),
    user_id: str = typer.Argument(..., help="Target UserID."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
):
    """Delete a user from a collection (revokes its credential; irreversible)."""
    client = _client(ctx)
    if not yes:
        typer.confirm(
            f"Delete user {user_id} from collection {resource_id} (revokes its credential)?",
            abort=True,
        )
    try:
        _print(client.delete_user(resource_id, user_id))
    except Exception as e:
        raise _fail(e)


@app.command("delete")
def delete_cmd(
    ctx: typer.Context,
    resource_id: str = typer.Argument(..., help="Target library ResourceID."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
):
    """Delete a collection (irreversible; uninstalls its Helm release)."""
    client = _client(ctx)
    if not yes:
        typer.confirm(
            f"Irreversibly delete collection {resource_id} (uninstalls its Helm release)?",
            abort=True,
        )
    try:
        _print(client.delete_collection(resource_id))
    except Exception as e:
        raise _fail(e)


def main():
    app()


if __name__ == "__main__":
    main()
