"""Palantir Kinetic Action executor with pre-condition checks and Omnigraph staging."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .branching import CommitRecord, GraphSnapshot, OmnigraphBranchManager, StateDiffItem
from .engine import ObjectNotFoundError, SemanticGraphEngine
from .policies import CedarPolicyEvaluator, PolicyDecision, PolicyViolationError

_TIER_RANK = {"P0": 0, "P1": 1, "P2": 2}


class ActionPreconditionError(ValueError):
    """Raised when a Kinetic Action's domain pre-conditions are not satisfied."""


class ActionProposal(BaseModel):
    """Structured outcome of staging a governed Kinetic Action on an Omnigraph branch."""

    model_config = ConfigDict(extra="forbid")

    action_type: str
    branch_name: str
    commit_hash: str
    policy_decision: PolicyDecision
    parameters: dict[str, Any] = Field(default_factory=dict)
    state_diff: list[StateDiffItem] = Field(default_factory=list)
    simulated_post_action_health: dict[str, Any] = Field(default_factory=dict)


class KineticActionExecutor:
    """Executes validated Palantir Kinetic Actions onto Omnigraph branches under Cedar policies."""

    def __init__(
        self,
        branch_manager: OmnigraphBranchManager,
        policy_evaluator: CedarPolicyEvaluator | None = None,
    ) -> None:
        self.branch_manager = branch_manager
        self.policy_evaluator = policy_evaluator or CedarPolicyEvaluator()

    def _resolve_target_tier(
        self,
        engine: SemanticGraphEngine,
        action_type: str,
        parameters: dict[str, Any],
    ) -> str:
        try:
            if action_type == "TriggerSafeRollback":
                svc = engine.get_raw_object("Service", str(parameters.get("service_id", "")))
                return str(svc["tier"])
            if action_type == "IsolateServiceTraffic":
                tiers = [
                    engine.get_raw_object("Service", str(parameters.get("caller_service_id", "")))["tier"],
                    engine.get_raw_object("Service", str(parameters.get("target_service_id", "")))["tier"],
                ]
                return min(tiers, key=lambda t: _TIER_RANK.get(t, 3))
            if action_type == "ScaleDatabaseConnectionPool":
                db_id = str(parameters.get("database_id", ""))
                callers = engine.get_neighbors(db_id, link_types=["READS_WRITES"], direction="in")
                tiers = [edge["neighbor"]["tier"] for edge in callers if edge["neighbor"] is not None]
                return min(tiers, key=lambda t: _TIER_RANK.get(t, 3)) if tiers else "P1"
        except ObjectNotFoundError:
            return "P0"
        return "P0"

    def _validate_and_build_mutator(
        self,
        engine: SemanticGraphEngine,
        action_type: str,
        parameters: dict[str, Any],
    ):
        justification = str(parameters.get("justification", "")).strip()
        if not justification:
            raise ActionPreconditionError(f"Action '{action_type}' requires a non-empty justification.")

        if action_type == "TriggerSafeRollback":
            service_id = str(parameters.get("service_id", ""))
            target_version = str(parameters.get("target_version", ""))
            incident_id = str(parameters.get("incident_id", ""))
            try:
                svc = engine.get_raw_object("Service", service_id)
                inc = engine.get_raw_object("Incident", incident_id)
            except ObjectNotFoundError as exc:
                raise ActionPreconditionError(str(exc)) from exc

            if svc["status"] not in ("CRITICAL", "DEGRADED"):
                raise ActionPreconditionError(
                    f"Service '{service_id}' status is '{svc['status']}', not CRITICAL or DEGRADED."
                )
            if not target_version or target_version == svc["current_version"]:
                raise ActionPreconditionError(
                    f"target_version '{target_version}' must differ from current_version '{svc['current_version']}'."
                )
            if inc["affected_service_id"] != service_id:
                raise ActionPreconditionError(
                    f"Incident '{incident_id}' affects '{inc['affected_service_id']}', not '{service_id}'."
                )

            simulated = {
                "service_id": service_id,
                "previous_version": svc["current_version"],
                "new_version": target_version,
                "new_status": "HEALTHY",
                "new_error_rate_pct": 0.2,
                "incident_id": incident_id,
                "incident_status": "MITIGATED",
            }

            def mutate(snap: GraphSnapshot) -> None:
                s = snap.objects["Service"][service_id]
                s["current_version"] = target_version
                s["status"] = "HEALTHY"
                s["error_rate_pct"] = 0.2
                s["p99_latency_ms"] = 180
                i = snap.objects["Incident"][incident_id]
                i["status"] = "MITIGATED"

            return mutate, simulated

        if action_type == "ScaleDatabaseConnectionPool":
            database_id = str(parameters.get("database_id", ""))
            incident_id = str(parameters.get("incident_id", ""))
            try:
                new_max = int(parameters["new_max_connections"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ActionPreconditionError("new_max_connections must be an integer.") from exc

            if not 100 <= new_max <= 2000:
                raise ActionPreconditionError("new_max_connections must be between 100 and 2000.")
            try:
                db = engine.get_raw_object("Database", database_id)
                engine.get_raw_object("Incident", incident_id)
            except ObjectNotFoundError as exc:
                raise ActionPreconditionError(str(exc)) from exc

            new_ratio = round(db["active_connections"] / new_max, 4)
            new_db_status = "HEALTHY" if new_ratio < 0.90 else db["status"]
            simulated = {
                "database_id": database_id,
                "previous_max_connections": db["max_connections"],
                "new_max_connections": new_max,
                "new_saturation_ratio": new_ratio,
                "new_status": new_db_status,
                "incident_id": incident_id,
                "incident_status": "MITIGATED",
            }

            def mutate(snap: GraphSnapshot) -> None:
                d = snap.objects["Database"][database_id]
                d["max_connections"] = new_max
                d["status"] = new_db_status
                i = snap.objects["Incident"][incident_id]
                i["status"] = "MITIGATED"

            return mutate, simulated

        if action_type == "IsolateServiceTraffic":
            caller_id = str(parameters.get("caller_service_id", ""))
            target_id = str(parameters.get("target_service_id", ""))
            fallback_mode = str(parameters.get("fallback_mode", "")).strip()
            if not fallback_mode:
                raise ActionPreconditionError("IsolateServiceTraffic requires a non-empty fallback_mode.")

            try:
                engine.get_raw_object("Service", caller_id)
                engine.get_raw_object("Service", target_id)
            except ObjectNotFoundError as exc:
                raise ActionPreconditionError(str(exc)) from exc

            has_link = any(
                link.link_type == "CALLS"
                and link.source_id == caller_id
                and link.target_id == target_id
                for link in engine.snapshot.links
            )
            if not has_link:
                raise ActionPreconditionError(
                    f"No CALLS link found from '{caller_id}' to '{target_id}'."
                )

            simulated = {
                "caller_service_id": caller_id,
                "target_service_id": target_id,
                "circuit_breaker_open": True,
                "fallback_mode": fallback_mode,
            }

            def mutate(snap: GraphSnapshot) -> None:
                for link in snap.links:
                    if (
                        link.link_type == "CALLS"
                        and link.source_id == caller_id
                        and link.target_id == target_id
                    ):
                        link.properties["circuit_breaker_open"] = True
                        link.properties["fallback_mode"] = fallback_mode
                        break

            return mutate, simulated

        raise ActionPreconditionError(f"Unsupported Kinetic Action '{action_type}'.")

    def stage_action(
        self,
        action_type: str,
        parameters: dict[str, Any],
        branch_name: str,
        actor: str = "omniops-sre-agent",
        actor_role: str = "AutonomousAgent",
    ) -> ActionProposal:
        """Validate policy + pre-conditions and stage a Kinetic Action onto an Omnigraph branch."""
        branch_exists = branch_name in self.branch_manager.branches
        ref_branch = branch_name if branch_exists else "main"
        ref_engine = self.branch_manager.get_engine(ref_branch)

        tier = self._resolve_target_tier(ref_engine, action_type, parameters)
        decision = self.policy_evaluator.evaluate(
            principal_role=actor_role,
            action_type=action_type,
            target_branch=branch_name,
            target_service_tier=tier,
            justification=str(parameters.get("justification", "")),
        )
        if not decision.allowed:
            raise PolicyViolationError(f"[{decision.policy_id}] {decision.reason}")

        mutate, simulated = self._validate_and_build_mutator(ref_engine, action_type, parameters)

        if not branch_exists:
            self.branch_manager.create_branch(branch_name, author=actor, base_branch="main")

        pending_meta = {
            "action_type": action_type,
            "parameters": dict(parameters),
            "target_service_tier": tier,
            "policy_id": decision.policy_id,
            "requires_human_merge": decision.requires_human_merge,
            "simulated_post_action_health": simulated,
        }
        commit = self.branch_manager.commit_mutation(
            branch_name,
            mutate,
            author=actor,
            actor_role=actor_role,
            action_type=action_type,
            summary=f"{action_type}: {parameters.get('justification', '')}",
            pending_action=pending_meta,
        )

        return ActionProposal(
            action_type=action_type,
            branch_name=branch_name,
            commit_hash=commit.commit_hash,
            policy_decision=decision,
            parameters=dict(parameters),
            state_diff=commit.diff,
            simulated_post_action_health=simulated,
        )

    def approve_and_merge(
        self,
        branch_name: str,
        approver: str,
        approval_note: str = "Approved via SRE Inbox",
        actor_role: str = "HumanSRE",
    ) -> CommitRecord:
        """Evaluate merge policy and merge a staged incident branch into main."""
        decision = self.policy_evaluator.evaluate(
            principal_role=actor_role,
            action_type="MergeBranchToMain",
            target_branch="main",
            justification=approval_note,
        )
        if not decision.allowed:
            raise PolicyViolationError(f"[{decision.policy_id}] {decision.reason}")
        return self.branch_manager.merge_branch(
            branch_name=branch_name,
            approver=approver,
            approval_note=approval_note,
            target_branch="main",
        )
