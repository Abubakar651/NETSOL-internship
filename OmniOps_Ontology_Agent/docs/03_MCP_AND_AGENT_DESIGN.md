# 03 — Model Context Protocol (MCP) Server & Agent Reasoning Design

| Metadata | Details |
| :--- | :--- |
| **Document ID** | `OMNIOPS-MCP-003` |
| **Title** | MCP Server Contract (Resources, Tools, Prompts) & Grounded Agent Loop |
| **Status** | Approved Specification |
| **Related Docs** | [`01_SYSTEM_ARCHITECTURE_RFC.md`](01_SYSTEM_ARCHITECTURE_RFC.md), [`02_ONTOLOGY_SPECIFICATION.md`](02_ONTOLOGY_SPECIFICATION.md) |

---

## 1. Why Model Context Protocol (MCP) for the Ontology Layer?

Both **NVIDIA Auto-Ontology** and **ModernRelay Omnigraph** standardize on the **Model Context Protocol (MCP)** as the boundary between the ontology layer and AI agents. By exposing our Ontology Layer as an MCP Server:

1. **Single Source of Truth:** Any agent client—whether our built-in OmniOps SRE Agent or an external IDE client like Claude Desktop, Cursor, or Antigravity—consumes the exact same certified Objects, Links, Metrics, and Governed Actions.
2. **Zero Raw DB Exposure:** The LLM never sees raw SQL credentials or uncertified table schemas. Every tool call is mediated and validated by the MCP server.
3. **Dual Transport Support:** Our MCP Server (`omniops/mcp/server.py`) supports:
   - **In-Process Direct Dispatch:** Zero-serialization Python invocation for fast local web UI and test suite runs.
   - **Standard JSON-RPC 2.0 (Stdio & HTTP endpoint `/api/mcp`):** Allows external MCP clients to connect directly to `OmniOps_Ontology_Agent`.

---

## 2. MCP Resources Specification

MCP Resources provide read-only, URI-addressed snapshots of the ontology metadata and version control history.

| Resource URI | MIME Type | Purpose & Payload |
| :--- | :--- | :--- |
| `ontology://schema/certified` | `application/json` | Complete catalog of `CERTIFIED` Object Types, Properties, Link Types, Certified Metrics, and Action Types. |
| `ontology://schema/drafts` | `application/json` | Uncertified (`DRAFT`) tables/columns discovered by Auto-Ontology awaiting SME review. |
| `ontology://topology/live` | `application/json` | Current production graph snapshot on branch `main` (all nodes, health statuses, and directed edges). |
| `ontology://branches/list` | `application/json` | Active Omnigraph branches (`main` plus any pending `incident/*` remediation branches). |
| `ontology://branches/{branch_name}/diff` | `application/json` | 3-way structural diff comparing `{branch_name}` against `main` (modified properties, staged actions, policy evaluation status). |
| `ontology://audit/commits` | `application/json` | Immutable Git-style commit log across all branches with commit hash, parent hash, actor, approver, and timestamp. |

---

## 3. MCP Tools Specification

MCP Tools provide deterministic graph queries, analytical traversal algorithms, and governed kinetic action staging.

### 3.1 `check_question_answerability`
- **Purpose:** Pre-flight check (inspired by *NVIDIA Auto-Ontology*) verifying whether a natural-language question can be answered using certified ontology concepts.
- **Input Schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "question": { "type": "string", "description": "Natural language query from the user." }
    },
    "required": ["question"]
  }
  ```
- **Returns:** `{ "answerable": bool, "matched_object_types": [...], "matched_links": [...], "matched_actions": [...], "unmodeled_concepts": [...], "guidance": str }`

### 3.2 `get_ontology_object`
- **Purpose:** Retrieve a single typed Ontology Object by its primary key along with its immediate inbound and outbound links.
- **Input Schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "object_type": { "type": "string", "enum": ["Service", "Endpoint", "Database", "PullRequest", "Incident", "Team"] },
      "object_id": { "type": "string", "description": "Primary key, e.g. SVC-PAYMENT-GW or INC-409" },
      "branch": { "type": "string", "default": "main" }
    },
    "required": ["object_type", "object_id"]
  }
  ```

### 3.3 `search_ontology_objects`
- **Purpose:** Hybrid filter + keyword search across any certified `ObjectType`.
- **Input Schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "object_type": { "type": "string", "enum": ["Service", "Endpoint", "Database", "PullRequest", "Incident", "Team"] },
      "filters": { "type": "object", "description": "Exact property filters, e.g. {'status': 'CRITICAL', 'tier': 'P0'}" },
      "keyword": { "type": "string", "description": "Optional substring/keyword match across title and summary properties." },
      "branch": { "type": "string", "default": "main" }
    },
    "required": ["object_type"]
  }
  ```

### 3.4 `compute_blast_radius`
- **Purpose:** Deterministic multi-hop reverse traversal across `CALLS` and `READS_WRITES` links to calculate every upstream service and endpoint impacted if `service_id` fails.
- **Input Schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "service_id": { "type": "string", "description": "Target failing service ID, e.g. SVC-PAYMENT-GW" },
      "max_depth": { "type": "integer", "default": 4, "minimum": 1, "maximum": 6 },
      "branch": { "type": "string", "default": "main" }
    },
    "required": ["service_id"]
  }
  ```
- **Returns:**
  - `root_service`: Full object metadata
  - `impacted_upstream_services`: Ordered list of affected callers with `hop_distance`, `tier` (`P0`/`P1`/`P2`), `dependency_path` (e.g. `SVC-MOBILE-GW -> SVC-CHECKOUT -> SVC-PAYMENT-GW`), and `hard_dependency` boolean
  - `downstream_dependencies`: Databases and services that `service_id` depends on
  - `blast_radius_severity_score`: Certified weighted severity score
  - `affected_teams`: On-call teams to notify

### 3.5 `find_suspect_deployments`
- **Purpose:** Correlates an active `Incident` against recent `PullRequest` deployments and `Database` schema migrations across the affected service and its downstream fault tree.
- **Input Schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "incident_id": { "type": "string", "description": "Active incident ID, e.g. INC-409" },
      "lookback_minutes": { "type": "integer", "default": 120, "minimum": 15, "maximum": 1440 },
      "branch": { "type": "string", "default": "main" }
    },
    "required": ["incident_id"]
  }
  ```
- **Returns:** Ranked list of `SuspectDeployment` records with `pr_id`, `target_service_id`, `minutes_before_incident`, `suspect_score` (`0.0`–`1.0`), `evidence_reasons` (e.g., *"Merged 22 minutes prior to INC-409; modified `db/connection_pool.py`; correlates with `DB-ACCOUNT-LEDGER` connection exhaustion"*), and `recommended_rollback_version`.

### 3.6 `stage_governed_action`
- **Purpose:** Creates or updates an isolated Omnigraph branch (`incident/<incident_id>-remediation`), validates action pre-conditions and Cedar policies, and commits the proposed state mutation on that branch.
- **Input Schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "action_type": { "type": "string", "enum": ["TriggerSafeRollback", "ScaleDatabaseConnectionPool", "IsolateServiceTraffic"] },
      "parameters": { "type": "object" },
      "branch_name": { "type": "string", "description": "Isolated branch name, e.g. incident/INC-409-rollback" },
      "actor_role": { "type": "string", "default": "AutonomousAgent" }
    },
    "required": ["action_type", "parameters", "branch_name"]
  }
  ```
- **Returns:** `ActionProposalRecord` including `branch_name`, `commit_hash`, `policy_decision` (`PERMIT_STAGE_REQUIRE_HUMAN_MERGE`), `state_diff`, and `simulated_post_action_health`.

### 3.7 `approve_and_merge_branch`
- **Purpose:** Human-gated operation that performs a 3-way merge of a staged Omnigraph branch into `main`.
- **Input Schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "branch_name": { "type": "string" },
      "approver": { "type": "string", "description": "Authenticated human SRE identifier" },
      "approval_note": { "type": "string" }
    },
    "required": ["branch_name", "approver"]
  }
  ```

---

## 4. MCP Prompts Specification

1. **`sre_root_cause_runbook(incident_id)`**: Pre-packaged multi-step investigation template guiding any MCP-compatible agent through:
   *Answerability Check $\rightarrow$ Incident & Root Service Lookup $\rightarrow$ Upstream Blast Radius $\rightarrow$ Downstream Fault Tree $\rightarrow$ Suspect PR Correlation $\rightarrow$ Staged Remediation Branch*.
2. **`pr_blast_radius_gate(pr_id)`**: Pre-deployment architectural review template evaluating which `P0`/`P1` services and databases are transitively exposed if a given Pull Request introduces a regression.

---

## 5. Agent Output Contract & Anti-Hallucination Verifier

The OmniOps Agent returns a strictly typed Pydantic model (`InvestigationReport`):

```python
class InvestigationReport(BaseModel):
    incident_id: str
    answerable: bool
    root_cause_summary: str
    primary_failing_service_id: str
    culprit_pull_request_id: str | None
    affected_downstream_resource_id: str | None
    upstream_blast_radius_service_ids: list[str]
    blast_radius_severity_score: int
    evidence_chain: list[str]
    staged_branch_name: str
    staged_action_type: str
    staged_commit_hash: str
    human_approval_required: bool
```

### Deterministic Verification Invariants (`omniops/agent/validator.py`)
Before any `InvestigationReport` is returned to the user:
1. **Entity Existence Check:** `primary_failing_service_id`, `culprit_pull_request_id`, `affected_downstream_resource_id`, and every ID in `upstream_blast_radius_service_ids` must exist in the certified ontology and must have been retrieved in the session's MCP tool trace.
2. **Branch Integrity Check:** `staged_branch_name` and `staged_commit_hash` must match an actual uncommitted Omnigraph branch in `OmnigraphVCS`.
3. **Zero Unverified Claims:** Any regex match for `SVC-[A-Z0-9-]+`, `PR-[0-9]+`, `DB-[A-Z0-9-]+`, or `INC-[0-9]+` inside `root_cause_summary` or `evidence_chain` that was not returned by an MCP tool call triggers an automatic validation error and corrective regeneration.
