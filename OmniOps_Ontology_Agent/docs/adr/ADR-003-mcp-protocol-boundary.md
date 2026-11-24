# ADR-003: Decoupling the Ontology Layer from Agents via the Model Context Protocol (MCP)

- **Status:** Accepted
- **Date:** 2026-11-24
- **Context:** NETSOL Internship — OmniOps Ontology Agent Architecture

---

## 1. Context and Problem Statement

In many prototype AI applications, ontology traversal functions are tightly coupled inside a single LLM agent loop. This creates two problems:
1. Other developer tools (such as Claude Desktop, Cursor, or Antigravity IDE) cannot reuse the ontology layer without duplicating code.
2. There is no formal contract separating *what the ontology provides* from *how a specific LLM reasons over it*.

Both **NVIDIA Auto-Ontology** and **ModernRelay Omnigraph** solve this by exposing their semantic and graph layers as a **Model Context Protocol (MCP) Server**.

## 2. Decision

We architect the Ontology Layer as a self-contained **MCP Server** (`omniops/mcp/server.py`) that exposes:

1. **MCP Resources (`ontology://*`):** Read-only URIs for certified schemas, uncertified drafts, live graph topology, branch diffs, and commit logs.
2. **MCP Tools:** Strictly schema-validated operations (`check_question_answerability`, `get_ontology_object`, `search_ontology_objects`, `compute_blast_radius`, `find_suspect_deployments`, `stage_governed_action`, `approve_and_merge_branch`).
3. **MCP Prompts:** Standardized operational runbooks (`sre_root_cause_runbook`, `pr_blast_radius_gate`).

The MCP Server supports both **in-process Python dispatch** (for zero-overhead execution inside the FastAPI web app and unit test suite) and **JSON-RPC 2.0 transport** (via HTTP `/api/mcp` and CLI stdio) so external MCP clients can connect directly.

## 3. Consequences

- **Positive:** Complete architectural decoupling between the Ontology Engine and the Agent Runner; instant compatibility with external MCP ecosystems; every agent interaction is logged through a single, auditable protocol boundary.
- **Negative / Trade-off:** Requires maintaining strict JSON Schema definitions for all tools and resources (which simultaneously improves LLM tool-calling reliability).
