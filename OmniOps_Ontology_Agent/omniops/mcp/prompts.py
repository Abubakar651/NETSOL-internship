"""MCP Prompt templates providing standardized SRE RCA and PR Risk Gate runbooks."""

from __future__ import annotations

from typing import Any


class UnknownPromptError(KeyError):
    """Raised when an MCP client requests a prompt name that does not exist."""


_PROMPTS: list[dict[str, Any]] = [
    {
        "name": "sre_root_cause_runbook",
        "description": "Guided 5-step Ontology investigation runbook for diagnosing a production incident and staging a safe remediation branch.",
        "arguments": [
            {
                "name": "incident_id",
                "description": "Active Incident ID to investigate (e.g., INC-409).",
                "required": True,
            }
        ],
    },
    {
        "name": "pr_blast_radius_gate",
        "description": "Pre-merge or post-merge architectural risk assessment for a PullRequest using transitive dependency blast radius.",
        "arguments": [
            {
                "name": "pr_id",
                "description": "PullRequest ID to evaluate (e.g., PR-882).",
                "required": True,
            }
        ],
    },
]


class MCPPromptProvider:
    """Renders structured MCP prompt templates with strict required-argument checks."""

    def list_prompts(self) -> list[dict[str, Any]]:
        return [dict(item) for item in _PROMPTS]

    def get_prompt(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        args = dict(arguments or {})

        if name == "sre_root_cause_runbook":
            incident_id = args.get("incident_id")
            if not isinstance(incident_id, str) or not incident_id.strip():
                raise ValueError("Prompt 'sre_root_cause_runbook' requires non-empty argument 'incident_id'.")
            clean_id = incident_id.strip()
            text = (
                f"Execute the OmniOps Ontology SRE Root-Cause Runbook for {clean_id}:\n"
                "1. Call check_question_answerability to confirm certified Ontology coverage.\n"
                f"2. Call get_ontology_object(object_type='Incident', object_id='{clean_id}') to locate affected_service_id.\n"
                "3. Call compute_blast_radius on affected_service_id to quantify upstream P0/P1 impact and downstream DB saturation.\n"
                f"4. Call find_suspect_deployments(incident_id='{clean_id}') to rank recent PRs along the fault tree.\n"
                f"5. Call stage_governed_action onto branch 'incident/{clean_id}-rollback' for HumanSRE approval in the Inbox."
            )
            return {
                "description": _PROMPTS[0]["description"],
                "messages": [{"role": "user", "content": {"type": "text", "text": text}}],
            }

        if name == "pr_blast_radius_gate":
            pr_id = args.get("pr_id")
            if not isinstance(pr_id, str) or not pr_id.strip():
                raise ValueError("Prompt 'pr_blast_radius_gate' requires non-empty argument 'pr_id'.")
            clean_id = pr_id.strip()
            text = (
                f"Run the Architectural Blast-Radius Gate for {clean_id}:\n"
                f"1. Call get_ontology_object(object_type='PullRequest', object_id='{clean_id}') to identify target_service_id.\n"
                "2. Call compute_blast_radius on target_service_id to enumerate every transitive P0/P1 caller and downstream DB.\n"
                "3. Summarize affected engineering teams, schema/config risk flags, and rollback readiness."
            )
            return {
                "description": _PROMPTS[1]["description"],
                "messages": [{"role": "user", "content": {"type": "text", "text": text}}],
            }

        raise UnknownPromptError(f"Unknown MCP prompt '{name}'.")
