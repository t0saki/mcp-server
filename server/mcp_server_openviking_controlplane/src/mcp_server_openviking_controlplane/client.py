import json
import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional

import requests

from mcp_server_openviking_controlplane.common.auth import AuthProvider, BearerTokenAuth
from mcp_server_openviking_controlplane.config import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_VLM_MODEL,
    PAY_TYPE_MAP,
    VERSION_CHOICES,
    ControlPlaneConfig,
    get_config,
)

logger = logging.getLogger(__name__)

# Headers we never replay verbatim: requests recomputes them, or a stale value
# breaks the request. We always send a freshly serialized JSON body.
_DROP_HEADERS = {"content-length", "connection", "accept-encoding"}
_AFP_PER_CNY = Decimal("500")


def _format_decimal(value: Decimal) -> str:
    """Render a decimal without scientific notation or insignificant zeroes."""
    rendered = format(value.normalize(), "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def enrich_usage_billing(
    usage: Dict[str, Any],
    collection: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Add unit, period, payment source and AgentPlan AFP to legacy usage data."""
    if isinstance(usage.get("EstimatedBilling"), dict):
        return usage
    estimated_cost = usage.get("EstimatedCosts")
    if estimated_cost is None:
        return usage

    billing: Dict[str, Any] = {
        "CNY": str(estimated_cost),
        "Period": "hour",
    }
    payment = (collection or {}).get("PaymentConfig")
    if isinstance(payment, dict):
        pay_type = payment.get("PayType")
        if pay_type:
            billing["PayType"] = pay_type
        agentplan = payment.get("AgentPlanConfig")
        if isinstance(agentplan, dict):
            scenario = agentplan.get("BusinessScenarios")
            if scenario:
                billing["BusinessScenarios"] = scenario
        if pay_type == "agentplan_pay":
            try:
                billing["AFP"] = _format_decimal(
                    Decimal(str(estimated_cost)) * _AFP_PER_CNY
                )
            except InvalidOperation:
                logger.warning(
                    "cannot convert EstimatedCosts=%r to AgentPlan AFP",
                    estimated_cost,
                )

    usage["EstimatedBilling"] = billing
    return usage


def build_payment_config(
    pay_type: Optional[str] = None,
    seat_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Validate billing arguments and build the ``PaymentConfig`` request block.

    ``pay_type`` is the flat user-facing enum (``agentplan_personal`` /
    ``agentplan_enterprise`` / ``volc_pay``); the wire split into PayType +
    BusinessScenarios happens here. Returns None when nothing was given — the
    server then defaults the library to ``volc_pay``: Volcano pay-as-you-go,
    with charges billed directly to the Volcano account rather than deducted
    from AgentPlan AFP. The server
    only checks a SeatId is non-empty, not that it exists: a typo surfaces at
    the next hourly deduction, after which the library is disabled.
    """
    if not (pay_type or seat_id):
        return None
    if pay_type is None:  # only seat_id was given
        raise ValueError(
            "seat_id alone is ambiguous: also pass pay_type='agentplan_enterprise'"
        )
    if pay_type == "agentplan_pay":
        raise ValueError(
            "'agentplan_pay' is ambiguous here: use 'agentplan_personal' or "
            "'agentplan_enterprise' (the choice is always explicit)"
        )
    if pay_type not in PAY_TYPE_MAP:
        raise ValueError(
            f"invalid pay_type {pay_type!r}; expected one of {', '.join(PAY_TYPE_MAP)} "
            "(empty_pay is not offered: an unbound library is unusable and "
            "auto-cleaned after 30 days)"
        )

    wire_type, scenario = PAY_TYPE_MAP[pay_type]
    if wire_type == "volc_pay":
        if seat_id:
            raise ValueError("seat_id only applies to pay_type='agentplan_enterprise'")
        return {"PayType": "volc_pay"}
    if scenario == "agent_plan_enterprise" and not seat_id:
        raise ValueError(
            "pay_type='agentplan_enterprise' requires seat_id — the seat that pays; "
            "copy it from the Ark console seat-management page"
        )
    if scenario == "agent_plan_personal" and seat_id:
        raise ValueError(
            "pay_type='agentplan_personal' must not carry a seat_id "
            "(a personal plan has no seat)"
        )
    return {
        "PayType": wire_type,
        "AgentPlanConfig": {"BusinessScenarios": scenario, "SeatId": seat_id or ""},
    }


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
        pay_type: Optional[str] = None,
        seat_id: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if version not in VERSION_CHOICES:
            raise ValueError(
                f"invalid version {version!r}; expected one of {', '.join(VERSION_CHOICES)}"
            )
        # Billing default: when the caller specifies nothing, bind the personal
        # AgentPlan instead of leaving PaymentConfig unset — the server-side
        # default is volc_pay, which would put the library on Volcano
        # pay-as-you-go billing without an explicit decision. A wrong personal
        # binding is visible immediately and recoverable via update; unintended
        # account billing is neither. Accounts without a personal plan must
        # pass an explicit pay_type.
        if pay_type is None and seat_id is None:
            pay_type = "agentplan_personal"
        payment = build_payment_config(pay_type, seat_id)
        # Multi-credential create format: top-level Source is omitted (each model
        # carries its source inside Credentials[]).
        body: Dict[str, Any] = {
            "Name": name,
            "Version": version,
            "VLM": self._model_block(vlm, source, DEFAULT_VLM_MODEL),
            "Embedding": self._model_block(embedding, source, DEFAULT_EMBEDDING_MODEL),
        }
        if payment is not None:
            body["PaymentConfig"] = payment
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
        pay_type: Optional[str] = None,
        seat_id: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Update a collection's mutable fields (e.g. Description, PaymentConfig).

        This is also the way to CHANGE how a library is billed (volc_pay ↔
        AgentPlan deduction, or re-bind a seat after it was unbound): pass
        pay_type / seat_id, validated by ``build_payment_config``. Omitting
        both leaves the current billing untouched.

        VLM and Embedding are sent only when explicitly supplied. This preserves
        existing multi-credential model configuration during description or billing
        updates. Passing an empty/whitespace Description is a server-side no-op.
        ``extra`` is merged verbatim for forward-compatibility."""
        payment = build_payment_config(pay_type, seat_id)
        body: Dict[str, Any] = {"ResourceID": resource_id}
        if vlm is not None:
            body["VLM"] = self._model_block(vlm, source, DEFAULT_VLM_MODEL)
        if embedding is not None:
            body["Embedding"] = self._model_block(
                embedding,
                source,
                DEFAULT_EMBEDDING_MODEL,
            )
        if payment is not None:
            body["PaymentConfig"] = payment
        if description is not None:
            body["Description"] = description
        if extra:
            body.update(extra)
        return self._request("UpdateOpenVikingCollection", body)

    def delete_collection(self, resource_id: str) -> Dict[str, Any]:
        return self._request("DeleteOpenVikingCollection", {"ResourceID": resource_id})

    def get_usage(self, resource_id: str) -> Dict[str, Any]:
        result = self._request("GetOpenVikingUsage", {"ResourceID": resource_id})
        # AgentFileNum is not meaningful here; drop it from the returned usage.
        result.pop("AgentFileNum", None)
        collection: Optional[Dict[str, Any]] = None
        try:
            collection = self.get_collection(resource_id)
        except (ControlPlaneError, requests.RequestException) as error:
            # PaymentConfig was added after the usage API. Keep usage compatible
            # with older deployments even when collection metadata is unavailable.
            logger.debug(
                "cannot load billing metadata for %s: %s",
                resource_id,
                error,
            )
        return enrich_usage_billing(result, collection)

    def get_user_access(
        self,
        resource_id: str,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        # On the data-plane cluster the api-key action is registered as
        # GetOpenVikingCollectionUserAccess (the console proxy's
        # AccessOpenVikingApiKey is NOT routed here — it 404s). Returns a
        # PLAINTEXT key: {"UserID", "Role", "ApiKey"}. With no UserID the
        # backend returns the default user.
        # (ListOpenVikingCollectionUser only returns a masked key.)
        body: Dict[str, Any] = {"ResourceID": resource_id}
        if user_id is not None:
            body["UserID"] = user_id
        return self._request("GetOpenVikingCollectionUserAccess", body)

    # --- User management (enterprise-tier libraries: multi-user) -------------
    # These require the AgentPlan key to be associated with the target library;
    # operating on an unassociated library is rejected server-side. The ApiKey in
    # a List response is MASKED — fetch the plaintext key via get_user_access.

    def list_collection_users(
        self,
        resource_id: str,
        user_id: Optional[str] = None,
        role: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
    ) -> Dict[str, Any]:
        # ListOpenVikingCollectionUser: users under the library (ApiKey masked).
        if page < 1:
            raise ValueError("page must be >= 1")
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        body: Dict[str, Any] = {
            "ResourceID": resource_id,
            "Page": page,
            "Limit": limit,
        }
        if user_id is not None:
            body["UserID"] = user_id
        if role is not None:
            body["Role"] = role
        return self._request("ListOpenVikingCollectionUser", body)

    def register_user(
        self,
        resource_id: str,
        user_id: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        # RegisterOpenVikingUser: create a regular "user" under the library.
        # The backend does not accept a Role parameter.
        body: Dict[str, Any] = {"ResourceID": resource_id, "UserID": user_id}
        if extra:
            body.update(extra)
        return self._request("RegisterOpenVikingUser", body)

    def update_user(
        self,
        resource_id: str,
        user_id: str,
        regenerate_key: bool = False,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        # UpdateOpenVikingUser only supports rotating the user's ApiKey.
        if not regenerate_key:
            raise ValueError(
                "nothing to update: regenerate_key=True is required to rotate the user's API Key"
            )
        body: Dict[str, Any] = {
            "ResourceID": resource_id,
            "UserID": user_id,
            "RegenerateKey": True,
        }
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
