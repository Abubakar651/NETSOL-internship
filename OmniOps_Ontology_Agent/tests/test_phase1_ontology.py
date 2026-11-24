"""Phase 1 unit and diagnostic tests mapped to Jira Workstream OO-3 (OO-11..OO-16)."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from omniops.ontology import (
    AnswerabilityChecker,
    AutoOntologyScanner,
    CertificationStatus,
    DatabaseEngine,
    DatabaseObject,
    DatabaseStatus,
    IncidentObject,
    OntologyRegistry,
    PullRequestObject,
    RiskLevel,
    ServiceObject,
    ServiceStatus,
    ServiceTier,
    UncertifiedOntologyError,
    UnknownOntologyEntityError,
    create_seeded_database,
)


class TestOntologySchema(unittest.TestCase):
    """P1-T1 (OO-11): Validates strict Pydantic v2 models, ID regexes, and computed metrics."""

    def test_valid_service_and_database_metrics(self) -> None:
        svc = ServiceObject(
            id="SVC-PAYMENT-GW",
            name="PaymentGatewayService",
            tier=ServiceTier.P0,
            status=ServiceStatus.CRITICAL,
            current_version="v2.5.0",
            last_stable_version="v2.4.1",
            error_rate_pct=18.4,
            p99_latency_ms=2450,
            owner_team_id="TEAM-PAYMENTS",
        )
        db = DatabaseObject(
            id="DB-ACCOUNT-LEDGER",
            name="AccountLedgerDB",
            engine=DatabaseEngine.POSTGRESQL,
            status=DatabaseStatus.HIGH_LOAD,
            active_connections=498,
            max_connections=500,
            cpu_utilization_pct=94.2,
            schema_version="v14",
        )
        self.assertEqual(svc.tier, ServiceTier.P0)
        self.assertAlmostEqual(db.connection_saturation_ratio, 0.996)
        self.assertTrue(db.is_connection_exhausted)

    def test_invalid_id_regex_and_bounds_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            ServiceObject(
                id="payment-gw",  # missing ^SVC- prefix
                name="BadService",
                tier=ServiceTier.P0,
                status=ServiceStatus.HEALTHY,
                current_version="v1.0.0",
                last_stable_version="v0.9.0",
                error_rate_pct=0.5,
                p99_latency_ms=100,
                owner_team_id="TEAM-PAYMENTS",
            )

        with self.assertRaises(ValidationError):
            PullRequestObject(
                id="PR-882",
                title="Test",
                author="dev.alex",
                target_service_id="SVC-PAYMENT-GW",
                deployed_version="v2.5.0",
                merged_at=datetime(2026, 11, 24, 17, 38, tzinfo=timezone.utc),
                changed_files=["a.py"],
                touches_db_config=True,
                touches_schema=False,
                risk_level=RiskLevel.HIGH,
                unexpected_extra_field="forbidden",
            )


class TestSeedDatabase(unittest.TestCase):
    """P1-T2 (OO-12): Verifies SQLite schema seeding, FK integrity, and Golden Incidents."""

    def setUp(self) -> None:
        self.conn = create_seeded_database()

    def tearDown(self) -> None:
        self.conn.close()

    def test_seed_row_counts_and_golden_incidents(self) -> None:
        expected_counts = {
            "raw_teams": 3,
            "raw_services": 6,
            "raw_endpoints": 6,
            "raw_databases": 3,
            "raw_service_calls": 5,
            "raw_service_databases": 5,
            "raw_pull_requests": 6,
            "raw_incidents": 3,
            "raw_wifi_telemetry": 2,
        }
        for table, expected in expected_counts.items():
            actual = self.conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            self.assertEqual(actual, expected, f"Row count mismatch on {table}")

        inc_ids = {
            row["id"]
            for row in self.conn.execute("SELECT id FROM raw_incidents").fetchall()
        }
        self.assertEqual(inc_ids, {"INC-409", "INC-512", "INC-601"})

    def test_foreign_key_enforcement_active(self) -> None:
        fk_on = self.conn.execute("PRAGMA foreign_keys").fetchone()[0]
        self.assertEqual(fk_on, 1)


class TestAutoDiscovery(unittest.TestCase):
    """P1-T3 (OO-13): Verifies Auto-Ontology introspection of SQLite tables and FKs."""

    def setUp(self) -> None:
        self.conn = create_seeded_database()
        self.scanner = AutoOntologyScanner(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_discovers_certified_and_draft_definitions(self) -> None:
        catalog = self.scanner.discover()

        self.assertEqual(
            {k for k, v in catalog.objects.items() if v.status == CertificationStatus.CERTIFIED},
            {"Team", "Service", "Endpoint", "Database", "PullRequest", "Incident"},
        )
        self.assertIn("WifiTelemetry", catalog.objects)
        self.assertEqual(catalog.objects["WifiTelemetry"].status, CertificationStatus.DRAFT)

        self.assertEqual(
            set(catalog.links.keys()),
            {"CALLS", "READS_WRITES", "EXPOSES", "OWNED_BY", "DEPLOYED_TO", "MIGRATES_SCHEMA", "AFFECTS"},
        )
        self.assertEqual(
            set(catalog.metrics.keys()),
            {"connection_saturation_ratio", "blast_radius_severity_score", "deployment_suspect_score"},
        )
        self.assertEqual(
            set(catalog.actions.keys()),
            {"TriggerSafeRollback", "ScaleDatabaseConnectionPool", "IsolateServiceTraffic", "CertifyOntologyDefinition"},
        )

    def test_manifest_export(self) -> None:
        catalog = self.scanner.discover()
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = AutoOntologyScanner.export_manifest(catalog, Path(tmpdir) / "ontology_manifest.json")
            self.assertTrue(manifest_path.is_file())
            text = manifest_path.read_text(encoding="utf-8")
            self.assertIn('"Service"', text)
            self.assertIn('"MobileAppGateway"', text)
            self.assertIn('"WifiTelemetry"', text)


class TestCertificationGate(unittest.TestCase):
    """P1-T4 (OO-14): Verifies DRAFT definitions are blocked until SME certification."""

    def setUp(self) -> None:
        self.conn = create_seeded_database()
        catalog = AutoOntologyScanner(self.conn).discover()
        self.registry = OntologyRegistry(catalog, self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_draft_object_is_blocked_until_certified(self) -> None:
        with self.assertRaises(UncertifiedOntologyError):
            self.registry.load_certified_instances("WifiTelemetry")

        with self.assertRaises(UnknownOntologyEntityError):
            self.registry.load_certified_instances("NonExistentEntity")

        audit = self.registry.certify_definition("object", "WifiTelemetry", reviewer="senior.architect")
        self.assertEqual(audit["previous_status"], "DRAFT")
        self.assertEqual(audit["new_status"], "CERTIFIED")
        self.assertEqual(len(self.registry.certification_audit_log), 1)

        wifi_rows = self.registry.load_certified_instances("WifiTelemetry")
        self.assertEqual(len(wifi_rows), 2)
        self.assertEqual(wifi_rows[0]["sensor_id"], "WIFI-FL3-01")

    def test_loads_typed_certified_objects_and_links(self) -> None:
        services = self.registry.load_certified_instances("Service")
        self.assertEqual(len(services), 6)
        self.assertTrue(all(isinstance(item, ServiceObject) for item in services))

        incidents = self.registry.load_certified_instances("Incident")
        self.assertEqual(len(incidents), 3)
        self.assertTrue(all(isinstance(item, IncidentObject) for item in incidents))

        prs = self.registry.load_certified_instances("PullRequest")
        self.assertEqual(len(prs), 6)
        self.assertTrue(all(isinstance(item, PullRequestObject) for item in prs))

        calls_links = self.registry.load_certified_links("CALLS")
        self.assertEqual(len(calls_links), 5)
        migrate_links = self.registry.load_certified_links("MIGRATES_SCHEMA")
        self.assertEqual(len(migrate_links), 1)
        self.assertEqual(migrate_links[0].source_id, "PR-879")
        self.assertEqual(migrate_links[0].target_id, "DB-ORDER-STORE")


class TestAnswerabilityChecker(unittest.TestCase):
    """P1-T5 (OO-15): Verifies pre-flight query acceptance, draft warnings, and out-of-domain rejection."""

    def setUp(self) -> None:
        self.conn = create_seeded_database()
        catalog = AutoOntologyScanner(self.conn).discover()
        self.registry = OntologyRegistry(catalog, self.conn)
        self.checker = AnswerabilityChecker(self.registry)

    def tearDown(self) -> None:
        self.conn.close()

    def test_valid_sre_query_is_answerable(self) -> None:
        report = self.checker.evaluate(
            "INC-409 is failing on PaymentGateway. Analyze the blast radius, find suspect PRs, and stage a rollback."
        )
        self.assertTrue(report.answerable)
        self.assertGreaterEqual(report.confidence, 0.85)
        self.assertIn("Incident", report.matched_object_types)
        self.assertIn("PullRequest", report.matched_object_types)
        self.assertIn("CALLS", report.matched_links)
        self.assertIn("TriggerSafeRollback", report.matched_actions)

    def test_uncertified_concept_blocked_then_allowed_after_certification(self) -> None:
        query = "What was the office Wi-Fi packet loss on Floor-3?"
        blocked = self.checker.evaluate(query)
        self.assertFalse(blocked.answerable)
        self.assertEqual(blocked.uncertified_concepts, ["WifiTelemetry"])

        self.registry.certify_definition("object", "WifiTelemetry", reviewer="platform.lead")
        allowed = self.checker.evaluate(query)
        self.assertTrue(allowed.answerable)
        self.assertIn("WifiTelemetry", allowed.matched_object_types)

    def test_out_of_domain_query_rejected(self) -> None:
        report = self.checker.evaluate("What is the weather forecast in Lahore tomorrow?")
        self.assertFalse(report.answerable)
        self.assertEqual(report.uncertified_concepts, [])
        self.assertIn("weather", report.unmodeled_concepts)
        self.assertIn("Certified ObjectTypes available", report.guidance)


if __name__ == "__main__":
    unittest.main()
