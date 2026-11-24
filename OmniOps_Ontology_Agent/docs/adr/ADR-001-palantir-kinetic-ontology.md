# ADR-001: Adopting a Palantir-Style Semantic & Kinetic Ontology over Raw Text-to-SQL and Vector RAG

- **Status:** Accepted
- **Date:** 2026-11-24
- **Context:** NETSOL Internship — OmniOps Ontology Agent Architecture

---

## 1. Context and Problem Statement

When building an AI Agent for microservice root-cause analysis (RCA) and architectural blast-radius evaluation, two common baseline architectures are often proposed:
1. **Text-to-SQL over telemetry tables:** Let the LLM inspect SQL `CREATE TABLE` statements and generate ad-hoc SQL queries (`JOIN`s, recursive `CTE`s) at runtime.
2. **Vector RAG over markdown docs and logs:** Chunk architecture documentation and incident logs into vector embeddings and retrieve top-$k$ chunks per query.

However, in operational software engineering environments:
- **Multi-hop graph traversal in ad-hoc LLM SQL is brittle:** Computing transitive upstream blast radius ($1..k$ hops with cycle prevention and criticality weighting) via LLM-generated recursive SQL frequently produces syntax errors, infinite loops, or silent join omissions.
- **Unstructured RAG lacks topological truth:** Vector similarity cannot reliably answer deterministic structural questions such as *"List every P0 service transitively calling `PaymentGatewayService`"*.
- **Neither approach governs mutations:** Operational remediation requires strict pre-conditions, typed parameters, and access control before rolling back a deployment or modifying infrastructure state.

## 2. Decision

We adopt a **Palantir Foundry-inspired Semantic & Kinetic Ontology combined with NVIDIA Auto-Ontology discovery and certification**:

1. **Auto-Ontology Discovery & Certification Gate:** Raw relational tables (`raw_services`, `raw_calls`, `raw_pull_requests`, `raw_incidents`) are scanned to draft semantic definitions, which must be marked `CERTIFIED` before agent exposure.
2. **Semantic Layer (Nouns & Graph Links):** All domain entities are instantiated as validated Pydantic **Objects** (`Service`, `Endpoint`, `Database`, `PullRequest`, `Incident`, `Team`) connected by typed, directional **Links** (`CALLS`, `EXPOSES`, `READS_WRITES`, `DEPLOYED_TO`, `AFFECTS`, `OWNED_BY`).
3. **Kinetic Layer (Governed Verbs):** Every state change is encapsulated in an **Action Type** (`TriggerSafeRollback`, `ScaleDatabaseConnectionPool`, `IsolateServiceTraffic`) with deterministic Python pre-condition checks and side-effect handlers.

## 3. Consequences

- **Positive:** 100% deterministic blast-radius and fault-tree traversal; zero hallucinated SQL joins; self-documenting domain vocabulary; strict validation of all operational mutations.
- **Negative / Trade-off:** Requires defining and certifying ontology schemas upfront before new entity types can be reasoned over by the agent (mitigated by the Auto-Ontology scanner that drafts schemas automatically from SQLite metadata).
