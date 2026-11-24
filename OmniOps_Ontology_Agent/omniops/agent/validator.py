"""Anti-hallucination EvidenceValidator grounding all report claims in MCP tool traces."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from omniops.mcp import ToolCallTrace

from .prompts import InvestigationReport

_ENTITY_ID_RE = re.compile(
    r"\b(?:SVC-[A-Z0-9-]+|PR-[0-9]+|DB-[A-Z0-9-]+|INC-[0-9]+|EP-[A-Z0-9-]+|TEAM-[A-Z0-9-]+)\b"
)


class EvidenceValidationError(ValueError):
    """Raised when an agent report cites unverified entity IDs, branches, or commits."""

    def __init__(self, message: str, *, validation_hint: str = "") -> None:
        super().__init__(message)
        self.validation_hint = validation_hint or message


def extract_entity_ids(text: str) -> set[str]:
    """Extract all Ontology object identifiers (SVC-*, PR-*, DB-*, INC-*, EP-*, TEAM-*) from text."""
    return set(_ENTITY_ID_RE.findall(text))


class EvidenceValidator:
    """Cross-verifies every identifier and staged action against the session MCP tool trace."""

    def collect_allowed_evidence(self, traces: list[ToolCallTrace]) -> dict[str, set[str]]:
        entity_ids: set[str] = set()
        branches: set[str] = set()
        commits: set[str] = set()
        actions: set[str] = set()

        for trace in traces:
            if trace.status != "OK":
                continue
            serialized = json.dumps({"arguments": trace.arguments, "result": trace.result})
            entity_ids.update(extract_entity_ids(serialized))

            if trace.tool_name == "stage_governed_action" and isinstance(trace.result, dict):
                branch = trace.result.get("branch_name")
                commit = trace.result.get("commit_hash")
                action = trace.result.get("action_type")
                if isinstance(branch, str) and branch:
                    branches.add(branch)
                if isinstance(commit, str) and commit:
                    commits.add(commit)
                if isinstance(action, str) and action:
                    actions.add(action)

        return {
            "entity_ids": entity_ids,
            "branches": branches,
            "commits": commits,
            "actions": actions,
        }

    def validate(
        self,
        raw_report: dict[str, Any] | InvestigationReport,
        traces: list[ToolCallTrace],
    ) -> InvestigationReport:
        try:
            report = (
                raw_report
                if isinstance(raw_report, InvestigationReport)
                else InvestigationReport.model_validate(raw_report)
            )
        except ValidationError as exc:
            raise EvidenceValidationError(
                f"InvestigationReport schema validation failed: {exc}",
                validation_hint="Return a complete JSON object matching the InvestigationReport schema.",
            ) from exc

        allowed = self.collect_allowed_evidence(traces)
        allowed_ids = allowed["entity_ids"]

        # 1. Verify structured entity ID fields
        structured_ids: list[str] = []
        for candidate in (
            report.incident_id,
            report.primary_failing_service_id,
            report.culprit_pull_request_id,
            report.affected_downstream_resource_id,
            *report.upstream_blast_radius_service_ids,
        ):
            if isinstance(candidate, str) and candidate.strip():
                structured_ids.append(candidate.strip())

        ungrounded_structured = sorted(set(structured_ids) - allowed_ids)
        if ungrounded_structured:
            raise EvidenceValidationError(
                f"Ungrounded entity ID(s) in report fields: {ungrounded_structured}",
                validation_hint=(
                    f"Remove fabricated ID(s) {ungrounded_structured}. "
                    f"Only cite verified IDs from MCP tools: {sorted(allowed_ids)}."
                ),
            )

        # 2. Verify every entity ID mentioned in prose summary and evidence_chain
        prose = report.root_cause_summary + "\n" + "\n".join(report.evidence_chain)
        prose_ids = extract_entity_ids(prose)
        ungrounded_prose = sorted(prose_ids - allowed_ids)
        if ungrounded_prose:
            raise EvidenceValidationError(
                f"Hallucinated entity ID(s) in narrative text: {ungrounded_prose}",
                validation_hint=(
                    f"Narrative text mentioned unverified ID(s) {ungrounded_prose}. "
                    f"Use only verified IDs: {sorted(allowed_ids)}."
                ),
            )

        # 3. Verify staged branch, action, and commit hash grounding
        if allowed["branches"]:
            if report.staged_branch_name not in allowed["branches"]:
                raise EvidenceValidationError(
                    f"Unverified staged_branch_name '{report.staged_branch_name}'.",
                    validation_hint=f"Use exact staged branch from MCP trace: {sorted(allowed['branches'])}.",
                )
            if report.staged_commit_hash not in allowed["commits"]:
                raise EvidenceValidationError(
                    f"Unverified staged_commit_hash '{report.staged_commit_hash}'.",
                    validation_hint=f"Use exact commit hash from MCP trace: {sorted(allowed['commits'])}.",
                )
            if report.staged_action_type not in allowed["actions"]:
                raise EvidenceValidationError(
                    f"Unverified staged_action_type '{report.staged_action_type}'.",
                    validation_hint=f"Use exact action type from MCP trace: {sorted(allowed['actions'])}.",
                )
        else:
            if report.staged_branch_name or report.staged_commit_hash:
                raise EvidenceValidationError(
                    "Report claimed a staged branch/commit even though no action was staged in MCP tools.",
                    validation_hint="Leave staged_branch_name and staged_commit_hash empty when no action was staged.",
                )

        return report
