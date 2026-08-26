"""Transport wiring: stateless streamable HTTP and per-request credentials."""

import importlib
import os
import sys
import unittest
from unittest.mock import Mock, patch

from starlette.datastructures import Headers

from mcp_server_openviking_controlplane import server


def _reload_server(**env):
    """Reload the server module with ``env`` applied, returning the fresh module."""
    with patch.dict(os.environ, env, clear=False):
        return importlib.reload(server)


class TransportDefaultsTest(unittest.TestCase):
    """The settings the gateway depends on, asserted directly."""

    def test_stateless_http_is_on_by_default(self):
        self.assertTrue(server.mcp.settings.stateless_http)

    def test_binds_all_interfaces_so_dns_rebinding_protection_stays_off(self):
        # FastMCP auto-enables a localhost-only Host allowlist when host is
        # 127.0.0.1/localhost/::1, which would reject every gateway-forwarded
        # request. Binding 0.0.0.0 is what keeps transport_security unset.
        self.assertEqual(server.mcp.settings.host, "0.0.0.0")
        self.assertIsNone(server.mcp.settings.transport_security)

    def test_streamable_http_is_mounted_at_mcp(self):
        self.assertEqual(server.mcp.settings.streamable_http_path, "/mcp")


class TransportSelectionTest(unittest.TestCase):
    """``main()`` must hand FastMCP a transport string the SDK actually accepts."""

    def _run_main(self, argv):
        with patch.object(server.mcp, "run") as run:
            with patch.object(sys, "argv", ["mcp-server-openviking-controlplane"] + argv):
                server.main()
        return run

    def test_defaults_to_stdio(self):
        self.assertEqual(self._run_main([]).call_args.kwargs["transport"], "stdio")

    def test_accepts_every_transport_the_sdk_supports(self):
        for transport in ("stdio", "sse", "streamable-http"):
            with self.subTest(transport=transport):
                run = self._run_main(["--transport", transport])
                self.assertEqual(run.call_args.kwargs["transport"], transport)

    def test_rejects_the_underscore_spelling(self):
        # FastMCP.run types transport as Literal["stdio", "sse", "streamable-http"],
        # so the underscore form would be a runtime ValueError deep inside the SDK.
        # argparse must reject it first.
        with patch.object(server.mcp, "run"):
            with patch.object(sys, "argv", ["x", "--transport", "streamable_http"]):
                with self.assertRaises(SystemExit):
                    with patch.object(sys, "stderr"):
                        server.main()


class StatelessEnvOverrideTest(unittest.TestCase):
    """Both spellings of the opt-out are honoured; the repo's typo wins."""

    def tearDown(self):
        # Restore the module built from a clean environment for the rest of the suite.
        for name in ("STATLESS_HTTP", "STATELESS_HTTP"):
            os.environ.pop(name, None)
        importlib.reload(server)

    def test_repo_standard_typo_disables_it(self):
        self.assertFalse(_reload_server(STATLESS_HTTP="false").mcp.settings.stateless_http)

    def test_correct_spelling_also_disables_it(self):
        self.assertFalse(_reload_server(STATELESS_HTTP="false").mcp.settings.stateless_http)

    def test_typo_takes_precedence_when_both_are_set(self):
        module = _reload_server(STATLESS_HTTP="true", STATELESS_HTTP="false")
        self.assertTrue(module.mcp.settings.stateless_http)

    def test_empty_port_falls_back_instead_of_crashing(self):
        # `int(os.getenv("MCP_SERVER_PORT", ...))` would raise on an exported-but-empty
        # variable and kill the process at import time.
        self.assertEqual(_reload_server(MCP_SERVER_PORT="").mcp.settings.port, 8000)


class RequestCredentialTest(unittest.TestCase):
    """The credential is resolved per request, not once per process."""

    def _with_headers(self, headers):
        context = Mock()
        context.request_context.request.headers = Headers(headers)
        return patch.object(server.mcp, "get_context", return_value=context)

    def test_dedicated_header_is_used_verbatim(self):
        with self._with_headers({"X-AgentPlan-Api-Key": "ark-caller"}):
            self.assertEqual(server._request_api_key(), "ark-caller")

    def test_bearer_scheme_is_stripped(self):
        with self._with_headers({"Authorization": "Bearer ark-caller"}):
            self.assertEqual(server._request_api_key(), "ark-caller")

    def test_dedicated_header_beats_authorization(self):
        with self._with_headers(
            {"X-AgentPlan-Api-Key": "ark-dedicated", "Authorization": "Bearer ark-auth"}
        ):
            self.assertEqual(server._request_api_key(), "ark-dedicated")

    def test_non_bearer_authorization_is_ignored(self):
        # A gateway terminating its own auth may put an unrelated credential here.
        # Using it as an Ark key would stamp it into the caller's collection.
        for value in ("Basic dXNlcjpwYXNz", "opaque-gateway-token", "Bearer "):
            with self.subTest(value=value):
                with self._with_headers({"Authorization": value}):
                    self.assertIsNone(server._request_api_key())

    def test_no_http_request_means_no_request_key(self):
        # stdio: get_context() raises outside a request, and .request is None inside one.
        with patch.object(server.mcp, "get_context", side_effect=ValueError):
            self.assertIsNone(server._request_api_key())

        context = Mock()
        context.request_context.request = None
        with patch.object(server.mcp, "get_context", return_value=context):
            self.assertIsNone(server._request_api_key())

    def test_consecutive_requests_do_not_share_a_credential(self):
        with patch.dict(os.environ, {"AGENTPLAN_API_KEY": "ark-env"}, clear=False):
            with self._with_headers({"X-AgentPlan-Api-Key": "ark-first"}):
                first = server.get_client()
            with self._with_headers({"X-AgentPlan-Api-Key": "ark-second"}):
                second = server.get_client()
            with patch.object(server.mcp, "get_context", side_effect=ValueError):
                fallback = server.get_client()

        self.assertEqual(first.config.api_key, "ark-first")
        self.assertEqual(second.config.api_key, "ark-second")
        self.assertEqual(fallback.config.api_key, "ark-env")


if __name__ == "__main__":
    unittest.main()
