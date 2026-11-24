# 00 — Executive Summary & Product Requirements Document (PRD)

| Metadata | Details |
| :--- | :--- |
| **Document ID** | `OMNIOPS-PRD-001` |
| **Project Name** | OmniOps Ontology Agent (Microservice Root-Cause & Blast-Radius Intelligence) |
| **Organization** | NETSOL Internship Engineering |
| **Status** | Approved for 5-Phase Implementation |
| **Architectural References** | NVIDIA Auto-Ontology, Palantir Foundry Ontology, ModernRelay Omnigraph |

---

## 1. Problem Statement & Industry Context

In modern enterprise software organizations running dozens or hundreds of microservices, production incidents trigger a high-stress race against downtime. When an alert fires (for example, `PaymentGatewayService` returning HTTP `500` errors), on-call engineers must rapidly answer four critical questions:

1. **Blast Radius (Upstream Impact):** Which customer-facing `P0` and `P1` services depend directly or transitively on this failing component?
2. **Fault Tree (Downstream Dependencies):** Which databases, caches, queues, or third-party APIs does this component depend on?
3. **Causal Change Correlation:** Were any Pull Requests, configuration changes, or database schema migrations deployed to the affected service—or its transitive dependencies—shortly before the anomaly began?
4. **Safe Remediation:** What is the safest corrective action (e.g., rolling back a specific deployment or shifting traffic), and what governance approval is required before mutating production state?

### Why Standard AI Approaches Fail in Enterprise Operations

| Traditional AI Pattern | Failure Mode in Production Incident Response |
| :--- | :--- |
| **Unconstrained Text-to-SQL** | LLMs guess foreign-key join paths across raw telemetry tables, silently producing wrong blast-radius counts or missing multi-hop transitive dependencies. |
| **Unstructured Vector RAG** | Runbooks and architecture markdown docs drift out of sync with live service topology; vector similarity retrieves irrelevant historical post-mortems. |
| **Direct Tool-Calling Agents** | Allowing an LLM to directly invoke destructive APIs (`rollback_service`, `restart_db`) without a transactional state branch and policy engine creates severe operational risk. |

---

## 2. The Solution: An Ontology-Grounded Agent Architecture

**OmniOps Ontology Agent** introduces a **Governed Ontology Layer** between raw operational data and AI agents:

1. **Auto-Ontology Discovery & Certification (NVIDIA Pattern):** Raw database schemas and service manifests are introspected to draft semantic definitions (`Objects`, `Metrics`, `Join Paths`) that must be marked `CERTIFIED` before any agent can query them. Incoming questions are checked for **answerability** against the certified schema before execution.
2. **Semantic & Kinetic Modeling (Palantir Foundry Pattern):** The domain is modeled as strictly typed **Object Types** (`Service`, `Endpoint`, `Database`, `PullRequest`, `Incident`, `Team`), **Link Types** (`CALLS`, `EXPOSES`, `READS_WRITES`, `DEPLOYED_TO`, `AFFECTS`, `OWNED_BY`), and **Action Types** (`TriggerSafeRollback`, `IsolateServiceTraffic`, `ScaleConnectionPool`).
3. **Versioned Graph & Policy Governance (ModernRelay Omnigraph Pattern):** Every state mutation proposed by an agent is written as a commit on an isolated, zero-copy **Omnigraph branch** (e.g., `incident/INC-409-rollback`). Declarative **Cedar-style policies** enforce that high-criticality (`P0`) mutations cannot merge to `main` without human approval.
4. **Universal Access via MCP (Model Context Protocol):** The entire Ontology Layer is served through a standardized **MCP Server**, enabling both the built-in OmniOps SRE Agent and external AI clients (Claude, Cursor, Antigravity) to reason over the exact same certified world model.

---

## 3. Target Personas

1. **On-Call Site Reliability Engineer (SRE):** Needs immediate root-cause correlation during an active `SEV1`/`SEV2` outage and a one-click, pre-validated remediation proposal.
2. **Staff Software Architect / Tech Lead:** Wants to evaluate the transitive blast radius of a proposed Pull Request or database schema change before merging.
3. **Platform / Data Owner:** Uses the Auto-Ontology Discovery view to review, refine, and certify entity definitions and governance policies.

---

## 4. Functional Requirements (FR)

### 4.1 Auto-Ontology & Semantic Discovery
- **`FR-01` (Schema Introspection):** The system shall inspect underlying SQLite tables and service metadata to automatically generate draft Ontology Object, Property, and Link definitions.
- **`FR-02` (Certification Gate):** Only ontology definitions with `certification_status == "CERTIFIED"` shall be exposed to production agent reasoning tools.
- **`FR-03` (Answerability Check):** Before running a multi-step investigation, the ontology layer shall verify whether the user's question maps to certified Object Types, Properties, and Links, returning a structured explanation if unanswerable.

### 4.2 Palantir Semantic & Kinetic Layer
- **`FR-04` (Typed Object Registry):** The system shall enforce strict Pydantic validation on all instances of `Service`, `Endpoint`, `Database`, `PullRequest`, `Incident`, and `Team`.
- **`FR-05` (Multi-Hop Blast Radius):** The graph engine shall compute upstream blast radius up to $k$ hops along inverse `CALLS` and `READS_WRITES` links, categorizing affected services by tier (`P0`, `P1`, `P2`).
- **`FR-06` (Causal Deployment Correlation):** Given an `Incident`, the ontology engine shall traverse the affected service and its downstream fault tree to rank recent `PullRequest` deployments by temporal proximity and changed-component overlap.
- **`FR-07` (Governed Kinetic Actions):** Every operational mutation shall be encapsulated as an `ActionType` with explicit pre-condition checks, parameter schemas, and side-effect declarations.

### 4.3 Omnigraph Versioned State & Policy Engine
- **`FR-08` (Git-Style Branching):** Agents shall stage proposed actions on isolated branches (`incident/<id>-remediation`) without mutating the `main` production state graph.
- **`FR-09` (Declarative Policy Evaluation):** A Cedar-inspired policy engine shall evaluate every staged action against actor role, target service criticality (`tier`), and target branch (`main` vs. feature branch).
- **`FR-10` (3-Way Diff & Merge Audit Log):** Approving a branch shall perform a state diff check, apply the mutation to `main`, and record an immutable commit hash with timestamp, actor, approver, and justification.

### 4.4 MCP Server & Autonomous Agent
- **`FR-11` (Full MCP Server):** The ontology layer shall expose standardized MCP `Resources`, `Tools`, and `Prompts` accessible both in-process and over JSON-RPC.
- **`FR-12` (Resilient Multi-Provider Agent):** The agent shall support Gemini as primary reasoning engine, automatic fallback to Groq / OpenRouter, and a deterministic offline graph-reasoning mode for zero-key environments.
- **`FR-13` (Anti-Hallucination Evidence Verifier):** Every entity ID (`SVC-*`, `PR-*`, `INC-*`, `DB-*`) cited in the agent's root-cause conclusion must be cross-verified against the actual MCP tool outputs recorded in that turn.

### 4.5 Operations Center UI
- **`FR-14` (Interactive Topology & Blast-Radius Visualizer):** The web UI shall render the live microservice dependency graph and visually highlight blast-radius propagation paths.
- **`FR-15` (Human-in-the-Loop Approval Inbox):** Following the modern Agent OS inbox paradigm, the UI shall provide a dedicated Approval Inbox where engineers review staged Omnigraph branch diffs and approve or reject agent actions.

---

## 5. Non-Functional Requirements (NFR) & Service Level Objectives (SLOs)

| Category | Requirement / SLO Target |
| :--- | :--- |
| **Determinism & Accuracy** | **100% topological precision** on blast-radius traversal (zero hallucinated edges); **0 unverified entity IDs** permitted in final agent reports. |
| **Safety & Governance** | **0 direct mutations on `main`** by an AI agent on `P0`/`P1` services without an explicit human approval commit. |
| **Performance** | Graph traversal & blast-radius calculation (`depth <= 5`) completes in **< 15 ms** in-memory; MCP tool calls complete in **< 50 ms**. |
| **Reliability & Resilience** | Automatic provider failover (Gemini $\rightarrow$ Groq/OpenRouter $\rightarrow$ Deterministic Ontology Reasoner) ensures **100% uptime** during live demos and CI tests. |
| **Security** | Zero API credentials exposed to browser clients; all API keys redacted from logs and error diagnostics. |

---

## 6. Success Metrics for Internship Evaluation

1. **Architectural Completeness:** Clear trace showing how *NVIDIA Auto-Ontology*, *Palantir Foundry*, and *ModernRelay Omnigraph* principles operate together in code.
2. **Benchmark Root-Cause Accuracy:** Passes 3/3 Golden Incident Scenarios (`INC-409` Connection Pool Leak, `INC-512` Schema Drift, `INC-601` Redis Eviction Cascade) with exact culprit PR identification and accurate upstream `P0` blast radius.
3. **Automated Test Coverage:** 100% pass rate across all 5 Phase verification test suites (`tests/test_phase1_*.py` through `tests/test_phase5_*.py`).
