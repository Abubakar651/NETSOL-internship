"""Phase 5 full-stack FastAPI & E2E tests mapped to Jira OO-7 (OO-34..OO-38 / OO-61..OO-70)."""

from __future__ import annotations

import asyncio
import unittest

import httpx

from omniops.agent import Settings
from omniops.app import create_app


class TestFastAPIBackend(unittest.TestCase):
    """P5-T1 (OO-34 / OO-61..OO-62): Validates config, schema, topology, blast radius, and /api/mcp."""

    def setUp(self) -> None:
        self.app = create_app(settings=Settings())

    def test_config_schema_topology_and_mcp_jsonrpc(self) -> None:
        async def scenario() -> None:
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                cfg = await client.get("/api/config")
                self.assertEqual(cfg.status_code, 200)
                cfg_json = cfg.json()
                self.assertEqual(cfg_json["jira_project_key"], "OO")
                self.assertTrue(cfg_json["providers"]["offline_reasoner"])
                self.assertNotIn("gemini_key", cfg_json)

                topo = await client.get("/api/topology")
                self.assertEqual(topo.status_code, 200)
                self.assertEqual(len(topo.json()["nodes"]), 18)
                self.assertEqual(topo.json()["kpis"]["open_incidents"], 3)

                br = await client.get("/api/blast-radius/SVC-PAYMENT-GW")
                self.assertEqual(br.status_code, 200)
                self.assertEqual(br.json()["blast_radius_severity_score"], 30)

                mcp = await client.post(
                    "/api/mcp",
                    json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                )
                self.assertEqual(mcp.status_code, 200)
                self.assertEqual(len(mcp.json()["result"]["tools"]), 7)

        asyncio.run(scenario())


class TestWebAssetsServed(unittest.TestCase):
    """P5-T2 (OO-35 / OO-63..OO-64): Validates Apple Liquid Glass UI & 60% squircle assets."""

    def setUp(self) -> None:
        self.app = create_app(settings=Settings())

    def test_html_css_js_served_with_apple_glass_and_squircle(self) -> None:
        async def scenario() -> None:
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                html_res = await client.get("/")
                self.assertEqual(html_res.status_code, 200)
                self.assertIn("OmniOps Ontology Agent", html_res.text)
                self.assertIn("Approval Inbox", html_res.text)

                css_res = await client.get("/styles.css")
                self.assertEqual(css_res.status_code, 200)
                self.assertIn("corner-shape: squircle", css_res.text)
                self.assertIn("backdrop-filter: blur(24px)", css_res.text)

                js_res = await client.get("/app.js")
                self.assertEqual(js_res.status_code, 200)
                self.assertIn("appleSquirclePath", js_res.text)
                self.assertIn("1.528665", js_res.text)

        asyncio.run(scenario())


class TestInvestigationFlowAPI(unittest.TestCase):
    """P5-T3 (OO-36 / OO-65..OO-66): Validates /api/investigate and /api/ontology/certify."""

    def setUp(self) -> None:
        self.app = create_app(settings=Settings())

    def test_investigate_and_draft_certification_flow(self) -> None:
        async def scenario() -> None:
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                # 1. Uncertified Wi-Fi query blocked by Answerability Gate
                wifi_blocked = await client.post(
                    "/api/investigate",
                    json={"question": "Check office Wi-Fi packet loss on Floor-3."},
                )
                self.assertEqual(wifi_blocked.status_code, 200)
                self.assertFalse(wifi_blocked.json()["report"]["answerable"])
                self.assertEqual(wifi_blocked.json()["answerability"]["uncertified_concepts"], ["WifiTelemetry"])

                # 2. SME promotes WifiTelemetry via /api/ontology/certify
                cert = await client.post(
                    "/api/ontology/certify",
                    json={"entity_kind": "object", "entity_name": "WifiTelemetry", "reviewer": "senior.architect"},
                )
                self.assertEqual(cert.status_code, 200)
                self.assertEqual(cert.json()["audit_entry"]["new_status"], "CERTIFIED")
                self.assertEqual(cert.json()["schema"]["draft_objects"], {})

                # 3. INC-409 investigation succeeds & stages Omnigraph branch
                inc = await client.post(
                    "/api/investigate",
                    json={"incident_id": "INC-409", "prefer_offline": True},
                )
                self.assertEqual(inc.status_code, 200)
                data = inc.json()
                self.assertTrue(data["report"]["answerable"])
                self.assertEqual(data["report"]["culprit_pull_request_id"], "PR-882")
                self.assertEqual(data["report"]["staged_branch_name"], "incident/INC-409-rollback")
                self.assertGreaterEqual(len(data["tool_trace"]), 5)

        asyncio.run(scenario())


class TestBranchApprovalE2E(unittest.TestCase):
    """P5-T4 & P5-T5 (OO-37..OO-38 / OO-67..OO-70): Full E2E investigation -> approval -> recovery -> reset."""

    def setUp(self) -> None:
        self.app = create_app(settings=Settings())

    def test_full_e2e_investigation_merge_recovery_and_reset(self) -> None:
        async def scenario() -> None:
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                # 1. Investigate INC-409
                inv = await client.post(
                    "/api/investigate",
                    json={"incident_id": "INC-409", "prefer_offline": True},
                )
                self.assertEqual(inv.status_code, 200)

                # 2. Verify pending branch appears in /api/branches with 3-way diff
                branches = (await client.get("/api/branches")).json()["branches"]
                staged = next(b for b in branches if b["branch_name"] == "incident/INC-409-rollback")
                self.assertEqual(staged["status"], "ACTIVE")
                self.assertTrue(staged["three_way_diff"]["can_merge"])

                # 3. HumanSRE approves & merges branch to main
                approved = await client.post(
                    "/api/branches/approve",
                    json={
                        "branch_name": "incident/INC-409-rollback",
                        "approver": "senior.sre@netsol.example",
                        "approval_note": "Confirmed PR-882 leak; approved rollback",
                    },
                )
                self.assertEqual(approved.status_code, 200)
                topo_after = approved.json()["topology"]
                payment_node = next(n for n in topo_after["nodes"] if n["id"] == "SVC-PAYMENT-GW")
                self.assertEqual(payment_node["data"]["status"], "HEALTHY")
                self.assertEqual(payment_node["data"]["current_version"], "v2.4.1")
                self.assertEqual(topo_after["kpis"]["pending_branches"], 0)

                # 4. Reset demo restores CRITICAL v2.5.0 state
                reset_res = await client.post("/api/reset")
                self.assertEqual(reset_res.status_code, 200)
                topo_reset = reset_res.json()["topology"]
                payment_reset = next(n for n in topo_reset["nodes"] if n["id"] == "SVC-PAYMENT-GW")
                self.assertEqual(payment_reset["data"]["status"], "CRITICAL")
                self.assertEqual(payment_reset["data"]["current_version"], "v2.5.0")

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
