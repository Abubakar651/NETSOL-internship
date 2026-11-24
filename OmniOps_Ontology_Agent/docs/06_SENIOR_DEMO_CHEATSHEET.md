# OmniOps Ontology Agent — 3-Minute Senior Live Demo Cheat-Sheet

Concise walkthrough for demonstrating **OmniOps** live, grounded in verified Phase 1–5 behavior (`45/45` tests passing, live Gemini & Groq runs verified, `omniops-ontology` MCP server active).

---

## Pre-Demo Setup (10 Seconds)

1. **Launch Web UI & API Server** (skip if already running on `:4320`):
   ```bash
   python3 /home/bakar/Documents/Internships/NETSOL/OmniOps_Ontology_Agent/run.py
   ```
   Open `http://127.0.0.1:4320/` in Chrome (Dark Glass or Light Glass toggle in top bar).

2. **Optional Terminal Proof — Run Full 45-Test Gate (`~0.3s`):**
   ```bash
   cd /home/bakar/Documents/Internships/NETSOL/OmniOps_Ontology_Agent && \
   /home/bakar/Documents/Internships/NETSOL/.venv/bin/python -m unittest discover -s tests -p "test_phase*.py" -v
   ```

---

## Live Demo Script (3 Minutes)

### 0:00–0:45 — Ontology Discovery & Certification (`Ontology Explorer` Tab)
- Open the **Ontology Explorer** tab.
- Point out how **NVIDIA Auto-Ontology** scanned raw SQLite tables (`raw_services`, `raw_service_calls`, `raw_endpoints`, `raw_databases`, `raw_pull_requests`, `raw_incidents`) and mapped them into **Palantir Foundry** typed primitives:
  - **6 Object Types:** `Service`, `Endpoint`, `Database`, `PullRequest`, `Incident`, `Team`
  - **Link Types:** `EXPOSES`, `CALLS`, `READS_WRITES`, `DEPLOYED_TO`, `AFFECTS`, `OWNED_BY`
  - **Kinetic Action Types:** `TriggerSafeRollback`, `IsolateServiceTraffic`, `ScaleConnectionPool`, `AttachIncidentPostMortem`, `CertifyOntologyDefinition`
- Highlight the **Certification Gate:** `raw_wifi_telemetry` sits in **`DRAFT`** status and is automatically blocked from agent queries until an SME promotes it via `CertifyOntologyDefinition`.

### 0:45–1:45 — Live Incident RCA & Blast Radius (`Operations Center` Tab)
- Switch back to **Operations Center** and click **`INC-409: Payment 500s`** (or enter a custom RCA question).
- Walk through the live investigation steps shown in the console:
  - **6 Timed MCP Tool Calls:** `check_question_answerability` $\rightarrow$ `get_ontology_object` $\rightarrow$ `compute_blast_radius` $\rightarrow$ `find_suspect_deployments` $\rightarrow$ `stage_governed_action`.
  - **Deterministic Graph Math:** Reverse-BFS computes **Blast Radius Score = 30**, flagging 3 upstream **`P0`** services impacted (`SVC-CHECKOUT`, `SVC-MOBILE-GW`, `SVC-WEB-STORE`).
  - **Root Cause Pinpointed:** Correlates **`PR-882`** (deployed 22m prior to `v2.5.0`) exhausting **`DB-ACCOUNT-LEDGER`** (`498 / 500` connections).
  - **Anti-Hallucination Badge:** Point to the **`Verified`** badge — every cited `SVC-*`, `PR-*`, `DB-*`, and `INC-*` ID is programmatically verified against tool outputs before rendering.

### 1:45–2:30 — Omnigraph Branch Governance & One-Click Recovery (`Approval Inbox` Tab)
- Open **Approval Inbox** and inspect staged branch **`incident/INC-409-rollback`**.
- Explain the **Cedar Policy Shield**:
  - `FORBID-AGENT-MAIN-MUTATION` blocks any agent from mutating `main` directly.
  - `FORBID-NONHUMAN-MERGE-MAIN` enforces human-in-the-loop sign-off before merging remediation commits.
- Point to the **3-way state diff** (`PaymentGatewayService`: `v2.5.0` `CRITICAL` $\rightarrow$ `v2.4.1` `HEALTHY`) and click **Approve & Merge to Main**.
- Show `PaymentGatewayService` recovering to **`HEALTHY`** live on the Apple Liquid Glass topology graph.
- *(Tip: Click **Reset Demo** anytime in the header to replay from clean `INC-409` state.)*

### 2:30–3:00 — External MCP Server & Multi-Provider Resilience
- Show [`LIVE_PROVIDER_CHECK.md`](LIVE_PROVIDER_CHECK.md): verified cloud runs on **`INC-409`** with **Gemini (`gemini-3.5-flash-lite`, `2.2s`)** and **Groq (`openai/gpt-oss-20b`, `1.19s`)**, plus an offline deterministic Ontology Reasoner fallback for zero-network demos.
- Note that the exact same **7 Tools, 6 Resources, and 2 Prompts** are live over JSON-RPC 2.0 (`stdio` via `omniops-ontology` in `~/.gemini/config/mcp_config.json`, plus HTTP `POST /mcp`).

---

## Top 4 Senior Q&A Talking Points

1. **Why a Governed Ontology + Graph instead of Text-to-SQL or Vector RAG?**
   Raw RAG and Text-to-SQL guess joins and miss multi-hop upstream callers during an outage. OmniOps models `Service` $\leftrightarrow$ `Database` $\leftrightarrow$ `PullRequest` links explicitly and computes upstream blast radius deterministically in $O(V + E)$ graph traversal.

2. **How do you prevent the LLM from hallucinating service names or fake PR numbers?**
   Every agent response passes through `EvidenceValidator` (`omniops/agent/validator.py`), which extracts cited entity IDs (`SVC-*`, `PR-*`, `DB-*`, `INC-*`) and commit hashes and cross-checks them against the session's recorded MCP tool trace, triggering corrective retry on any ungrounded ID.

3. **What stops an autonomous agent from breaking production (`main`)?**
   ModernRelay Omnigraph-style copy-on-write branching isolates every agent mutation to `incident/*` branches, while Cedar policy rules explicitly forbid autonomous agents from mutating or merging `main` without a human approver.

4. **How is the codebase structured for fast debugging and tracking?**
   The project is split into 6 Jira (`OO`) workstreams, 32 single-responsibility tasks (`OO-2`, `OO-8`..`OO-38`), and 32 subtasks (`OO-39`..`OO-70`), backed by 23 isolated `unittest` diagnostic classes (`45/45` passing) so any regression pinpoints the exact module and task key.
