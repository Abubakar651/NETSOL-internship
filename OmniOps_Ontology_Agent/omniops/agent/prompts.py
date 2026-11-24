"""Ontology-grounded SRE instructions and InvestigationReport Pydantic output contract."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class InvestigationReport(BaseModel):
    """Structured Root-Cause Analysis & Blast-Radius report verified against MCP tool outputs."""

    model_config = ConfigDict(extra="forbid")

    incident_id: str
    answerable: bool
    root_cause_summary: str
    primary_failing_service_id: str
    culprit_pull_request_id: str | None = None
    affected_downstream_resource_id: str | None = None
    upstream_blast_radius_service_ids: list[str] = Field(default_factory=list)
    blast_radius_severity_score: int = Field(ge=0, default=0)
    evidence_chain: list[str] = Field(default_factory=list)
    staged_branch_name: str = ""
    staged_action_type: str = ""
    staged_commit_hash: str = ""
    human_approval_required: bool = True


SRE_INVESTIGATION_SYSTEM_PROMPT = """You are the OmniOps Autonomous SRE & Architecture Investigation Agent.
You reason strictly over verified outputs returned by the OmniOps Ontology MCP Server.

Rules:
1. Ground every single identifier (SVC-*, PR-*, DB-*, INC-*, EP-*, TEAM-*), branch name, and commit hash in the supplied MCP tool evidence.
2. NEVER invent, guess, or extrapolate service IDs, Pull Request IDs, databases, versions, or commit hashes not present in the provided evidence payload.
3. Explain clearly:
   - What failed (root incident and primary service)
   - Upstream blast radius (impacted P0/P1/P2 services and severity score)
   - Downstream root bottleneck (e.g., saturated database or schema issue)
   - Suspect deployment (exact culprit PR and minutes prior to outage)
   - Governed remediation staged on the isolated Omnigraph branch awaiting HumanSRE merge approval.
4. Return ONLY a single valid JSON object matching the InvestigationReport schema.
"""


def investigation_report_json_schema() -> dict[str, Any]:
    """Return a strict JSON Schema compatible with Gemini, Groq, and OpenRouter structured outputs."""
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "incident_id": {"type": "string"},
            "answerable": {"type": "boolean"},
            "root_cause_summary": {"type": "string"},
            "primary_failing_service_id": {"type": "string"},
            "culprit_pull_request_id": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "affected_downstream_resource_id": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "upstream_blast_radius_service_ids": {
                "type": "array",
                "items": {"type": "string"},
            },
            "blast_radius_severity_score": {"type": "integer"},
            "evidence_chain": {
                "type": "array",
                "items": {"type": "string"},
            },
            "staged_branch_name": {"type": "string"},
            "staged_action_type": {"type": "string"},
            "staged_commit_hash": {"type": "string"},
            "human_approval_required": {"type": "boolean"},
        },
        "required": [
            "incident_id",
            "answerable",
            "root_cause_summary",
            "primary_failing_service_id",
            "culprit_pull_request_id",
            "affected_downstream_resource_id",
            "upstream_blast_radius_service_ids",
            "blast_radius_severity_score",
            "evidence_chain",
            "staged_branch_name",
            "staged_action_type",
            "staged_commit_hash",
            "human_approval_required",
        ],
    }
