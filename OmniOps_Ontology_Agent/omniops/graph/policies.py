"""Cedar-inspired declarative policy evaluator governing Omnigraph & Kinetic Actions."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class PolicyViolationError(PermissionError):
    """Raised when a Cedar policy rule forbids a requested operation."""


class PolicyDecision(BaseModel):
    """Structured result from evaluating declarative governance policies."""

    model_config = ConfigDict(extra="forbid")

    allowed: bool
    effect: Literal["PERMIT", "FORBID"]
    policy_id: str
    reason: str
    requires_human_merge: bool = False


_AGENT_STAGEABLE_ACTIONS = {
    "TriggerSafeRollback",
    "ScaleDatabaseConnectionPool",
    "IsolateServiceTraffic",
}


class CedarPolicyEvaluator:
    """Evaluates actor role, action type, target branch, and service tier rules."""

    def evaluate(
        self,
        principal_role: str,
        action_type: str,
        target_branch: str,
        target_service_tier: str = "P0",
        justification: str = "",
    ) -> PolicyDecision:
        if principal_role == "AutonomousAgent" and target_branch == "main":
            return PolicyDecision(
                allowed=False,
                effect="FORBID",
                policy_id="FORBID-AGENT-MAIN-MUTATION",
                reason="AutonomousAgent principals are forbidden from directly mutating 'main'. Stage on an 'incident/*' branch instead.",
                requires_human_merge=True,
            )

        if action_type == "MergeBranchToMain":
            if principal_role != "HumanSRE":
                return PolicyDecision(
                    allowed=False,
                    effect="FORBID",
                    policy_id="FORBID-NONHUMAN-MERGE-MAIN",
                    reason=f"Principal role '{principal_role}' cannot merge branches into 'main'; HumanSRE role is required.",
                    requires_human_merge=True,
                )
            if not justification.strip():
                return PolicyDecision(
                    allowed=False,
                    effect="FORBID",
                    policy_id="FORBID-MISSING-JUSTIFICATION",
                    reason="HumanSRE merge into 'main' requires a non-empty approval justification.",
                    requires_human_merge=False,
                )
            return PolicyDecision(
                allowed=True,
                effect="PERMIT",
                policy_id="PERMIT-HUMAN-MERGE-MAIN",
                reason="HumanSRE merge into 'main' permitted with valid justification.",
                requires_human_merge=False,
            )

        if (
            principal_role == "AutonomousAgent"
            and target_branch.startswith("incident/")
            and action_type in _AGENT_STAGEABLE_ACTIONS
        ):
            needs_human = target_service_tier in {"P0", "P1"}
            return PolicyDecision(
                allowed=True,
                effect="PERMIT",
                policy_id="PERMIT-AGENT-INCIDENT-BRANCH",
                reason=(
                    f"Action '{action_type}' permitted to stage on isolated branch '{target_branch}'. "
                    + (
                        f"HumanSRE approval required before merging tier {target_service_tier} change to 'main'."
                        if needs_human
                        else "Low-tier service change ready for review."
                    )
                ),
                requires_human_merge=needs_human,
            )

        if principal_role == "HumanSRE" and action_type in _AGENT_STAGEABLE_ACTIONS:
            return PolicyDecision(
                allowed=True,
                effect="PERMIT",
                policy_id="PERMIT-HUMAN-KINETIC-ACTION",
                reason=f"HumanSRE permitted to execute '{action_type}' on '{target_branch}'.",
                requires_human_merge=False,
            )

        return PolicyDecision(
            allowed=False,
            effect="FORBID",
            policy_id="FORBID-DEFAULT",
            reason=f"No policy permits '{principal_role}' to invoke '{action_type}' on branch '{target_branch}'.",
            requires_human_merge=True,
        )
