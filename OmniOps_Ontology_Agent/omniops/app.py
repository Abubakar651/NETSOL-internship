"""FastAPI backend serving the Apple Liquid Glass UI, REST API, and /api/mcp JSON-RPC endpoint."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from omniops.agent import InvestigationRunner, ReasoningProviders, Settings, load_settings
from omniops.graph import (
    BranchError,
    BranchNotFoundError,
    ObjectNotFoundError,
    PolicyViolationError,
    compute_blast_radius,
)
from omniops.mcp import OmniOpsMCPServer
from omniops.ontology import OntologyError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = PROJECT_ROOT / "web"


class CertifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_kind: Literal["object", "link", "metric", "action"] = "object"
    entity_name: str = Field(min_length=1)
    reviewer: str = Field(default="senior.architect", min_length=1)


class InvestigateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str | None = None
    incident_id: str | None = None
    prefer_offline: bool = False


class ApproveBranchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    branch_name: str = Field(min_length=1)
    approver: str = Field(default="senior.sre@netsol.example", min_length=1)
    approval_note: str = Field(default="Approved via Operations Center Inbox", min_length=1)


class RejectBranchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    branch_name: str = Field(min_length=1)
    reviewer: str = Field(default="senior.sre@netsol.example", min_length=1)
    reason: str = Field(default="Rejected via Operations Center Inbox")


class AppState:
    """In-process stateful container holding the active Ontology, Omnigraph, MCP, and Agent Runner."""

    def __init__(
        self,
        settings: Settings | None = None,
        providers: ReasoningProviders | None = None,
    ) -> None:
        self.settings = settings or load_settings()
        self.providers = providers
        self.mcp = OmniOpsMCPServer.from_seeded_database()
        self.runner = InvestigationRunner(
            self.mcp,
            settings=self.settings,
            providers=self.providers,
        )

    def reset(self) -> None:
        self.mcp.close()
        self.mcp = OmniOpsMCPServer.from_seeded_database()
        self.runner = InvestigationRunner(
            self.mcp,
            settings=self.settings,
            providers=self.providers,
        )


def _build_topology_payload(mcp: OmniOpsMCPServer, branch: str = "main") -> dict[str, Any]:
    engine = mcp.branch_manager.get_engine(branch)
    topology = engine.export_topology()
    services = engine.list_objects("Service")
    incidents = engine.list_objects("Incident")
    branches = mcp.branch_manager.list_branches()

    pending_branches = sum(
        1 for b in branches if b.branch_name != "main" and b.status == "ACTIVE"
    )
    kpis = {
        "total_services": len(services),
        "healthy_services": sum(1 for s in services if s["status"] == "HEALTHY"),
        "degraded_services": sum(1 for s in services if s["status"] == "DEGRADED"),
        "critical_services": sum(1 for s in services if s["status"] == "CRITICAL"),
        "open_incidents": sum(1 for i in incidents if i["status"] == "OPEN"),
        "mitigated_incidents": sum(1 for i in incidents if i["status"] in ("MITIGATED", "RESOLVED")),
        "pending_branches": pending_branches,
        "certified_objects": len(mcp.registry.get_certified_objects()),
        "draft_objects": len(mcp.registry.get_draft_objects()),
    }
    return {
        "branch": branch,
        "nodes": topology["nodes"],
        "edges": topology["edges"],
        "incidents": incidents,
        "kpis": kpis,
    }


def _build_schema_payload(mcp: OmniOpsMCPServer) -> dict[str, Any]:
    certified = mcp.read_resource("ontology://schema/certified")["data"]
    drafts = mcp.read_resource("ontology://schema/drafts")["data"]
    return {
        **certified,
        "draft_objects": drafts["draft_objects"],
        "certification_audit_log": drafts["certification_audit_log"],
    }


def create_app(
    settings: Settings | None = None,
    *,
    providers: ReasoningProviders | None = None,
) -> FastAPI:
    """Create and configure the OmniOps FastAPI application."""
    state = AppState(settings=settings, providers=providers)
    app = FastAPI(title="OmniOps Ontology Operations Center", version="1.0.0")
    app.state.omniops = state

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-store"})

    @app.get("/styles.css")
    async def styles() -> FileResponse:
        return FileResponse(
            WEB_DIR / "styles.css",
            media_type="text/css",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/app.js")
    async def script() -> FileResponse:
        return FileResponse(
            WEB_DIR / "app.js",
            media_type="application/javascript",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/config")
    async def get_config() -> dict[str, Any]:
        cfg = state.settings
        return {
            "app_name": "OmniOps Ontology Agent",
            "version": "1.0.0",
            "jira_project_key": cfg.jira_project_key,
            "providers": {
                "gemini": bool(cfg.gemini_key),
                "groq": bool(cfg.groq_key),
                "openrouter": bool(cfg.openrouter_key),
                "offline_reasoner": True,
            },
            "models": {
                "gemini": cfg.gemini_model,
                "groq": cfg.groq_reasoning_model,
                "openrouter": cfg.openrouter_model,
            },
        }

    @app.get("/api/ontology/schema")
    async def get_ontology_schema() -> dict[str, Any]:
        return _build_schema_payload(state.mcp)

    @app.post("/api/ontology/certify")
    async def certify_ontology(req: CertifyRequest) -> dict[str, Any]:
        try:
            audit_entry = state.mcp.registry.certify_definition(
                req.entity_kind,
                req.entity_name,
                req.reviewer,
            )
            if req.entity_kind == "object":
                obj_def = state.mcp.registry.catalog.objects[req.entity_name]
                rows = state.mcp.registry.load_certified_instances(req.entity_name)
                pk = obj_def.primary_key
                bucket = {
                    str((r.model_dump(mode="json") if isinstance(r, BaseModel) else r)[pk]): (
                        r.model_dump(mode="json") if isinstance(r, BaseModel) else dict(r)
                    )
                    for r in rows
                }
                state.mcp.branch_manager.commit_mutation(
                    "main",
                    lambda snap: snap.objects.__setitem__(req.entity_name, bucket),
                    author=req.reviewer,
                    actor_role="HumanSRE",
                    action_type="CertifyOntologyDefinition",
                    summary=f"Certified {req.entity_name} ({len(bucket)} records synced to main).",
                )
            return {
                "audit_entry": audit_entry,
                "schema": _build_schema_payload(state.mcp),
            }
        except (OntologyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/topology")
    async def get_topology(branch: str = Query(default="main")) -> dict[str, Any]:
        try:
            return _build_topology_payload(state.mcp, branch=branch)
        except BranchNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/blast-radius/{service_id}")
    async def get_blast_radius(
        service_id: str,
        max_depth: int = Query(default=4, ge=1, le=6),
        branch: str = Query(default="main"),
    ) -> dict[str, Any]:
        try:
            engine = state.mcp.branch_manager.get_engine(branch)
            report = compute_blast_radius(engine, service_id, max_depth=max_depth)
            return report.model_dump(mode="json")
        except (ObjectNotFoundError, BranchNotFoundError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/investigate")
    async def run_investigation(req: InvestigateRequest) -> dict[str, Any]:
        if not req.question and not req.incident_id:
            raise HTTPException(status_code=400, detail="Provide 'question' or 'incident_id'.")
        try:
            result = await state.runner.investigate(
                req.question,
                incident_id=req.incident_id,
                prefer_offline=req.prefer_offline,
            )
            return result.model_dump(mode="json")
        except (ObjectNotFoundError, BranchNotFoundError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (OntologyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/branches")
    async def list_branches() -> dict[str, Any]:
        branches_out: list[dict[str, Any]] = []
        for branch in state.mcp.branch_manager.list_branches():
            entry = branch.model_dump(mode="json")
            if branch.branch_name != "main":
                diff = state.mcp.branch_manager.compute_three_way_diff(
                    branch.branch_name, target_branch="main"
                )
                entry["three_way_diff"] = diff.model_dump(mode="json")
            else:
                entry["three_way_diff"] = None
            branches_out.append(entry)

        commits = [c.model_dump(mode="json") for c in state.mcp.branch_manager.get_audit_log()]
        return {"branches": branches_out, "commits": commits}

    @app.post("/api/branches/approve")
    async def approve_branch(req: ApproveBranchRequest) -> dict[str, Any]:
        res = state.mcp.call_tool(
            "approve_and_merge_branch",
            {
                "branch_name": req.branch_name,
                "approver": req.approver,
                "approval_note": req.approval_note,
                "actor_role": "HumanSRE",
            },
        )
        if res["isError"]:
            err = res["data"]
            err_type = err.get("error_type", "")
            status = 403 if err_type == "PolicyViolationError" else (404 if "NotFound" in err_type else 400)
            raise HTTPException(status_code=status, detail=err.get("error", "Merge failed"))
        return {
            "commit": res["data"],
            "topology": _build_topology_payload(state.mcp, branch="main"),
        }

    @app.post("/api/branches/reject")
    async def reject_branch(req: RejectBranchRequest) -> dict[str, Any]:
        try:
            branch = state.mcp.branch_manager.reject_branch(
                req.branch_name,
                reviewer=req.reviewer,
                reason=req.reason,
            )
            return {
                "branch": branch.model_dump(mode="json"),
                "topology": _build_topology_payload(state.mcp, branch="main"),
            }
        except BranchNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (BranchError, PolicyViolationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/reset")
    async def reset_demo() -> dict[str, Any]:
        state.reset()
        return {
            "status": "reset",
            "topology": _build_topology_payload(state.mcp, branch="main"),
            "schema": _build_schema_payload(state.mcp),
        }

    @app.post("/api/mcp")
    async def mcp_jsonrpc(request: Request) -> Response:
        try:
            payload = await request.json()
        except ValueError:
            return JSONResponse(
                {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error."}},
                status_code=400,
            )
        resp = state.mcp.handle_jsonrpc(payload)
        if resp is None:
            return Response(status_code=204)
        return JSONResponse(resp)

    return app


app = create_app()
