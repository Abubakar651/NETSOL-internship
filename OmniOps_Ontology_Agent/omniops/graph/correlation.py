"""Causal PullRequest deployment & schema migration correlation engine."""

from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

from .engine import SemanticGraphEngine

_SYMPTOM_TOKENS = (
    "pool",
    "connection",
    "fraud_risk_audit",
    "jsonb",
    "redis",
    "session",
    "migration",
    "timeout",
    "exhaust",
)


class SuspectDeployment(BaseModel):
    """Ranked Pull Request suspected of causing an operational incident."""

    model_config = ConfigDict(extra="forbid")

    pr_id: str
    title: str
    author: str
    target_service_id: str
    deployed_version: str
    minutes_before_incident: float
    suspect_score: float
    evidence_reasons: list[str] = Field(default_factory=list)
    recommended_rollback_version: str | None = None
    touches_db_config: bool
    touches_schema: bool
    migrates_database_id: str | None = None


class DeploymentCorrelationReport(BaseModel):
    """Correlation result ranking suspect deployments for a given Incident."""

    model_config = ConfigDict(extra="forbid")

    incident_id: str
    affected_service_id: str
    lookback_minutes: int
    suspect_deployments: list[SuspectDeployment] = Field(default_factory=list)
    top_suspect_pr_id: str | None = None


def correlate_suspect_deployments(
    engine: SemanticGraphEngine,
    incident_id: str,
    lookback_minutes: int = 120,
) -> DeploymentCorrelationReport:
    """Rank PullRequests within lookback_minutes of an Incident along its fault tree."""
    bounded_lookback = max(15, min(1440, lookback_minutes))
    incident = engine.get_raw_object("Incident", incident_id)
    affected_service_id = incident["affected_service_id"]
    detected_at = datetime.fromisoformat(incident["detected_at"])
    symptom_text = f"{incident['title']} {incident['symptom_summary']}".lower()

    # Gather fault tree: affected service + direct downstream CALLS services + direct downstream DBs.
    downstream_services = {
        edge["neighbor_id"]
        for edge in engine.get_neighbors(affected_service_id, link_types=["CALLS"], direction="out")
    }
    candidate_services = {affected_service_id, *downstream_services}

    downstream_db_map: dict[str, dict] = {}
    for edge in engine.get_neighbors(affected_service_id, link_types=["READS_WRITES"], direction="out"):
        if edge["neighbor"] is not None:
            downstream_db_map[edge["neighbor_id"]] = edge["neighbor"]

    suspects: list[SuspectDeployment] = []
    for pr in engine.list_objects("PullRequest"):
        target_svc_id = pr["target_service_id"]
        migrates_db_id = pr.get("migrates_database_id")

        in_service_tree = target_svc_id in candidate_services
        migrates_direct_db = migrates_db_id is not None and migrates_db_id in downstream_db_map
        if not in_service_tree and not migrates_direct_db:
            continue

        merged_at = datetime.fromisoformat(pr["merged_at"])
        minutes_before = round((detected_at - merged_at).total_seconds() / 60.0, 2)
        if minutes_before < 0 or minutes_before > bounded_lookback:
            continue

        score = 0.0
        reasons: list[str] = []

        if target_svc_id == affected_service_id:
            score += 0.40
            reasons.append(f"Deployed directly to affected service {affected_service_id} as {pr['deployed_version']}.")
        elif target_svc_id in downstream_services:
            score += 0.20
            reasons.append(f"Deployed to direct downstream dependency {target_svc_id}.")

        proximity_score = 0.25 * max(0.0, 1.0 - (minutes_before / bounded_lookback))
        score += proximity_score
        reasons.append(f"Merged {minutes_before:g} minutes prior to incident detection.")

        if pr["touches_db_config"] and any(
            db["status"] in ("HIGH_LOAD", "LOCKED") for db in downstream_db_map.values()
        ):
            score += 0.18
            stressed = sorted(
                db["id"] for db in downstream_db_map.values() if db["status"] in ("HIGH_LOAD", "LOCKED")
            )
            reasons.append(f"Modified DB/cache pool config while downstream datastore(s) {stressed} show saturation.")

        if pr["touches_schema"] or migrates_direct_db:
            score += 0.22
            db_note = f" targeting {migrates_db_id}" if migrates_db_id else ""
            reasons.append(f"Includes schema migration{db_note}.")

        if pr["risk_level"] == "HIGH":
            score += 0.08
        elif pr["risk_level"] == "MEDIUM":
            score += 0.04

        pr_text = f"{pr['title']} {' '.join(pr['changed_files'])}".lower()
        overlapping_tokens = [
            tok for tok in _SYMPTOM_TOKENS if tok in symptom_text and tok in pr_text
        ]
        if overlapping_tokens:
            score += 0.10
            reasons.append(f"Symptom keywords match PR changes ({', '.join(overlapping_tokens)}).")

        target_svc = engine.get_raw_object("Service", target_svc_id)
        suspects.append(
            SuspectDeployment(
                pr_id=pr["id"],
                title=pr["title"],
                author=pr["author"],
                target_service_id=target_svc_id,
                deployed_version=pr["deployed_version"],
                minutes_before_incident=minutes_before,
                suspect_score=round(min(0.99, score), 3),
                evidence_reasons=reasons,
                recommended_rollback_version=target_svc["last_stable_version"],
                touches_db_config=bool(pr["touches_db_config"]),
                touches_schema=bool(pr["touches_schema"]),
                migrates_database_id=migrates_db_id,
            )
        )

    suspects.sort(key=lambda item: (-item.suspect_score, item.minutes_before_incident, item.pr_id))
    return DeploymentCorrelationReport(
        incident_id=incident_id,
        affected_service_id=affected_service_id,
        lookback_minutes=bounded_lookback,
        suspect_deployments=suspects,
        top_suspect_pr_id=suspects[0].pr_id if suspects else None,
    )
