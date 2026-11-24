"""Multi-step MCP InvestigationRunner orchestrating grounded root-cause & blast-radius analysis."""

from __future__ import annotations

import asyncio
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from omniops.mcp import OmniOpsMCPServer, ToolCallTrace
from omniops.ontology import AnswerabilityReport

from .config import Settings, load_settings
from .prompts import InvestigationReport
from .providers import ReasoningProviders
from .validator import EvidenceValidator

_INCIDENT_RE = re.compile(r"\bINC-[0-9]+\b")
_SEVERITY_RANK = {"SEV1": 0, "SEV2": 1, "SEV3": 2}


class InvestigationRunResult(BaseModel):
    """Complete output from one end-to-end SRE Agent investigation turn."""

    model_config = ConfigDict(extra="forbid")

    question: str
    answerability: AnswerabilityReport
    report: InvestigationReport
    provider_used: str
    tool_trace: list[ToolCallTrace] = Field(default_factory=list)
    diagnostic_events: list[dict[str, Any]] = Field(default_factory=list)


class InvestigationRunner:
    """Executes the 5-step Ontology MCP runbook, validates evidence, and stages remediation."""

    def __init__(
        self,
        mcp_server: OmniOpsMCPServer,
        settings: Settings | None = None,
        providers: ReasoningProviders | None = None,
    ) -> None:
        self.mcp = mcp_server
        self.settings = settings or load_settings()
        self.providers = providers or ReasoningProviders(self.settings)
        self.validator = EvidenceValidator()

    def _resolve_incident_id(self, question: str, explicit_incident_id: str | None) -> str:
        if explicit_incident_id:
            return explicit_incident_id.strip().upper()

        match = _INCIDENT_RE.search(question.upper())
        if match:
            return match.group(0)

        open_res = self.mcp.call_tool(
            "search_ontology_objects",
            {"object_type": "Incident", "filters": {"status": "OPEN"}},
        )
        incidents = open_res["data"]["items"]
        if not incidents:
            all_res = self.mcp.call_tool("search_ontology_objects", {"object_type": "Incident"})
            incidents = all_res["data"]["items"]

        if not incidents:
            raise ValueError("No Incident objects available in the Ontology.")

        lower_q = question.lower()
        for inc in sorted(incidents, key=lambda i: (_SEVERITY_RANK.get(i["severity"], 9), i["id"])):
            svc = self.mcp.call_tool(
                "get_ontology_object",
                {"object_type": "Service", "object_id": inc["affected_service_id"]},
            )["data"]
            svc_tokens = [
                svc["name"].lower(),
                svc["name"].lower().replace("service", "").strip(),
                svc["id"].lower(),
            ]
            if any(tok and tok in lower_q for tok in svc_tokens):
                return inc["id"]
            if any(
                word in lower_q
                for word in re.findall(r"[a-z0-9_]{4,}", f"{inc['title']} {inc['symptom_summary']}".lower())
            ):
                return inc["id"]

        incidents.sort(key=lambda i: (_SEVERITY_RANK.get(i["severity"], 9), i["id"]))
        return incidents[0]["id"]

    def _unique_branch_name(self, base_name: str) -> str:
        existing = set(self.mcp.branch_manager.branches.keys())
        if base_name not in existing:
            return base_name
        counter = 2
        while f"{base_name}-{counter}" in existing:
            counter += 1
        return f"{base_name}-{counter}"

    @staticmethod
    def _select_primary_downstream_db(
        blast_radius: dict[str, Any],
        suspects: dict[str, Any],
    ) -> dict[str, Any] | None:
        dbs = [
            dep
            for dep in blast_radius.get("downstream_dependencies", [])
            if dep.get("object_type") == "Database"
        ]
        if not dbs:
            return None

        top = suspects["suspect_deployments"][0] if suspects.get("suspect_deployments") else None
        migrates_db = top.get("migrates_database_id") if top else None
        if migrates_db:
            for dep in dbs:
                if dep["object_id"] == migrates_db:
                    return dep

        exhausted = [dep for dep in dbs if dep.get("details", {}).get("is_connection_exhausted")]
        if exhausted:
            return exhausted[0]

        stressed = [dep for dep in dbs if dep.get("status") != "HEALTHY"]
        return stressed[0] if stressed else dbs[0]

    async def investigate(
        self,
        question: str | None = None,
        *,
        incident_id: str | None = None,
        prefer_offline: bool = False,
    ) -> InvestigationRunResult:
        if not question and not incident_id:
            raise ValueError("Provide either 'question' or 'incident_id'.")

        effective_question = (
            question.strip()
            if question and question.strip()
            else f"Investigate {incident_id}, compute blast radius, find suspect deployments, and stage a safe remediation."
        )

        trace_start = len(self.mcp.get_trace_log())
        diag_start = len(self.providers.diagnostic_events)

        # Step 1: Pre-flight Answerability Gate
        ans_raw = self.mcp.call_tool("check_question_answerability", {"question": effective_question})["data"]
        answerability = AnswerabilityReport.model_validate(ans_raw)

        if not answerability.answerable:
            run_traces = self.mcp.get_trace_log()[trace_start:]
            return InvestigationRunResult(
                question=effective_question,
                answerability=answerability,
                report=InvestigationReport(
                    incident_id=incident_id or "",
                    answerable=False,
                    root_cause_summary=answerability.guidance,
                    primary_failing_service_id="",
                    human_approval_required=False,
                ),
                provider_used="answerability_gate",
                tool_trace=run_traces,
                diagnostic_events=self.providers.diagnostic_events[diag_start:],
            )

        # Step 2: Inspect Incident and Primary Failing Service
        resolved_inc_id = self._resolve_incident_id(effective_question, incident_id)
        incident = self.mcp.call_tool(
            "get_ontology_object",
            {"object_type": "Incident", "object_id": resolved_inc_id},
        )["data"]
        failing_service_id = incident["affected_service_id"]
        service = self.mcp.call_tool(
            "get_ontology_object",
            {"object_type": "Service", "object_id": failing_service_id},
        )["data"]

        # Step 3: Deterministic Multi-Hop Blast Radius
        blast_radius = self.mcp.call_tool(
            "compute_blast_radius",
            {"service_id": failing_service_id, "max_depth": 4},
        )["data"]

        # Step 4: Causal PR Deployment Correlation
        suspects = self.mcp.call_tool(
            "find_suspect_deployments",
            {"incident_id": resolved_inc_id, "lookback_minutes": 120},
        )["data"]

        downstream_db = self._select_primary_downstream_db(blast_radius, suspects)
        top_suspect = suspects["suspect_deployments"][0] if suspects["suspect_deployments"] else None

        # Step 5: Stage Governed Kinetic Action onto an Isolated Omnigraph Branch
        staged_action: dict[str, Any] | None = None
        rollback_target = (
            (top_suspect.get("recommended_rollback_version") if top_suspect else None)
            or service["last_stable_version"]
        )
        if service["status"] in ("CRITICAL", "DEGRADED") and rollback_target != service["current_version"]:
            branch_name = self._unique_branch_name(f"incident/{resolved_inc_id}-rollback")
            justification = (
                f"Revert {failing_service_id} to {rollback_target} after {top_suspect['pr_id']} correlation."
                if top_suspect
                else f"Revert {failing_service_id} to last stable {rollback_target} during {resolved_inc_id}."
            )
            stage_res = self.mcp.call_tool(
                "stage_governed_action",
                {
                    "action_type": "TriggerSafeRollback",
                    "parameters": {
                        "service_id": failing_service_id,
                        "target_version": rollback_target,
                        "incident_id": resolved_inc_id,
                        "justification": justification,
                    },
                    "branch_name": branch_name,
                    "actor_role": "AutonomousAgent",
                },
            )
            if not stage_res["isError"]:
                staged_action = stage_res["data"]
        elif downstream_db and downstream_db.get("details", {}).get("is_connection_exhausted"):
            branch_name = self._unique_branch_name(f"incident/{resolved_inc_id}-scale")
            curr_max = int(downstream_db["details"]["max_connections"])
            new_max = min(2000, max(curr_max + 200, int(curr_max * 1.5)))
            stage_res = self.mcp.call_tool(
                "stage_governed_action",
                {
                    "action_type": "ScaleDatabaseConnectionPool",
                    "parameters": {
                        "database_id": downstream_db["object_id"],
                        "new_max_connections": new_max,
                        "incident_id": resolved_inc_id,
                        "justification": f"Relieve {downstream_db['object_id']} connection exhaustion for {resolved_inc_id}.",
                    },
                    "branch_name": branch_name,
                    "actor_role": "AutonomousAgent",
                },
            )
            if not stage_res["isError"]:
                staged_action = stage_res["data"]

        # Step 6: Synthesize & Verify Grounded Report
        run_traces = self.mcp.get_trace_log()[trace_start:]
        payload = {
            "question": effective_question,
            "incident": incident,
            "service": service,
            "blast_radius": blast_radius,
            "suspect_deployments": suspects,
            "downstream_db": downstream_db,
            "staged_action": staged_action,
        }

        report, provider_used = await self.providers.synthesize_report(
            payload,
            lambda raw: self.validator.validate(raw, run_traces),
            prefer_offline=prefer_offline,
        )

        return InvestigationRunResult(
            question=effective_question,
            answerability=answerability,
            report=report,
            provider_used=provider_used,
            tool_trace=run_traces,
            diagnostic_events=self.providers.diagnostic_events[diag_start:],
        )

    def investigate_sync(
        self,
        question: str | None = None,
        *,
        incident_id: str | None = None,
        prefer_offline: bool = False,
    ) -> InvestigationRunResult:
        """Synchronous convenience wrapper for CLI and unittest callers."""
        return asyncio.run(
            self.investigate(
                question,
                incident_id=incident_id,
                prefer_offline=prefer_offline,
            )
        )
