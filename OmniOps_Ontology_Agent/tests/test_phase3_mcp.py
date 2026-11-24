"""Phase 3 MCP protocol compliance tests mapped to Jira Workstream OO-5 (OO-23..OO-27)."""

from __future__ import annotations

import io
import json
import unittest

from omniops.mcp import (
    OmniOpsMCPServer,
    ResourceNotFoundError,
    ToolInputError,
    UnknownPromptError,
    UnknownToolError,
)


class TestMCPResources(unittest.TestCase):
    """P3-T1 (OO-23): Verifies static URIs, dynamic branch diff URI templates, and error handling."""

    def setUp(self) -> None:
        self.server = OmniOpsMCPServer.from_seeded_database()

    def tearDown(self) -> None:
        self.server.close()

    def test_static_resources_and_schema_reads(self) -> None:
        resources = self.server.list_resources()
        uris = {r["uri"] for r in resources}
        self.assertEqual(
            uris,
            {
                "ontology://schema/certified",
                "ontology://schema/drafts",
                "ontology://topology/live",
                "ontology://branches/list",
                "ontology://audit/commits",
            },
        )
        templates = self.server.list_resource_templates()
        self.assertEqual(templates[0]["uriTemplate"], "ontology://branches/{branch_name}/diff")

        certified = self.server.read_resource("ontology://schema/certified")["data"]
        self.assertEqual(len(certified["objects"]), 6)
        self.assertEqual(len(certified["links"]), 7)

        drafts = self.server.read_resource("ontology://schema/drafts")["data"]
        self.assertIn("WifiTelemetry", drafts["draft_objects"])

        topology = self.server.read_resource("ontology://topology/live")["data"]
        self.assertEqual(len(topology["nodes"]), 18)

    def test_dynamic_branch_diff_uri_and_missing_uri(self) -> None:
        self.server.call_tool(
            "stage_governed_action",
            {
                "action_type": "TriggerSafeRollback",
                "parameters": {
                    "service_id": "SVC-PAYMENT-GW",
                    "target_version": "v2.4.1",
                    "incident_id": "INC-409",
                    "justification": "PR-882 connection leak",
                },
                "branch_name": "incident/INC-409-rollback",
            },
        )
        diff = self.server.read_resource("ontology://branches/incident/INC-409-rollback/diff")["data"]
        self.assertTrue(diff["can_merge"])
        self.assertGreaterEqual(len(diff["changes"]), 2)

        with self.assertRaises(ResourceNotFoundError):
            self.server.read_resource("ontology://unknown/path")
        with self.assertRaises(ResourceNotFoundError):
            self.server.read_resource("ontology://branches/incident/does-not-exist/diff")


class TestMCPTools(unittest.TestCase):
    """P3-T2 (OO-24): Verifies all 7 MCP tools, schema validation, Cedar policy errors, and traces."""

    def setUp(self) -> None:
        self.server = OmniOpsMCPServer.from_seeded_database()

    def tearDown(self) -> None:
        self.server.close()

    def test_tool_catalog_and_investigation_pipeline(self) -> None:
        tools = self.server.list_tools()
        self.assertEqual(
            {t["name"] for t in tools},
            {
                "check_question_answerability",
                "get_ontology_object",
                "search_ontology_objects",
                "compute_blast_radius",
                "find_suspect_deployments",
                "stage_governed_action",
                "approve_and_merge_branch",
            },
        )

        ans = self.server.call_tool(
            "check_question_answerability",
            {"question": "Analyze INC-409 blast radius and culprit PR"},
        )
        self.assertFalse(ans["isError"])
        self.assertTrue(ans["data"]["answerable"])

        inc = self.server.call_tool(
            "get_ontology_object", {"object_type": "Incident", "object_id": "INC-409"}
        )
        self.assertEqual(inc["data"]["affected_service_id"], "SVC-PAYMENT-GW")

        critical = self.server.call_tool(
            "search_ontology_objects",
            {"object_type": "Service", "filters": {"status": "CRITICAL"}},
        )
        self.assertEqual(critical["data"]["count"], 1)

        br = self.server.call_tool("compute_blast_radius", {"service_id": "SVC-PAYMENT-GW"})
        self.assertEqual(br["data"]["blast_radius_severity_score"], 30)

        suspects = self.server.call_tool("find_suspect_deployments", {"incident_id": "INC-409"})
        self.assertEqual(suspects["data"]["top_suspect_pr_id"], "PR-882")

        # Agent blocked on main -> isError=True
        blocked = self.server.call_tool(
            "stage_governed_action",
            {
                "action_type": "TriggerSafeRollback",
                "parameters": {
                    "service_id": "SVC-PAYMENT-GW",
                    "target_version": "v2.4.1",
                    "incident_id": "INC-409",
                    "justification": "Direct main attempt",
                },
                "branch_name": "main",
            },
        )
        self.assertTrue(blocked["isError"])
        self.assertEqual(blocked["data"]["error_type"], "PolicyViolationError")

        # Staged cleanly on incident/* branch
        staged = self.server.call_tool(
            "stage_governed_action",
            {
                "action_type": "TriggerSafeRollback",
                "parameters": {
                    "service_id": "SVC-PAYMENT-GW",
                    "target_version": "v2.4.1",
                    "incident_id": "INC-409",
                    "justification": "PR-882 connection leak",
                },
                "branch_name": "incident/INC-409-rollback",
            },
        )
        self.assertFalse(staged["isError"])

        merged = self.server.call_tool(
            "approve_and_merge_branch",
            {"branch_name": "incident/INC-409-rollback", "approver": "senior.sre"},
        )
        self.assertFalse(merged["isError"])

        trace = self.server.get_trace_log()
        self.assertEqual(len(trace), 8)
        self.assertTrue(all(item.latency_ms >= 0.0 for item in trace))
        self.assertEqual(trace[5].status, "ERROR")

    def test_unknown_tool_and_invalid_args(self) -> None:
        with self.assertRaises(UnknownToolError):
            self.server.call_tool("does_not_exist", {})
        with self.assertRaises(ToolInputError):
            self.server.call_tool("compute_blast_radius", {})


class TestMCPPrompts(unittest.TestCase):
    """P3-T3 (OO-25): Verifies MCP SRE and PR Risk Gate prompt templates."""

    def setUp(self) -> None:
        self.server = OmniOpsMCPServer.from_seeded_database()

    def tearDown(self) -> None:
        self.server.close()

    def test_prompt_listing_and_rendering(self) -> None:
        prompts = self.server.list_prompts()
        self.assertEqual(
            {p["name"] for p in prompts},
            {"sre_root_cause_runbook", "pr_blast_radius_gate"},
        )
        rca_prompt = self.server.get_prompt("sre_root_cause_runbook", {"incident_id": "INC-409"})
        self.assertIn("INC-409", rca_prompt["messages"][0]["content"]["text"])

        pr_prompt = self.server.get_prompt("pr_blast_radius_gate", {"pr_id": "PR-882"})
        self.assertIn("PR-882", pr_prompt["messages"][0]["content"]["text"])

        with self.assertRaises(ValueError):
            self.server.get_prompt("sre_root_cause_runbook", {})
        with self.assertRaises(UnknownPromptError):
            self.server.get_prompt("unknown_prompt", {})


class TestMCPServerJSONRPC(unittest.TestCase):
    """P3-T4 (OO-26): Verifies JSON-RPC 2.0 dispatch, error codes, and stdio loop."""

    def setUp(self) -> None:
        self.server = OmniOpsMCPServer.from_seeded_database()

    def tearDown(self) -> None:
        self.server.close()

    def test_jsonrpc_lifecycle_and_errors(self) -> None:
        init = self.server.handle_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        self.assertEqual(init["result"]["serverInfo"]["name"], "omniops-ontology-mcp")

        notif = self.server.handle_jsonrpc({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.assertIsNone(notif)

        tools_resp = self.server.handle_jsonrpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        self.assertEqual(len(tools_resp["result"]["tools"]), 7)

        call_resp = self.server.handle_jsonrpc(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "compute_blast_radius", "arguments": {"service_id": "SVC-PAYMENT-GW"}},
            }
        )
        self.assertFalse(call_resp["result"]["isError"])
        payload = json.loads(call_resp["result"]["content"][0]["text"])
        self.assertEqual(payload["blast_radius_severity_score"], 30)

        bad_method = self.server.handle_jsonrpc({"jsonrpc": "2.0", "id": 4, "method": "unknown/method"})
        self.assertEqual(bad_method["error"]["code"], -32601)

        bad_params = self.server.handle_jsonrpc(
            {"jsonrpc": "2.0", "id": 5, "method": "resources/read", "params": {"uri": "ontology://missing"}}
        )
        self.assertEqual(bad_params["error"]["code"], -32602)

    def test_stdio_transport_loop(self) -> None:
        requests = "\n".join(
            [
                json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}),
                json.dumps({"jsonrpc": "2.0", "id": 2, "method": "resources/list"}),
                "{invalid-json",
            ]
        ) + "\n"
        stdin = io.StringIO(requests)
        stdout = io.StringIO()
        self.server.serve_stdio(stdin=stdin, stdout=stdout)

        lines = [json.loads(line) for line in stdout.getvalue().strip().splitlines()]
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[0]["result"], {})
        self.assertEqual(len(lines[1]["result"]["resources"]), 5)
        self.assertEqual(lines[2]["error"]["code"], -32700)


if __name__ == "__main__":
    unittest.main()
