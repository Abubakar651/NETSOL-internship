# ADR-002: Omnigraph Copy-on-Write State Branching & Cedar Policy Governance for Agent Mutations

- **Status:** Accepted
- **Date:** 2026-11-24
- **Context:** NETSOL Internship — OmniOps Ontology Agent Architecture

---

## 1. Context and Problem Statement

An autonomous SRE agent that only *diagnoses* incidents still leaves manual toil on the on-call engineer, whereas an agent that *directly executes* rollbacks or traffic shifts in production introduces unacceptable risk if the agent misinterprets an ambiguous signal.

We need a mechanism that allows the agent to **proactively prepare and simulate the exact remediation action** while guaranteeing that **production state (`main`) is never mutated without policy compliance and human review**.

## 2. Decision

Inspired by **ModernRelay Omnigraph**, we treat the live ontology graph as a **Git-like versioned state store** paired with a **Cedar-inspired declarative policy evaluator**:

1. **Zero-Copy Branching (`main` vs. `incident/*`):**
   - Production state resides on branch `main`.
   - When the agent proposes a remediation action (e.g., `TriggerSafeRollback` on `SVC-PAYMENT-GW`), it forks a lightweight copy-on-write branch (`incident/INC-409-rollback`) from `main`'s head commit.
2. **Branch-Isolated Simulation & Diffing:**
   - The Kinetic Action executes on the `incident/INC-409-rollback` branch, producing a new commit and computing the simulated post-action service health and a structured 3-way state diff against `main`.
3. **Cedar-Style Policy Enforcement:**
   - Declarative policy rules explicitly **forbid** `Role::"AutonomousAgent"` from committing or merging directly to `main`.
   - Merging an `incident/*` branch affecting a `P0` or `P1` service into `main` requires an authenticated `Role::"HumanSRE"` approval action from the Operations Center Approval Inbox.

## 3. Consequences

- **Positive:** Eliminates the risk of unapproved production mutations; gives human engineers a concrete, previewable state diff (just like a Git Pull Request for operational state) and a full cryptographic/hash commit audit trail.
- **Negative / Trade-off:** Adds branch management and 3-way merge logic to the in-memory graph engine (kept fast and lightweight via deep-copied immutable object snapshots per commit).
