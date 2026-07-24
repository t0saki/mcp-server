import json
import logging
from typing import Any, Dict, Optional

import requests

from mcp_server_openviking_controlplane.common.auth import AuthProvider, BearerTokenAuth
from mcp_server_openviking_controlplane.config import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_VLM_MODEL,
    VERSION_CHOICES,
    ControlPlaneConfig,
    get_config,
)

logger = logging.getLogger(__name__)

# Headers we never replay verbatim: requests recomputes them, or a stale value
# breaks the request. We always send a freshly serialized JSON body.
_DROP_HEADERS = {"content-length", "connection", "accept-encoding"}


class ControlPlaneError(RuntimeError):
    """Raised when the control plane returns an Error envelope or a non-200 status."""

    def __init__(self, code: str, message: str, request_id: str = ""):
        self.code = code
        self.message = message
        self.request_id = request_id
        suffix = f" (RequestId={request_id})" if request_id else ""
        super().__init__(f"[{code}] {message}{suffix}")


class ControlPlaneClient:
    """Shared core used by both the MCP tools (``server.py``) and the CLI (``cli.py``).

    One method per control-plane Action. Each builds the request body, attaches auth
    headers via the ``AuthProvider``, POSTs, and unwraps the TOP response envelope.
    """

    def __init__(
        self,
        config: ControlPlaneConfig,
        auth: Optional[AuthProvider] = None,
        timeout: int = 30,
    ):
        self.config = config
        self.auth = auth or BearerTokenAuth(config.api_key)
        self.timeout = timeout

    def _request(self, action: str, body: Dict[str, Any]) -> Dict[str, Any]:
        # Console proxy: Action/Version are in the path, not the query string.
        path = self.config.action_path(action)
        body_str = json.dumps(body)

        headers = {"Content-Type": "application/json"}
        headers.update(self.auth.auth_headers("POST", path, {}, body_str))
        # Caller-supplied extra headers (e.g. x-tt-env for swim-lane routing);
        # protected keys (Authorization/Content-Type) are already filtered out.
        headers.update(self.config.safe_extra_headers())
        headers = {k: v for k, v in headers.items() if k.lower() not in _DROP_HEADERS}

        url = f"{self.config.base_url}{path}"
        logger.debug("POST %s body=%s", url, body_str)
        rsp = requests.request(
            "POST", url, data=body_str, headers=headers, timeout=self.timeout
        )
        return self._unwrap(action, rsp)

    @staticmethod
    def _unwrap(action: str, rsp: requests.Response) -> Dict[str, Any]:
        try:
            payload = rsp.json()
        except ValueError:
            raise ControlPlaneError(
                "InvalidResponse",
                f"{action} returned non-JSON (HTTP {rsp.status_code}): {rsp.text[:500]}",
            )

        meta = payload.get("ResponseMetadata", {}) if isinstance(payload, dict) else {}
        error = meta.get("Error")
        if error:
            raise ControlPlaneError(
                error.get("Code", "Unknown"),
                error.get("Message", ""),
                meta.get("RequestId", ""),
            )
        if rsp.status_code != 200:
            raise ControlPlaneError(
                "HTTPError",
                f"{action} HTTP {rsp.status_code}: {rsp.text[:500]}",
                meta.get("RequestId", ""),
            )
        return payload.get("Result", {}) if isinstance(payload, dict) else {}

    # --- Actions (6 core) ---------------------------------------------------

    def list_collections(self, project: Optional[str] = None) -> Dict[str, Any]:
        body: Dict[str, Any] = {}
        proj = project if project is not None else self.config.project
        if proj:
            body["Project"] = proj
        return self._request("ListOpenVikingCollections", body)

    def _model_block(
        self, cfg: Optional[Dict[str, Any]], source: str, default_model: str
    ) -> Dict[str, Any]:
        """Build a VLM/Embedding block in the multi-credential (Credentials[]) form.

        The new control-plane create format carries credentials per-model as an
        ordered failover list. We emit one credential built from ``source`` plus
        the supplied key fields; for ``source == "agentplan"`` the model credential
        is the AgentPlan ApiKey itself, so it falls back to the configured key.
        An advanced caller may instead pass a ready-made ``Credentials`` list
        (e.g. for multi-source failover), which is passed through verbatim."""
        cfg = dict(cfg or {})
        model_name = cfg.get("ModelName") or default_model

        creds = cfg.get("Credentials")
        if creds:  # caller already supplied the failover list — pass through
            return {"ModelName": model_name, "Credentials": creds}

        api_key = cfg.get("ApiKey")
        api_key_id = cfg.get("ApiKeyID")
        if not api_key and not api_key_id and source == "agentplan":
            api_key = self.config.api_key

        cred: Dict[str, Any] = {"Source": source}
        if api_key_id:
            cred["ApiKeyID"] = api_key_id
        if api_key:
            cred["ApiKey"] = api_key
        if cfg.get("EndpointID"):  # volcengine source only
            cred["EndpointID"] = cfg["EndpointID"]
        return {"ModelName": model_name, "Credentials": [cred]}

    def create_collection(
        self,
        name: str,
        source: str = "agentplan",
        vlm: Optional[Dict[str, Any]] = None,
        embedding: Optional[Dict[str, Any]] = None,
        version: str = "developer",
        project: Optional[str] = None,
        description: Optional[str] = None,
        openviking_version: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if version not in VERSION_CHOICES:
            raise ValueError(
                f"invalid version {version!r}; expected one of {', '.join(VERSION_CHOICES)}"
            )
        # Multi-credential create format: top-level Source is omitted (each model
        # carries its source inside Credentials[]).
        body: Dict[str, Any] = {
            "Name": name,
            "Version": version,
            "VLM": self._model_block(vlm, source, DEFAULT_VLM_MODEL),
            "Embedding": self._model_block(embedding, source, DEFAULT_EMBEDDING_MODEL),
        }
        proj = project if project is not None else self.config.project
        if proj:
            body["Project"] = proj
        if description is not None:
            body["Description"] = description
        if openviking_version:
            body["OpenvikingVersion"] = openviking_version
        if extra:
            body.update(extra)  # Feishu / GitHub / Memory, etc.
        return self._request("CreateOpenVikingCollection", body)

    def get_collection(self, resource_id: str) -> Dict[str, Any]:
        return self._request("GetOpenVikingCollection", {"ResourceID": resource_id})

    def update_collection(
        self,
        resource_id: str,
        description: Optional[str] = None,
        source: str = "agentplan",
        vlm: Optional[Dict[str, Any]] = None,
        embedding: Optional[Dict[str, Any]] = None,
        openviking_version: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Update a collection's mutable fields (e.g. Description).

        NOTE: the backend re-validates model credentials on every update, so VLM and
        Embedding blocks are always sent (built like ``create_collection`` — for
        ``source == "agentplan"`` the model credential falls back to the configured
        AgentPlan key). Passing an empty/whitespace Description is a server-side no-op
        (the field is only overwritten by a non-empty value). ``extra`` is merged
        verbatim for forward-compatibility (e.g. an eventual ``PaymentConfig``)."""
        body: Dict[str, Any] = {
            "ResourceID": resource_id,
            "VLM": self._model_block(vlm, source, DEFAULT_VLM_MODEL),
            "Embedding": self._model_block(embedding, source, DEFAULT_EMBEDDING_MODEL),
        }
        if description is not None:
            body["Description"] = description
        if openviking_version is not None:
            body["OpenvikingVersion"] = openviking_version
        if extra:
            body.update(extra)
        return self._request("UpdateOpenVikingCollection", body)

    def delete_collection(self, resource_id: str) -> Dict[str, Any]:
        return self._request("DeleteOpenVikingCollection", {"ResourceID": resource_id})

    def get_usage(self, resource_id: str) -> Dict[str, Any]:
        result = self._request("GetOpenVikingUsage", {"ResourceID": resource_id})
        # AgentFileNum is not meaningful here; drop it from the returned usage.
        result.pop("AgentFileNum", None)
        return result

    def get_user_access(self, resource_id: str) -> Dict[str, Any]:
        # On the data-plane cluster the api-key action is registered as
        # GetOpenVikingCollectionUserAccess (the console proxy's
        # AccessOpenVikingApiKey is NOT routed here — it 404s). Returns the
        # default user's PLAINTEXT key: {"UserID", "Role", "ApiKey"}.
        # (ListOpenVikingCollectionUser only returns a masked key.)
        return self._request(
            "GetOpenVikingCollectionUserAccess", {"ResourceID": resource_id}
        )

    # --- User management (enterprise-tier libraries: multi-user) -------------
    # These require the AgentPlan key to be associated with the target library;
    # operating on an unassociated library is rejected server-side. The ApiKey in
    # a List response is MASKED — fetch the plaintext key via get_user_access.

    def list_collection_users(self, resource_id: str) -> Dict[str, Any]:
        # ListOpenVikingCollectionUser: users under the library (ApiKey masked).
        return self._request(
            "ListOpenVikingCollectionUser", {"ResourceID": resource_id}
        )

    def register_user(
        self,
        resource_id: str,
        user_id: str,
        role: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        # RegisterOpenVikingUser: create a new user under the library. UserID is
        # required; Role is e.g. "admin" / "user".
        body: Dict[str, Any] = {"ResourceID": resource_id, "UserID": user_id}
        if role is not None:
            body["Role"] = role
        if extra:
            body.update(extra)
        return self._request("RegisterOpenVikingUser", body)

    def update_user(
        self,
        resource_id: str,
        user_id: str,
        role: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        # UpdateOpenVikingUser: update a user's mutable fields (e.g. Role).
        body: Dict[str, Any] = {"ResourceID": resource_id, "UserID": user_id}
        if role is not None:
            body["Role"] = role
        if extra:
            body.update(extra)
        return self._request("UpdateOpenVikingUser", body)

    def delete_user(self, resource_id: str, user_id: str) -> Dict[str, Any]:
        # DeleteOpenVikingUser: remove a user from the library.
        return self._request(
            "DeleteOpenVikingUser", {"ResourceID": resource_id, "UserID": user_id}
        )


_client: Optional[ControlPlaneClient] = None


def get_client() -> ControlPlaneClient:
    """Lazy singleton used by the MCP server (config resolved from the environment)."""
    global _client
    if _client is None:
        _client = ControlPlaneClient(get_config())
    return _client
