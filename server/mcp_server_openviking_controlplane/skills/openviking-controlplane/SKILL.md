---
name: openviking-controlplane
description: Manage OpenViking collections (OV libraries) from the command line with `ov-cp` — list / create / get / update / usage / get the data-plane API key / delete, plus managing the users of an enterprise-tier library (list / register / update / delete). Use when the user wants to provision or inspect an OpenViking library, fetch a library's data-plane API key, do the create→get-key cold-start, manage a library's users, or otherwise drive the OpenViking control plane (topapi). Authenticates with an Ark AgentPlan ApiKey.
---

# OpenViking Control Plane (`ov-cp`)

`ov-cp` is the CLI for the OpenViking control plane (topapi). It manages OV
**collections** (libraries) and shares its core with the
`mcp-server-openviking-controlplane` MCP server, so behavior is identical.

## Setup

Install once (from the package dir): `uv sync` (or `pip install -e .`).

Configure via env vars (CLI flags `-k` / `-e` / `--project` override them):

| Env var | Meaning | Default |
|---|---|---|
| `AGENTPLAN_API_KEY` | Ark AgentPlan ApiKey (sent as `Authorization: Bearer`) | — (required) |
| `VIKING_ENDPOINT` | Control-plane base URL | `https://api.vikingdb.cn-beijing.volces.com/openviking` |
| `OPENVIKING_PROJECT` | Default project | `default` |
| `VIKING_EXTRA_HEADERS` | Extra request headers, comma-separated `Key: Value` | — |

```bash
export AGENTPLAN_API_KEY=ark-xxxxxxxx
# VIKING_ENDPOINT defaults to the public gateway — leave it unset for normal use.
```

> The default endpoint is the **reserved** public gateway (not open yet). Override
> `VIKING_ENDPOINT` (or `-e`) only for testing — e.g. point it at a `kubectl
> port-forward` of the data-plane service. The full request URL is
> `{endpoint}/api/openviking/{Action}`.

## Commands

```bash
ov-cp list                       # list collections (optionally --project X)
ov-cp get     <ResourceID>       # collection info (Status, models, version, ...)
ov-cp usage   <ResourceID>       # file counts / estimated cost
ov-cp api-key <ResourceID>       # plaintext data-plane key {UserID, Role, ApiKey}
ov-cp create  --name my_kb       # create a collection (see below)
ov-cp update  <ResourceID> --description "..."   # update mutable fields
ov-cp delete  <ResourceID> --yes # delete (irreversible; uninstalls the Helm release)

# users of an enterprise-tier library (key must be associated with the library):
ov-cp user list     <ResourceID>                     # users (ApiKey is masked)
ov-cp user register <ResourceID> xiaohong --role user  # add a user (UserID + role)
ov-cp user update   <ResourceID> xiaohong --role admin
ov-cp user delete   <ResourceID> xiaohong --yes      # revoke a user's credential
```

Output is JSON. Errors print `Error [Code]: Message` to stderr with exit code 1.
`ov-cp --help` and `ov-cp <cmd> --help` work without any config.

## Creating a collection

⚠️ **Billable + requires the account to have AgentPlan deduction activated** (else
`ProductUnordered`). Confirm with the user before creating. Max 20 libraries/account.

For `--source agentplan` (default) you only need `--name`: the VLM/Embedding model
names default to `doubao-seed-2.0-lite` / `doubao-embedding-vision`, and the model
ApiKey falls back to the configured AgentPlan key.

```bash
ov-cp create --name my_kb
# enterprise tier (higher capacity, enterprise billing rates):
ov-cp create --name my_kb --version enterprise
# other sources need explicit model creds:
ov-cp create --name my_kb --source volcengine \
  --vlm-api-key-id <id> --vlm-endpoint-id <ep> \
  --emb-api-key-id <id> --emb-endpoint-id <ep>
```

`--version` is `developer` (default) or `enterprise`; any other value is rejected
locally before the request.

## Cold-start chain (create → use the library)

```bash
RID=$(ov-cp create --name my_kb | python3 -c 'import sys,json;print(json.load(sys.stdin)["ResourceID"])')
# Poll until provisioned; api-key times out while Status is INIT.
ov-cp get "$RID"        # wait for "Status": "READY"
ov-cp api-key "$RID"    # -> the plaintext data-plane key for the library
```

The returned `ApiKey` is the library's **data-plane** key. Use it as
`Authorization: Bearer <key>` against the library's data-plane (e.g.
`GET {endpoint}/health`, `GET {endpoint}/api/v1/system/status`,
`GET {endpoint}/api/v1/fs/ls?uri=viking://`).

## Notes

- Only `Authorization: Bearer` is accepted (no `X-API-Key`).
- Read-only actions (list/get/usage/delete) are not gated by AgentPlan; create and
  api-key are.
- `get`/`usage`/`api-key`/`delete`/`update` and all `user *` take a `ResourceID`
  (e.g. `ov-xxxxxxxx`).
- `user *` manages the multiple users of an **enterprise-tier** library and needs the
  AgentPlan key to be **associated with that library** (else the backend rejects it).
  `user list` returns each user's **masked** ApiKey; for a plaintext data-plane key
  use `api-key`.
- Extra headers: pass `-H 'Key: Value'` (repeatable) or set `VIKING_EXTRA_HEADERS`
  to a comma-separated `Key: Value` list — e.g. `-H 'x-tt-env: lujiakun'` for
  swim-lane routing. `Authorization` / `Content-Type` are protected and ignored.
