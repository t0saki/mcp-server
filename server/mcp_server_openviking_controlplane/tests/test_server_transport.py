"""Transport wiring: stateless streamable HTTP."""

import importlib
import os
import sys
import unittest
from unittest.mock import patch

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

if __name__ == "__main__":
    unittest.main()
