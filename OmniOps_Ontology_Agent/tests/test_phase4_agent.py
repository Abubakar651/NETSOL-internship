"""Phase 4 unit and Golden Incident agent tests mapped to Jira OO-6 (OO-28..OO-33 / OO-49..OO-60)."""

from __future__ import annotations

import asyncio
import json
import unittest

import httpx

from omniops.agent import (
    EvidenceValidationError,
    EvidenceValidator,
    InvestigationReport,
    InvestigationRunner,
    ReasoningProviders,
    Settings,
    extract_entity_ids,
    investigation_report_json_schema,
    load_settings,
    parse_env,
    redact_secrets,
)
from omniops.mcp import OmniOpsMCPServer


class TestAgentConfig(unittest.TestCase):
    """P4-T1 (OO-28 / OO-49..OO-50): Zero-leak .env loading, validation, and secret redaction."""

    def test_parse_env_and_load_settings(self) -> None:
        raw_env = (
            'GEMINI_API_KEY="AIzaTestSecret123"\n'
            "PORT=4399 # inline comment\n"
            "JIRA_PROJECT_KEY=OO\n"
            "UNRELATED_KEY=ignored\n"
        )
        parsed = parse_env(raw_env)
        self.assertEqual(parsed["GEMINI_API_KEY"], "AIzaTestSecret123")
        self.assertEqual(parsed["PORT"], "4399")
        self.assertNotIn("UNRELATED_KEY", parsed)

        settings = load_settings(parsed, load_files=False)
        self.assertEqual(settings.port, 4399)
        self.assertEqual(settings.jira_project_key, "OO")
        # repr must hide secrets
        self.assertNotIn("AIzaTestSecret123", repr(settings))

        with self.assertRaises(ValueError):
            load_settings({"PORT": "99999"}, load_files=False)

    def test_secret_redaction(self) -> None:
        settings = Settings(gemini_key="custom-secret-key-xyz", groq_key="gsk_abcdef12345")
        noisy = "Upstream failed with custom-secret-key-xyz and token gsk_abcdef12345 or sk-or-v1-xyz99"
        redacted = redact_secrets(noisy, settings)
        self.assertNotIn("custom-secret-key-xyz", redacted)
        self.assertNotIn("gsk_abcdef12345", redacted)
        self.assertNotIn("sk-or-v1-xyz99", redacted)
        self.assertIn("[redacted]", redacted)


class TestAgentPrompts(unittest.TestCase):
    """P4-T3 (OO-30 / OO-53..OO-54): Structured InvestigationReport model and strict JSON Schema."""

    def test_report_schema_and_strictness(self) -> None:
        schema = investigation_report_json_schema()
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["required"]), set(schema["properties"].keys()))

        report = InvestigationReport(
            incident_id="INC-409",
            answerable=True,
            root_cause_summary="PR-882 caused pool exhaustion on DB-ACCOUNT-LEDGER.",
            primary_failing_service_id="SVC-PAYMENT-GW",
            culprit_pull_request_id="PR-882",
            affected_downstream_resource_id="DB-ACCOUNT-LEDGER",
            upstream_blast_radius_service_ids=["SVC-CHECKOUT"],
            blast_radius_severity_score=30,
            evidence_chain=["Verified INC-409 -> SVC-PAYMENT-GW"],
            staged_branch_name="incident/INC-409-rollback",
            staged_action_type="TriggerSafeRollback",
            staged_commit_hash="abc123def456",
            human_approval_required=True,
        )
        self.assertEqual(report.incident_id, "INC-409")


class TestEvidenceValidator(unittest.TestCase):
    """P4-T4 (OO-31 / OO-55..OO-56): Anti-hallucination verification against MCP traces."""

    def setUp(self) -> None:
        self.server = OmniOpsMCPServer.from_seeded_database()
        self.server.call_tool("get_ontology_object", {"object_type": "Incident", "object_id": "INC-409"})
        self.server.call_tool("compute_blast_radius", {"service_id": "SVC-PAYMENT-GW"})
        self.server.call_tool("find_suspect_deployments", {"incident_id": "INC-409"})
        self.staged = self.server.call_tool(
            "stage_governed_action",
            {
                "action_type": "TriggerSafeRollback",
                "parameters": {
                    "service_id": "SVC-PAYMENT-GW",
                    "target_version": "v2.4.1",
                    "incident_id": "INC-409",
                    "justification": "PR-882 leak",
                },
                "branch_name": "incident/INC-409-rollback",
            },
        )["data"]
        self.traces = self.server.get_trace_log()
        self.validator = EvidenceValidator()

    def tearDown(self) -> None:
        self.server.close()

    def test_extract_and_accept_grounded_report(self) -> None:
        self.assertEqual(
            extract_entity_ids("Check SVC-PAYMENT-GW, PR-882, and DB-ACCOUNT-LEDGER."),
            {"SVC-PAYMENT-GW", "PR-882", "DB-ACCOUNT-LEDGER"},
        )
        valid_report = {
            "incident_id": "INC-409",
            "answerable": True,
            "root_cause_summary": "PR-882 exhausted DB-ACCOUNT-LEDGER under SVC-PAYMENT-GW.",
            "primary_failing_service_id": "SVC-PAYMENT-GW",
            "culprit_pull_request_id": "PR-882",
            "affected_downstream_resource_id": "DB-ACCOUNT-LEDGER",
            "upstream_blast_radius_service_ids": ["SVC-CHECKOUT", "SVC-MOBILE-GW", "SVC-WEB-STORE"],
            "blast_radius_severity_score": 30,
            "evidence_chain": ["INC-409 affects SVC-PAYMENT-GW"],
            "staged_branch_name": self.staged["branch_name"],
            "staged_action_type": self.staged["action_type"],
            "staged_commit_hash": self.staged["commit_hash"],
            "human_approval_required": True,
        }
        verified = self.validator.validate(valid_report, self.traces)
        self.assertEqual(verified.culprit_pull_request_id, "PR-882")

    def test_rejects_fabricated_structured_and_prose_ids_and_bad_commit(self) -> None:
        bad_structured = {
            "incident_id": "INC-409",
            "answerable": True,
            "root_cause_summary": "Valid summary mentioning SVC-PAYMENT-GW.",
            "primary_failing_service_id": "SVC-FAKE-999",
            "culprit_pull_request_id": "PR-882",
            "affected_downstream_resource_id": "DB-ACCOUNT-LEDGER",
            "upstream_blast_radius_service_ids": ["SVC-CHECKOUT"],
            "blast_radius_severity_score": 30,
            "evidence_chain": [],
            "staged_branch_name": self.staged["branch_name"],
            "staged_action_type": self.staged["action_type"],
            "staged_commit_hash": self.staged["commit_hash"],
            "human_approval_required": True,
        }
        with self.assertRaises(EvidenceValidationError) as ctx1:
            self.validator.validate(bad_structured, self.traces)
        self.assertIn("SVC-FAKE-999", str(ctx1.exception))

        bad_prose = {
            **bad_structured,
            "primary_failing_service_id": "SVC-PAYMENT-GW",
            "root_cause_summary": "Probably caused by PR-9999 in billing.",
        }
        with self.assertRaises(EvidenceValidationError) as ctx2:
            self.validator.validate(bad_prose, self.traces)
        self.assertIn("PR-9999", str(ctx2.exception))

        bad_commit = {
            **bad_structured,
            "primary_failing_service_id": "SVC-PAYMENT-GW",
            "staged_commit_hash": "deadbeef0000",
        }
        with self.assertRaises(EvidenceValidationError):
            self.validator.validate(bad_commit, self.traces)


class TestProviderFallback(unittest.TestCase):
    """P4-T2 (OO-29 / OO-51..OO-52): Gemini -> Groq retry/fallback -> Offline Ontology Reasoner."""

    def setUp(self) -> None:
        self.server = OmniOpsMCPServer.from_seeded_database()

    def tearDown(self) -> None:
        self.server.close()

    def test_gemini_primary_success(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content.decode("utf-8"))
            payload = json.loads(body["input"])
            report = ReasoningProviders.offline_ontology_reasoner(payload)
            return httpx.Response(
                200,
                json={
                    "status": "completed",
                    "steps": [
                        {
                            "type": "model_output",
                            "content": [{"type": "text", "text": json.dumps(report)}],
                        }
                    ],
                },
            )

        settings = Settings(gemini_key="AIzaDummyKey999")
        providers = ReasoningProviders(settings, transport=httpx.MockTransport(handler))
        runner = InvestigationRunner(self.server, settings=settings, providers=providers)
        result = asyncio.run(runner.investigate(incident_id="INC-409"))
        self.assertEqual(result.provider_used, "gemini")
        self.assertEqual(result.report.culprit_pull_request_id, "PR-882")

    def test_gemini_503_redacts_key_and_groq_corrective_retry_succeeds(self) -> None:
        groq_calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal groq_calls
            if "generativelanguage.googleapis.com" in str(request.url):
                return httpx.Response(
                    503,
                    json={"error": {"message": "Gemini overloaded for key AIzaLeakedKey777"}},
                )

            groq_calls += 1
            body = json.loads(request.content.decode("utf-8"))
            user_data = json.loads(body["messages"][1]["content"])
            evidence = user_data.get("evidence", user_data)
            report = ReasoningProviders.offline_ontology_reasoner(evidence)
            if groq_calls == 1:
                # Inject hallucinated ID on attempt 1; validator should catch and trigger retry!
                report["root_cause_summary"] = "Hallucinated SVC-GHOST-1 caused this outage."
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {"finish_reason": "stop", "message": {"content": json.dumps(report)}}
                    ]
                },
            )

        settings = Settings(gemini_key="AIzaLeakedKey777", groq_key="gsk_DummyGroqKey")
        providers = ReasoningProviders(settings, transport=httpx.MockTransport(handler))
        runner = InvestigationRunner(self.server, settings=settings, providers=providers)
        result = asyncio.run(runner.investigate(incident_id="INC-409"))

        self.assertEqual(result.provider_used, "groq")
        self.assertEqual(groq_calls, 2)
        self.assertEqual(result.report.culprit_pull_request_id, "PR-882")
        serialized_diag = json.dumps(result.diagnostic_events)
        self.assertNotIn("AIzaLeakedKey777", serialized_diag)
        self.assertIn("[redacted]", serialized_diag)

    def test_all_cloud_providers_fail_falls_back_to_offline(self) -> None:
        def failing_handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, json={"error": {"message": "Service unavailable"}})

        settings = Settings(
            gemini_key="AIzaFake",
            groq_key="gsk_Fake",
            openrouter_key="sk-or-v1-Fake",
        )
        providers = ReasoningProviders(settings, transport=httpx.MockTransport(failing_handler))
        runner = InvestigationRunner(self.server, settings=settings, providers=providers)
        result = asyncio.run(runner.investigate(incident_id="INC-409"))

        self.assertEqual(result.provider_used, "offline_ontology_reasoner")
        self.assertEqual(result.report.culprit_pull_request_id, "PR-882")
        self.assertEqual(len(result.diagnostic_events), 3)


class TestInvestigationRunner(unittest.TestCase):
    """P4-T5 & P4-T6 (OO-32..OO-33 / OO-57..OO-60): Golden Benchmarks & Gate Tests."""

    def setUp(self) -> None:
        self.server = OmniOpsMCPServer.from_seeded_database()
        self.runner = InvestigationRunner(self.server, settings=Settings())

    def tearDown(self) -> None:
        self.server.close()

    def test_golden_incident_benchmarks_offline_mode(self) -> None:
        inc_409 = self.runner.investigate_sync(incident_id="INC-409", prefer_offline=True)
        self.assertTrue(inc_409.report.answerable)
        self.assertEqual(inc_409.provider_used, "offline_ontology_reasoner")
        self.assertEqual(inc_409.report.primary_failing_service_id, "SVC-PAYMENT-GW")
        self.assertEqual(inc_409.report.culprit_pull_request_id, "PR-882")
        self.assertEqual(inc_409.report.affected_downstream_resource_id, "DB-ACCOUNT-LEDGER")
        self.assertEqual(inc_409.report.blast_radius_severity_score, 30)
        self.assertEqual(inc_409.report.staged_branch_name, "incident/INC-409-rollback")
        self.assertEqual(inc_409.report.staged_action_type, "TriggerSafeRollback")
        self.assertTrue(inc_409.report.human_approval_required)

        inc_512 = self.runner.investigate_sync(incident_id="INC-512", prefer_offline=True)
        self.assertEqual(inc_512.report.primary_failing_service_id, "SVC-FRAUD-ENGINE")
        self.assertEqual(inc_512.report.culprit_pull_request_id, "PR-879")
        self.assertEqual(inc_512.report.affected_downstream_resource_id, "DB-ORDER-STORE")
        self.assertEqual(inc_512.report.blast_radius_severity_score, 40)

        inc_601 = self.runner.investigate_sync(incident_id="INC-601", prefer_offline=True)
        self.assertEqual(inc_601.report.primary_failing_service_id, "SVC-MOBILE-GW")
        self.assertEqual(inc_601.report.culprit_pull_request_id, "PR-885")
        self.assertEqual(inc_601.report.affected_downstream_resource_id, "DB-SESSION-REDIS")

    def test_nl_resolution_and_idempotent_branch_naming(self) -> None:
        first = self.runner.investigate_sync(
            "PaymentGateway is returning 500 errors. Analyze the blast radius and propose a fix.",
            prefer_offline=True,
        )
        second = self.runner.investigate_sync(
            "Re-analyze INC-409 and stage another branch.",
            prefer_offline=True,
        )
        self.assertEqual(first.report.incident_id, "INC-409")
        self.assertEqual(first.report.staged_branch_name, "incident/INC-409-rollback")
        self.assertEqual(second.report.staged_branch_name, "incident/INC-409-rollback-2")
        # main production branch remains untouched until human approval
        self.assertEqual(
            self.server.branch_manager.get_engine("main").get_raw_object("Service", "SVC-PAYMENT-GW")[
                "status"
            ],
            "CRITICAL",
        )

    def test_unanswerable_and_uncertified_queries_short_circuit(self) -> None:
        weather = self.runner.investigate_sync("What is the weather in Lahore today?")
        self.assertFalse(weather.report.answerable)
        self.assertEqual(weather.provider_used, "answerability_gate")
        self.assertEqual(weather.report.staged_branch_name, "")

        wifi = self.runner.investigate_sync("Check Floor-3 Wi-Fi packet loss.")
        self.assertFalse(wifi.report.answerable)
        self.assertEqual(wifi.answerability.uncertified_concepts, ["WifiTelemetry"])
        self.assertEqual(wifi.provider_used, "answerability_gate")


if __name__ == "__main__":
    unittest.main()
