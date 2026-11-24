"""MCP Tool registry exposing validated Ontology queries, traversals, and governed actions."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from omniops.graph import (
    ActionPreconditionError,
    BranchError,
    GraphError,
    KineticActionExecutor,
    OmnigraphBranchManager,
    PolicyViolationError,
    compute_blast_radius,
    correlate_suspect_deployments,
)
from omniops.ontology import AnswerabilityChecker, OntologyError, OntologyRegistry


class UnknownToolError(KeyError):
    """Raised when an MCP client invokes a tool name not registered on the server."""


class ToolInputError(ValueError):
    """Raised when required MCP tool arguments are missing or invalid."""


class ToolCallTrace(BaseModel):
    """Telemetry record for every MCP tool execution."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    status: Literal["OK", "ERROR"]
    latency_ms: float
    result_summary: str
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    timestamp: str


_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "check_question_answerability",
        "description": "Pre-flight check verifying whether a user question maps to certified Ontology Objects, Links, Metrics, and Actions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "Natural-language question from the engineer."}
            },
            "required": ["question"],
        },
    },
    {
        "name": "get_ontology_object",
        "description": "Fetch a single certified Ontology object by type and primary key along with its inbound and outbound links.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "object_type": {
                    "type": "string",
                    "enum": ["Service", "Endpoint", "Database", "PullRequest", "Incident", "Team"],
                },
                "object_id": {"type": "string"},
                "branch": {"type": "string", "default": "main"},
            },
            "required": ["object_type", "object_id"],
        },
    },
    {
        "name": "search_ontology_objects",
        "description": "Hybrid exact-property filter and keyword search across a certified ObjectType.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "object_type": {
                    "type": "string",
                    "enum": ["Service", "Endpoint", "Database", "PullRequest", "Incident", "Team"],
                },
                "filters": {"type": "object"},
                "keyword": {"type": "string"},
                "branch": {"type": "string", "default": "main"},
            },
            "required": ["object_type"],
        },
    },
    {
        "name": "compute_blast_radius",
        "description": "Cycle-safe reverse BFS calculating upstream impacted services (by tier P0/P1/P2) and downstream dependencies.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "service_id": {"type": "string"},
                "max_depth": {"type": "integer", "default": 4, "minimum": 1, "maximum": 6},
                "branch": {"type": "string", "default": "main"},
            },
            "required": ["service_id"],
        },
    },
    {
        "name": "find_suspect_deployments",
        "description": "Correlate an active Incident and its downstream fault tree against recent PullRequest deployments.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "incident_id": {"type": "string"},
                "lookback_minutes": {"type": "integer", "default": 120, "minimum": 15, "maximum": 1440},
                "branch": {"type": "string", "default": "main"},
            },
            "required": ["incident_id"],
        },
    },
    {
        "name": "stage_governed_action",
        "description": "Evaluate Cedar policies and stage a Kinetic Action (TriggerSafeRollback, ScaleDatabaseConnectionPool, IsolateServiceTraffic) onto an isolated Omnigraph branch.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action_type": {
                    "type": "string",
                    "enum": ["TriggerSafeRollback", "ScaleDatabaseConnectionPool", "IsolateServiceTraffic"],
                },
                "parameters": {"type": "object"},
                "branch_name": {"type": "string"},
                "actor_role": {"type": "string", "default": "AutonomousAgent"},
            },
            "required": ["action_type", "parameters", "branch_name"],
        },
    },
    {
        "name": "approve_and_merge_branch",
        "description": "Human-gated 3-way merge of a staged Omnigraph incident branch into production 'main'.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "branch_name": {"type": "string"},
                "approver": {"type": "string"},
                "approval_note": {"type": "string", "default": "Approved via SRE Inbox"},
                "actor_role": {"type": "string", "default": "HumanSRE"},
            },
            "required": ["branch_name", "approver"],
        },
    },
]

_TOOL_NAMES = {tool["name"] for tool in _TOOL_DEFINITIONS}


class MCPToolRegistry:
    """Executes schema-validated MCP tools and records latency-tracked call traces."""

    def __init__(
        self,
        registry: OntologyRegistry,
        answerability: AnswerabilityChecker,
        branch_manager: OmnigraphBranchManager,
        action_executor: KineticActionExecutor,
    ) -> None:
        self.registry = registry
        self.answerability = answerability
        self.branch_manager = branch_manager
        self.action_executor = action_executor
        self._trace_log: list[ToolCallTrace] = []

    def list_tools(self) -> list[dict[str, Any]]:
        return [dict(tool) for tool in _TOOL_DEFINITIONS]

    def get_trace_log(self) -> list[ToolCallTrace]:
        return [entry.model_copy(deep=True) for entry in self._trace_log]

    def clear_trace_log(self) -> None:
        self._trace_log.clear()

    def _require_str(self, args: dict[str, Any], key: str) -> str:
        val = args.get(key)
        if not isinstance(val, str) or not val.strip():
            raise ToolInputError(f"Tool argument '{key}' must be a non-empty string.")
        return val.strip()

    def _require_dict(self, args: dict[str, Any], key: str) -> dict[str, Any]:
        val = args.get(key)
        if not isinstance(val, dict):
            raise ToolInputError(f"Tool argument '{key}' must be a JSON object.")
        return val

    def _summarize(self, name: str, data: dict[str, Any]) -> str:
        if name == "check_question_answerability":
            return f"answerable={data.get('answerable')} objects={data.get('matched_object_types')}"
        if name == "get_ontology_object":
            return f"fetched {data.get('id')}"
        if name == "search_ontology_objects":
            return f"matched {data.get('count', 0)} item(s)"
        if name == "compute_blast_radius":
            return (
                f"upstream={len(data.get('impacted_upstream_services', []))} "
                f"score={data.get('blast_radius_severity_score')}"
            )
        if name == "find_suspect_deployments":
            return f"top_suspect={data.get('top_suspect_pr_id')}"
        if name == "stage_governed_action":
            return f"branch={data.get('branch_name')} commit={data.get('commit_hash')}"
        if name == "approve_and_merge_branch":
            return f"merged={data.get('branch_name')} commit={data.get('commit_hash')}"
        return "completed"

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        if name not in _TOOL_NAMES:
            raise UnknownToolError(f"Unknown MCP tool '{name}'.")
        args = dict(arguments or {})

        # Pre-validate protocol argument shape before execution timer
        if name == "check_question_answerability":
            question = self._require_str(args, "question")
        elif name == "get_ontology_object":
            object_type = self._require_str(args, "object_type")
            object_id = self._require_str(args, "object_id")
            branch = str(args.get("branch", "main"))
        elif name == "search_ontology_objects":
            object_type = self._require_str(args, "object_type")
            filters = args.get("filters")
            if filters is not None and not isinstance(filters, dict):
                raise ToolInputError("Tool argument 'filters' must be an object or null.")
            keyword = args.get("keyword")
            if keyword is not None and not isinstance(keyword, str):
                raise ToolInputError("Tool argument 'keyword' must be a string or null.")
            branch = str(args.get("branch", "main"))
        elif name == "compute_blast_radius":
            service_id = self._require_str(args, "service_id")
            try:
                max_depth = int(args.get("max_depth", 4))
            except (TypeError, ValueError) as exc:
                raise ToolInputError("Tool argument 'max_depth' must be an integer.") from exc
            branch = str(args.get("branch", "main"))
        elif name == "find_suspect_deployments":
            incident_id = self._require_str(args, "incident_id")
            try:
                lookback_minutes = int(args.get("lookback_minutes", 120))
            except (TypeError, ValueError) as exc:
                raise ToolInputError("Tool argument 'lookback_minutes' must be an integer.") from exc
            branch = str(args.get("branch", "main"))
        elif name == "stage_governed_action":
            action_type = self._require_str(args, "action_type")
            parameters = self._require_dict(args, "parameters")
            branch_name = self._require_str(args, "branch_name")
            actor_role = str(args.get("actor_role", "AutonomousAgent"))
        elif name == "approve_and_merge_branch":
            branch_name = self._require_str(args, "branch_name")
            approver = self._require_str(args, "approver")
            approval_note = str(args.get("approval_note", "Approved via SRE Inbox"))
            actor_role = str(args.get("actor_role", "HumanSRE"))

        start = time.perf_counter()
        try:
            if name == "check_question_answerability":
                data = self.answerability.evaluate(question).model_dump(mode="json")
            elif name == "get_ontology_object":
                self.registry.require_certified_object(object_type)
                engine = self.branch_manager.get_engine(branch)
                data = engine.get_object(object_type, object_id)
            elif name == "search_ontology_objects":
                self.registry.require_certified_object(object_type)
                engine = self.branch_manager.get_engine(branch)
                items = engine.search_objects(object_type, filters=filters, keyword=keyword)
                data = {"object_type": object_type, "count": len(items), "items": items}
            elif name == "compute_blast_radius":
                engine = self.branch_manager.get_engine(branch)
                data = compute_blast_radius(engine, service_id, max_depth=max_depth).model_dump(
                    mode="json"
                )
            elif name == "find_suspect_deployments":
                engine = self.branch_manager.get_engine(branch)
                data = correlate_suspect_deployments(
                    engine, incident_id, lookback_minutes=lookback_minutes
                ).model_dump(mode="json")
            elif name == "stage_governed_action":
                data = self.action_executor.stage_action(
                    action_type=action_type,
                    parameters=parameters,
                    branch_name=branch_name,
                    actor_role=actor_role,
                ).model_dump(mode="json")
            else:
                data = self.action_executor.approve_and_merge(
                    branch_name=branch_name,
                    approver=approver,
                    approval_note=approval_note,
                    actor_role=actor_role,
                ).model_dump(mode="json")

            latency_ms = round((time.perf_counter() - start) * 1000.0, 3)
            self._trace_log.append(
                ToolCallTrace(
                    tool_name=name,
                    arguments=args,
                    status="OK",
                    latency_ms=latency_ms,
                    result_summary=self._summarize(name, data),
                    result=data,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            )
            return {
                "content": [{"type": "text", "text": json.dumps(data, indent=2)}],
                "isError": False,
                "data": data,
            }

        except (
            PolicyViolationError,
            ActionPreconditionError,
            BranchError,
            GraphError,
            OntologyError,
        ) as exc:
            latency_ms = round((time.perf_counter() - start) * 1000.0, 3)
            err_payload = {"error": str(exc), "error_type": type(exc).__name__}
            self._trace_log.append(
                ToolCallTrace(
                    tool_name=name,
                    arguments=args,
                    status="ERROR",
                    latency_ms=latency_ms,
                    result_summary=f"ERROR: {type(exc).__name__}",
                    result=err_payload,
                    error=str(exc),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            )
            return {
                "content": [{"type": "text", "text": json.dumps(err_payload, indent=2)}],
                "isError": True,
                "data": err_payload,
            }
