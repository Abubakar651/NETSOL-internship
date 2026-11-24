"""MCP Resource providers exposing certified schemas, topology, branches, and audit logs."""

from __future__ import annotations

import json
from typing import Any

from omniops.graph import BranchNotFoundError, OmnigraphBranchManager
from omniops.ontology import OntologyRegistry


class ResourceNotFoundError(KeyError):
    """Raised when an MCP client requests an unknown resource URI or missing branch."""


_STATIC_RESOURCES: list[dict[str, str]] = [
    {
        "uri": "ontology://schema/certified",
        "name": "Certified Ontology Schema Catalog",
        "description": "All SME-certified ObjectTypes, LinkTypes, Metrics, and Kinetic Actions.",
        "mimeType": "application/json",
    },
    {
        "uri": "ontology://schema/drafts",
        "name": "Draft Auto-Ontology Discoveries",
        "description": "Uncertified DRAFT tables discovered by Auto-Ontology plus certification audit log.",
        "mimeType": "application/json",
    },
    {
        "uri": "ontology://topology/live",
        "name": "Live Production Topology",
        "description": "Nodes and directed dependency/PR/incident edges on branch 'main'.",
        "mimeType": "application/json",
    },
    {
        "uri": "ontology://branches/list",
        "name": "Omnigraph Branches",
        "description": "Active, merged, and rejected Omnigraph state branches.",
        "mimeType": "application/json",
    },
    {
        "uri": "ontology://audit/commits",
        "name": "Omnigraph Audit Commit Log",
        "description": "Immutable commit history across all Omnigraph branches.",
        "mimeType": "application/json",
    },
]

_RESOURCE_TEMPLATES: list[dict[str, str]] = [
    {
        "uriTemplate": "ontology://branches/{branch_name}/diff",
        "name": "Omnigraph Branch 3-Way Diff",
        "description": "Three-way structural diff comparing a staged incident branch against main.",
        "mimeType": "application/json",
    }
]


class MCPResourceProvider:
    """Serves read-only ontology:// MCP resources backed by Registry and Omnigraph."""

    def __init__(
        self,
        registry: OntologyRegistry,
        branch_manager: OmnigraphBranchManager,
    ) -> None:
        self.registry = registry
        self.branch_manager = branch_manager

    def list_resources(self) -> list[dict[str, str]]:
        return [dict(item) for item in _STATIC_RESOURCES]

    def list_resource_templates(self) -> list[dict[str, str]]:
        return [dict(item) for item in _RESOURCE_TEMPLATES]

    def read_resource(self, uri: str) -> dict[str, Any]:
        payload = self._resolve_payload(uri)
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": json.dumps(payload, indent=2),
                }
            ],
            "data": payload,
        }

    def _resolve_payload(self, uri: str) -> dict[str, Any]:
        if uri == "ontology://schema/certified":
            return {
                "version": self.registry.catalog.version,
                "objects": {
                    k: v.model_dump(mode="json")
                    for k, v in self.registry.get_certified_objects().items()
                },
                "links": {
                    k: v.model_dump(mode="json")
                    for k, v in self.registry.get_certified_links().items()
                },
                "metrics": {
                    k: v.model_dump(mode="json")
                    for k, v in self.registry.get_certified_metrics().items()
                },
                "actions": {
                    k: v.model_dump(mode="json")
                    for k, v in self.registry.get_certified_actions().items()
                },
            }

        if uri == "ontology://schema/drafts":
            return {
                "draft_objects": {
                    k: v.model_dump(mode="json")
                    for k, v in self.registry.get_draft_objects().items()
                },
                "certification_audit_log": list(self.registry.certification_audit_log),
            }

        if uri == "ontology://topology/live":
            return self.branch_manager.get_engine("main").export_topology()

        if uri == "ontology://branches/list":
            return {
                "branches": [b.model_dump(mode="json") for b in self.branch_manager.list_branches()]
            }

        if uri == "ontology://audit/commits":
            return {
                "commits": [c.model_dump(mode="json") for c in self.branch_manager.get_audit_log()]
            }

        prefix = "ontology://branches/"
        suffix = "/diff"
        if uri.startswith(prefix) and uri.endswith(suffix) and len(uri) > len(prefix) + len(suffix):
            branch_name = uri[len(prefix) : -len(suffix)]
            try:
                diff = self.branch_manager.compute_three_way_diff(branch_name, target_branch="main")
                return diff.model_dump(mode="json")
            except BranchNotFoundError as exc:
                raise ResourceNotFoundError(str(exc)) from exc

        raise ResourceNotFoundError(f"Unknown MCP resource URI '{uri}'.")
