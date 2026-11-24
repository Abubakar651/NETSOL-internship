"""Cycle-safe multi-hop upstream blast-radius & downstream fault-tree traversal."""

from __future__ import annotations

from collections import deque
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .engine import SemanticGraphEngine

_TIER_ORDER = {"P0": 0, "P1": 1, "P2": 2}
_TIER_WEIGHT = {"P0": 10, "P1": 4, "P2": 1}


class ImpactedCaller(BaseModel):
    """Upstream service impacted when the target service fails."""

    model_config = ConfigDict(extra="forbid")

    service_id: str
    service_name: str
    tier: str
    status: str
    hop_distance: int
    dependency_path: list[str]
    hard_dependency: bool
    owner_team_id: str


class DownstreamDependency(BaseModel):
    """Direct downstream service or database that the failing service depends on."""

    model_config = ConfigDict(extra="forbid")

    object_id: str
    object_type: str
    name: str
    link_type: str
    status: str
    details: dict[str, Any] = Field(default_factory=dict)


class BlastRadiusReport(BaseModel):
    """Deterministic multi-hop blast radius and fault-tree report."""

    model_config = ConfigDict(extra="forbid")

    root_service_id: str
    root_service_name: str
    root_tier: str
    root_status: str
    max_depth: int
    impacted_upstream_services: list[ImpactedCaller] = Field(default_factory=list)
    downstream_dependencies: list[DownstreamDependency] = Field(default_factory=list)
    blast_radius_severity_score: int
    affected_team_ids: list[str] = Field(default_factory=list)
    cycle_detected: bool = False


def compute_blast_radius(
    engine: SemanticGraphEngine,
    service_id: str,
    max_depth: int = 4,
) -> BlastRadiusReport:
    """Run cycle-safe reverse BFS along CALLS edges and collect downstream dependencies."""
    bounded_depth = max(1, min(6, max_depth))
    root = engine.get_raw_object("Service", service_id)

    visited: set[str] = {service_id}
    queue: deque[tuple[str, int, list[str], bool]] = deque([(service_id, 0, [service_id], True)])
    impacted: list[ImpactedCaller] = []
    cycle_detected = False

    while queue:
        current_id, hop, path, chain_hard = queue.popleft()
        if hop >= bounded_depth:
            continue

        inbound = engine.get_neighbors(current_id, link_types=["CALLS"], direction="in")
        for edge in inbound:
            caller_id = edge["neighbor_id"]
            if caller_id in path:
                cycle_detected = True
            if caller_id in visited:
                continue

            caller = edge["neighbor"]
            if caller is None:
                continue

            edge_hard = bool(edge["properties"].get("hard_dependency", True))
            next_hard = chain_hard and edge_hard
            next_path = [caller_id, *path]
            next_hop = hop + 1

            visited.add(caller_id)
            impacted.append(
                ImpactedCaller(
                    service_id=caller_id,
                    service_name=caller["name"],
                    tier=caller["tier"],
                    status=caller["status"],
                    hop_distance=next_hop,
                    dependency_path=next_path,
                    hard_dependency=next_hard,
                    owner_team_id=caller["owner_team_id"],
                )
            )
            queue.append((caller_id, next_hop, next_path, next_hard))

    impacted.sort(
        key=lambda item: (item.hop_distance, _TIER_ORDER.get(item.tier, 3), item.service_id)
    )

    downstream: list[DownstreamDependency] = []
    outbound = engine.get_neighbors(service_id, link_types=["CALLS", "READS_WRITES"], direction="out")
    for edge in outbound:
        dep_obj = edge["neighbor"]
        dep_type = edge["neighbor_type"]
        if dep_obj is None or dep_type is None:
            continue
        details = dict(edge["properties"])
        if dep_type == "Database":
            sat_ratio = round(dep_obj["active_connections"] / dep_obj["max_connections"], 4)
            details.update(
                {
                    "engine": dep_obj["engine"],
                    "active_connections": dep_obj["active_connections"],
                    "max_connections": dep_obj["max_connections"],
                    "connection_saturation_ratio": sat_ratio,
                    "is_connection_exhausted": sat_ratio >= 0.90,
                    "cpu_utilization_pct": dep_obj["cpu_utilization_pct"],
                }
            )
        elif dep_type == "Service":
            details.update(
                {
                    "tier": dep_obj["tier"],
                    "error_rate_pct": dep_obj["error_rate_pct"],
                    "p99_latency_ms": dep_obj["p99_latency_ms"],
                }
            )
        downstream.append(
            DownstreamDependency(
                object_id=dep_obj["id"],
                object_type=dep_type,
                name=dep_obj["name"],
                link_type=edge["link_type"],
                status=dep_obj["status"],
                details=details,
            )
        )

    downstream.sort(key=lambda item: (item.object_type, item.object_id))

    severity_score = sum(_TIER_WEIGHT.get(caller.tier, 1) for caller in impacted)
    affected_teams = sorted(
        {root["owner_team_id"], *(caller.owner_team_id for caller in impacted)}
    )

    return BlastRadiusReport(
        root_service_id=root["id"],
        root_service_name=root["name"],
        root_tier=root["tier"],
        root_status=root["status"],
        max_depth=bounded_depth,
        impacted_upstream_services=impacted,
        downstream_dependencies=downstream,
        blast_radius_severity_score=severity_score,
        affected_team_ids=affected_teams,
        cycle_detected=cycle_detected,
    )
