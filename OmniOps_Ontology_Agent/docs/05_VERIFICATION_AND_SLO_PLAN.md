# 05 — QA, Golden Benchmark & Verification Plan

| Metadata | Details |
| :--- | :--- |
| **Document ID** | `OMNIOPS-QA-005` |
| **Title** | Automated Verification Matrix, Golden Incident Benchmarks & Acceptance Gates |
| **Status** | Approved Verification Plan |
| **Related Docs** | [`00_EXECUTIVE_SUMMARY_PRD.md`](00_EXECUTIVE_SUMMARY_PRD.md), [`04_PHASE_WISE_ROADMAP.md`](04_PHASE_WISE_ROADMAP.md) |

---

## 1. Verification Philosophy

In enterprise software houses, an AI agent architecture is only as credible as its **deterministic verification gates** and **golden evaluation benchmarks**. OmniOps enforces verification at four levels:

1. **Schema & Discovery Invariants (Phase 1):** Ensuring raw tables map accurately to certified Palantir Object and Link definitions and unanswerable queries are intercepted early.
2. **Topological & Governance Invariants (Phase 2):** Proving graph traversal algorithms (`compute_blast_radius`, `find_suspect_deployments`), Omnigraph branch isolation, and Cedar policy blocks behave deterministically.
3. **Protocol Compliance (Phase 3):** Validating JSON-RPC 2.0 MCP tool, resource, and prompt contracts.
4. **Golden Incident Benchmark & E2E Workflow (Phases 4–5):** Evaluating end-to-end Root-Cause Analysis accuracy, anti-hallucination evidence checking, and human-in-the-loop branch merge recovery across 3 realistic microservice outage scenarios.

---

## 2. The Golden Incident Benchmark Suite

Our seeded enterprise topology models a realistic fintech/e-commerce payment platform with 3 distinct active/historical incidents designed to test multi-hop graph reasoning:

### Scenario 1: `INC-409` — Connection Pool Exhaustion via Recent Code Deployment (`SEV1`)
- **Failing Service:** `SVC-PAYMENT-GW` (`PaymentGatewayService`, Tier `P0`, `v2.5.0`, Error Rate `18.4%`)
- **Downstream Symptom:** `DB-ACCOUNT-LEDGER` (`PostgreSQL`) at `498 / 500` active connections (`saturation_ratio = 0.996`).
- **Expected Upstream Blast Radius:**
  - Hop 1: `SVC-CHECKOUT` (`P0`, hard dependency)
  - Hop 2: `SVC-MOBILE-GW` (`P0`), `SVC-WEB-STORE` (`P0`)
- **Expected Root Cause PR:** `PR-882` (*"Refactor ledger DB connection pool & disable idle reaper"*, merged 22 minutes prior to `INC-409` onto `SVC-PAYMENT-GW` as `v2.5.0`).
- **Expected Staged Action:** `TriggerSafeRollback(service_id="SVC-PAYMENT-GW", target_version="v2.4.1", incident_id="INC-409")` on branch `incident/INC-409-rollback`.

### Scenario 2: `INC-512` — Fraud Engine Latency Spike & Breaking Schema Migration (`SEV2`)
- **Failing Service:** `SVC-FRAUD-ENGINE` (`FraudDetectionService`, Tier `P1`, `v1.9.0`, `p99_latency_ms = 3100`)
- **Downstream Symptom:** `DB-ORDER-STORE` experiencing full table scans after an unindexed column migration.
- **Expected Upstream Blast Radius:**
  - Hop 1: `SVC-PAYMENT-GW` (`P0`)
  - Hop 2: `SVC-CHECKOUT` (`P0`)
  - Hop 3: `SVC-MOBILE-GW` (`P0`), `SVC-WEB-STORE` (`P0`)
- **Expected Root Cause PR:** `PR-879` (*"Add fraud_risk_audit JSONB column migration without index"*, merged 47 minutes prior to `INC-512` onto `SVC-FRAUD-ENGINE` / `DB-ORDER-STORE`).
- **Expected Staged Action:** `TriggerSafeRollback(service_id="SVC-FRAUD-ENGINE", target_version="v1.8.4", incident_id="INC-512")` or `IsolateServiceTraffic` on branch `incident/INC-512-rollback`.

### Scenario 3: `INC-601` — Session Cache Saturation Affecting Edge Gateways (`SEV2`)
- **Failing Service:** `SVC-MOBILE-GW` (`MobileAppGateway`, Tier `P0`, `v3.1.2`, Error Rate `9.5%`)
- **Downstream Symptom:** `DB-SESSION-REDIS` (`Redis`) at `480 / 500` connections (`saturation_ratio = 0.96`).
- **Expected Root Cause PR:** `PR-885` (*"Increase mobile session prefetch fanout"*, merged 35 minutes prior to `INC-601`).
- **Expected Staged Action:** `ScaleDatabaseConnectionPool` or `TriggerSafeRollback` on branch `incident/INC-601-rollback`.

---

## 3. Automated Test Matrix

| Test Suite File | Target Phase | Key Test Cases |
| :--- | :--- | :--- |
| `tests/test_phase1_ontology.py` | **Phase 1** | 1. Raw SQLite seeding & schema introspection.<br>2. Auto-Ontology mapping of 6 certified `ObjectType`s and 7 `LinkType`s.<br>3. Blocking uncertified `DRAFT` tables (`raw_wifi_telemetry`) until `CertifyOntologyDefinition` is called.<br>4. Answerability check passing valid SRE queries and rejecting out-of-domain queries. |
| `tests/test_phase2_graph_governance.py` | **Phase 2** | 1. Multi-hop upstream blast-radius accuracy and `blast_radius_severity_score` calculation.<br>2. Cycle-safe traversal when circular service calls exist.<br>3. `correlate_suspect_deployments` ranking `PR-882` #1 for `INC-409` and `PR-879` #1 for `INC-512`.<br>4. Cedar policy rejecting direct agent mutations on `main`.<br>5. Omnigraph copy-on-write branch creation, state diff computation, and human-approved 3-way merge to `main`. |
| `tests/test_phase3_mcp.py` | **Phase 3** | 1. MCP `resources/list` and `resources/read` across all 6 ontology URIs.<br>2. MCP `tools/list` and `tools/call` across all 7 ontology tools.<br>3. MCP `prompts/list` and `prompts/get` for SRE runbooks.<br>4. JSON-RPC 2.0 request/response formatting and structured error codes. |
| `tests/test_phase4_agent.py` | **Phase 4** | 1. End-to-end agent investigation on `INC-409`, `INC-512`, and `INC-601`.<br>2. Provider fallback cascade (Mock Gemini failure $\rightarrow$ Groq/OpenRouter fallback $\rightarrow$ Deterministic Ontology Reasoner).<br>3. `EvidenceValidator` catching and rejecting hallucinated service IDs (`SVC-FAKE-999`) or PR IDs (`PR-9999`).<br>4. API key redaction in diagnostic output. |
| `tests/test_phase5_e2e.py` | **Phase 5** | 1. FastAPI startup & `/api/config`, `/api/topology`, `/api/ontology/schema` health checks.<br>2. Full HTTP lifecycle: `POST /api/investigate` $\rightarrow$ inspect staged branch via `GET /api/branches` $\rightarrow$ approve merge via `POST /api/branches/approve` $\rightarrow$ verify `SVC-PAYMENT-GW` is `HEALTHY` at `v2.4.1` on `main`.<br>3. `/api/mcp` HTTP JSON-RPC endpoint test. |

---

## 4. Verification Execution Commands

All tests are designed to run with zero external network dependencies using Python's standard `unittest` runner (and `pytest` when installed):

```bash
cd /home/bakar/Documents/Internships/NETSOL/OmniOps_Ontology_Agent
/home/bakar/Documents/NAVTTC/.venv/bin/python -m unittest discover -s tests -p "test_phase*.py" -v
```
