"""Phase 2 unit and governance tests mapped to Jira Workstream OO-4 (OO-17..OO-22)."""

from __future__ import annotations

import unittest

from omniops.graph import (
    ActionPreconditionError,
    CedarPolicyEvaluator,
    KineticActionExecutor,
    MergeConflictError,
    ObjectNotFoundError,
    OmnigraphBranchManager,
    PolicyViolationError,
    SemanticGraphEngine,
    compute_blast_radius,
    correlate_suspect_deployments,
)
from omniops.ontology import (
    AutoOntologyScanner,
    OntologyLink,
    OntologyRegistry,
    create_seeded_database,
)


def _build_phase2_fixtures():
    conn = create_seeded_database()
    catalog = AutoOntologyScanner(conn).discover()
    registry = OntologyRegistry(catalog, conn)
    engine = SemanticGraphEngine.from_registry(registry)
    return conn, engine


class TestGraphEngine(unittest.TestCase):
    """P2-T1 (OO-17): Verifies typed graph queries, hybrid search, neighbors, and topology export."""

    def setUp(self) -> None:
        self.conn, self.engine = _build_phase2_fixtures()

    def tearDown(self) -> None:
        self.conn.close()

    def test_get_object_and_not_found(self) -> None:
        svc = self.engine.get_object("Service", "SVC-PAYMENT-GW")
        self.assertEqual(svc["name"], "PaymentGatewayService")
        self.assertEqual(svc["tier"], "P0")
        self.assertGreaterEqual(len(svc["inbound_links"]), 1)
        self.assertGreaterEqual(len(svc["outbound_links"]), 1)

        with self.assertRaises(ObjectNotFoundError):
            self.engine.get_object("Service", "SVC-NON-EXISTENT")

    def test_hybrid_search_and_topology_export(self) -> None:
        p0_critical = self.engine.search_objects(
            "Service", filters={"tier": "P0", "status": "CRITICAL"}
        )
        self.assertEqual([s["id"] for s in p0_critical], ["SVC-PAYMENT-GW"])

        pool_prs = self.engine.search_objects("PullRequest", keyword="connection pool")
        self.assertEqual([p["id"] for p in pool_prs], ["PR-882"])

        topology = self.engine.export_topology()
        self.assertEqual(len(topology["nodes"]), 18)  # 6 services + 3 dbs + 6 PRs + 3 incidents
        self.assertGreaterEqual(len(topology["edges"]), 19)


class TestBlastRadius(unittest.TestCase):
    """P2-T2 (OO-18): Verifies multi-hop upstream blast radius, severity score, and cycle safety."""

    def setUp(self) -> None:
        self.conn, self.engine = _build_phase2_fixtures()

    def tearDown(self) -> None:
        self.conn.close()

    def test_payment_gateway_blast_radius(self) -> None:
        report = compute_blast_radius(self.engine, "SVC-PAYMENT-GW", max_depth=4)
        self.assertFalse(report.cycle_detected)
        self.assertEqual(report.blast_radius_severity_score, 30)
        self.assertEqual(
            [c.service_id for c in report.impacted_upstream_services],
            ["SVC-CHECKOUT", "SVC-MOBILE-GW", "SVC-WEB-STORE"],
        )
        self.assertEqual(report.impacted_upstream_services[0].hop_distance, 1)
        self.assertEqual(
            report.impacted_upstream_services[1].dependency_path,
            ["SVC-MOBILE-GW", "SVC-CHECKOUT", "SVC-PAYMENT-GW"],
        )
        db_deps = [d for d in report.downstream_dependencies if d.object_type == "Database"]
        self.assertEqual(len(db_deps), 1)
        self.assertEqual(db_deps[0].object_id, "DB-ACCOUNT-LEDGER")
        self.assertTrue(db_deps[0].details["is_connection_exhausted"])

    def test_fraud_engine_three_hop_blast_radius(self) -> None:
        report = compute_blast_radius(self.engine, "SVC-FRAUD-ENGINE", max_depth=4)
        self.assertEqual(report.blast_radius_severity_score, 40)
        self.assertEqual(
            [c.service_id for c in report.impacted_upstream_services],
            ["SVC-PAYMENT-GW", "SVC-CHECKOUT", "SVC-MOBILE-GW", "SVC-WEB-STORE"],
        )

    def test_cycle_safe_traversal(self) -> None:
        # Inject synthetic reverse cycle: SVC-PAYMENT-GW -> SVC-MOBILE-GW
        cycled_snap = self.engine.snapshot.clone()
        cycled_snap.links.append(
            OntologyLink(
                link_type="CALLS",
                source_id="SVC-PAYMENT-GW",
                target_id="SVC-MOBILE-GW",
                properties={"call_type": "GRPC", "rpm": 50, "hard_dependency": True},
            )
        )
        cycled_engine = SemanticGraphEngine(cycled_snap)
        report = compute_blast_radius(cycled_engine, "SVC-PAYMENT-GW", max_depth=6)
        self.assertTrue(report.cycle_detected)
        self.assertEqual(len(report.impacted_upstream_services), 3)


class TestDeploymentCorrelation(unittest.TestCase):
    """P2-T3 (OO-19): Verifies causal PR correlation across all 3 Golden Incidents."""

    def setUp(self) -> None:
        self.conn, self.engine = _build_phase2_fixtures()

    def tearDown(self) -> None:
        self.conn.close()

    def test_golden_incident_culprit_rankings(self) -> None:
        inc_409 = correlate_suspect_deployments(self.engine, "INC-409", lookback_minutes=120)
        self.assertEqual(inc_409.top_suspect_pr_id, "PR-882")
        self.assertEqual(inc_409.suspect_deployments[0].recommended_rollback_version, "v2.4.1")

        inc_512 = correlate_suspect_deployments(self.engine, "INC-512", lookback_minutes=120)
        self.assertEqual(inc_512.top_suspect_pr_id, "PR-879")
        self.assertEqual(inc_512.suspect_deployments[0].migrates_database_id, "DB-ORDER-STORE")

        inc_601 = correlate_suspect_deployments(self.engine, "INC-601", lookback_minutes=120)
        self.assertEqual(inc_601.top_suspect_pr_id, "PR-885")
        # PR-875 (4h old) must be excluded by 120-minute window
        self.assertNotIn("PR-875", [s.pr_id for s in inc_601.suspect_deployments])


class TestOmnigraphBranching(unittest.TestCase):
    """P2-T4 (OO-20): Verifies branch isolation, 3-way diff, merge audit, and conflict detection."""

    def setUp(self) -> None:
        self.conn, self.engine = _build_phase2_fixtures()
        self.bm = OmnigraphBranchManager(self.engine.snapshot)

    def tearDown(self) -> None:
        self.conn.close()

    def test_branch_isolation_and_merge(self) -> None:
        self.bm.create_branch("incident/INC-409-test", author="agent")

        def mutate_version(snap):
            snap.objects["Service"]["SVC-PAYMENT-GW"]["current_version"] = "v2.4.1"

        self.bm.commit_mutation(
            "incident/INC-409-test",
            mutate_version,
            author="agent",
            actor_role="AutonomousAgent",
            action_type="TriggerSafeRollback",
            summary="Rollback PaymentGateway to v2.4.1",
        )

        # main stays untouched while feature branch reflects change
        self.assertEqual(
            self.bm.get_engine("main").get_raw_object("Service", "SVC-PAYMENT-GW")["current_version"],
            "v2.5.0",
        )
        self.assertEqual(
            self.bm.get_engine("incident/INC-409-test").get_raw_object("Service", "SVC-PAYMENT-GW")["current_version"],
            "v2.4.1",
        )

        diff_report = self.bm.compute_three_way_diff("incident/INC-409-test")
        self.assertTrue(diff_report.can_merge)
        self.assertEqual(len(diff_report.changes), 1)

        merge_commit = self.bm.merge_branch("incident/INC-409-test", approver="sre.lead")
        self.assertEqual(merge_commit.action_type, "MergeBranchToMain")
        self.assertEqual(
            self.bm.get_engine("main").get_raw_object("Service", "SVC-PAYMENT-GW")["current_version"],
            "v2.4.1",
        )

    def test_three_way_conflict_detection(self) -> None:
        self.bm.create_branch("incident/conflict-branch", author="agent")
        self.bm.commit_mutation(
            "incident/conflict-branch",
            lambda snap: snap.objects["Service"]["SVC-PAYMENT-GW"].__setitem__("current_version", "v2.4.1"),
            author="agent",
            actor_role="AutonomousAgent",
            action_type="TriggerSafeRollback",
            summary="Propose v2.4.1",
        )
        self.bm.commit_mutation(
            "main",
            lambda snap: snap.objects["Service"]["SVC-PAYMENT-GW"].__setitem__("current_version", "v2.5.1-hotfix"),
            author="human",
            actor_role="HumanSRE",
            action_type="Hotfix",
            summary="Manual hotfix on main",
        )
        diff = self.bm.compute_three_way_diff("incident/conflict-branch")
        self.assertFalse(diff.can_merge)
        self.assertEqual(len(diff.conflicts), 1)
        with self.assertRaises(MergeConflictError):
            self.bm.merge_branch("incident/conflict-branch", approver="sre.lead")

    def test_branch_rejection(self) -> None:
        self.bm.create_branch("incident/INC-999-drop", author="agent")
        rejected = self.bm.reject_branch("incident/INC-999-drop", reviewer="sre.lead", reason="False alarm")
        self.assertEqual(rejected.status, "REJECTED")


class TestPoliciesAndActions(unittest.TestCase):
    """P2-T5 (OO-21): Verifies Cedar policies and Kinetic Actions on Omnigraph branches."""

    def setUp(self) -> None:
        self.conn, self.engine = _build_phase2_fixtures()
        self.bm = OmnigraphBranchManager(self.engine.snapshot)
        self.policies = CedarPolicyEvaluator()
        self.executor = KineticActionExecutor(self.bm, self.policies)

    def tearDown(self) -> None:
        self.conn.close()

    def test_agent_blocked_on_main_but_permitted_on_incident_branch(self) -> None:
        with self.assertRaises(PolicyViolationError):
            self.executor.stage_action(
                action_type="TriggerSafeRollback",
                parameters={
                    "service_id": "SVC-PAYMENT-GW",
                    "target_version": "v2.4.1",
                    "incident_id": "INC-409",
                    "justification": "Attempt direct main write",
                },
                branch_name="main",
                actor_role="AutonomousAgent",
            )

        with self.assertRaises(PolicyViolationError):
            self.executor.approve_and_merge(
                branch_name="incident/anything",
                approver="rogue-agent",
                actor_role="AutonomousAgent",
            )

    def test_stage_and_human_merge_rollback_workflow(self) -> None:
        proposal = self.executor.stage_action(
            action_type="TriggerSafeRollback",
            parameters={
                "service_id": "SVC-PAYMENT-GW",
                "target_version": "v2.4.1",
                "incident_id": "INC-409",
                "justification": "PR-882 leaked connections on AccountLedgerDB",
            },
            branch_name="incident/INC-409-rollback",
        )
        self.assertTrue(proposal.policy_decision.allowed)
        self.assertTrue(proposal.policy_decision.requires_human_merge)
        self.assertEqual(proposal.simulated_post_action_health["new_status"], "HEALTHY")

        # main still CRITICAL before merge
        self.assertEqual(
            self.bm.get_engine("main").get_raw_object("Service", "SVC-PAYMENT-GW")["status"],
            "CRITICAL",
        )

        # HumanSRE approves and merges
        self.executor.approve_and_merge(
            branch_name="incident/INC-409-rollback",
            approver="senior.sre@netsol.example",
            approval_note="Verified PR-882 leak; approved rollback to v2.4.1",
        )

        main_engine = self.bm.get_engine("main")
        svc = main_engine.get_raw_object("Service", "SVC-PAYMENT-GW")
        inc = main_engine.get_raw_object("Incident", "INC-409")
        self.assertEqual(svc["current_version"], "v2.4.1")
        self.assertEqual(svc["status"], "HEALTHY")
        self.assertEqual(inc["status"], "MITIGATED")

    def test_scale_pool_isolate_traffic_and_preconditions(self) -> None:
        # Precondition error: pool size out of range
        with self.assertRaises(ActionPreconditionError):
            self.executor.stage_action(
                action_type="ScaleDatabaseConnectionPool",
                parameters={
                    "database_id": "DB-SESSION-REDIS",
                    "new_max_connections": 5000,
                    "incident_id": "INC-601",
                    "justification": "Invalid limit test",
                },
                branch_name="incident/INC-601-scale",
            )

        scale_prop = self.executor.stage_action(
            action_type="ScaleDatabaseConnectionPool",
            parameters={
                "database_id": "DB-SESSION-REDIS",
                "new_max_connections": 800,
                "incident_id": "INC-601",
                "justification": "Relieve Redis connection saturation",
            },
            branch_name="incident/INC-601-scale",
        )
        self.assertEqual(scale_prop.simulated_post_action_health["new_status"], "HEALTHY")

        iso_prop = self.executor.stage_action(
            action_type="IsolateServiceTraffic",
            parameters={
                "caller_service_id": "SVC-CHECKOUT",
                "target_service_id": "SVC-PAYMENT-GW",
                "fallback_mode": "QUEUE_DEFERRED_PAYMENT",
                "justification": "Shed checkout load during mitigation",
            },
            branch_name="incident/INC-409-isolate",
        )
        self.assertTrue(iso_prop.simulated_post_action_health["circuit_breaker_open"])


if __name__ == "__main__":
    unittest.main()
