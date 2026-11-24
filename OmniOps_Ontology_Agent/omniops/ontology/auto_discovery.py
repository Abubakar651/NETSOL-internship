"""Auto-Ontology schema and foreign-key discovery scanner (NVIDIA Auto-Ontology pattern)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .schema import (
    ActionTypeDef,
    CertificationStatus,
    CertifiedMetricDef,
    LinkTypeDef,
    ObjectTypeDef,
    OntologyCatalog,
    PropertyDef,
    ServiceTier,
)

_CORE_OBJECT_SPECS: dict[str, dict[str, Any]] = {
    "raw_teams": {
        "name": "Team",
        "title_property": "name",
        "description": "Engineering squad responsible for service ownership and on-call escalation.",
        "synonyms": ["team", "squad", "oncall", "owner", "owners", "escalation"],
    },
    "raw_services": {
        "name": "Service",
        "title_property": "name",
        "description": "Production microservice exposing APIs and communicating with peers and databases.",
        "synonyms": ["service", "services", "microservice", "microservices", "api", "gateway", "worker", "tier"],
    },
    "raw_endpoints": {
        "name": "Endpoint",
        "title_property": "path",
        "description": "HTTP or gRPC route exposed by a microservice with latency and error-rate SLAs.",
        "synonyms": ["endpoint", "endpoints", "route", "routes", "url", "path", "sla"],
    },
    "raw_databases": {
        "name": "Database",
        "title_property": "name",
        "description": "Stateful persistence store or cache with active connection and CPU telemetry.",
        "synonyms": ["database", "databases", "db", "ledger", "postgres", "postgresql", "redis", "cache", "store"],
    },
    "raw_pull_requests": {
        "name": "PullRequest",
        "title_property": "title",
        "description": "Merged code or schema deployment targeting a microservice or database.",
        "synonyms": ["pull request", "pull requests", "pr", "prs", "deployment", "deployments", "commit", "release", "migration"],
    },
    "raw_incidents": {
        "name": "Incident",
        "title_property": "title",
        "description": "Active or historical operational alert linked to a failing microservice.",
        "synonyms": ["incident", "incidents", "outage", "alert", "sev1", "sev2", "failure", "failing", "500", "errors"],
    },
}

_JOIN_TABLE_LINKS: dict[str, LinkTypeDef] = {
    "raw_service_calls": LinkTypeDef(
        id="CALLS",
        source_object_type="Service",
        target_object_type="Service",
        cardinality="M:N",
        source_table="raw_service_calls",
        join_column="caller_service_id",
        target_column="target_service_id",
        description="Directed runtime dependency from a caller service to a downstream target service.",
        status=CertificationStatus.CERTIFIED,
        edge_properties=["call_type", "rpm", "hard_dependency"],
    ),
    "raw_service_databases": LinkTypeDef(
        id="READS_WRITES",
        source_object_type="Service",
        target_object_type="Database",
        cardinality="M:N",
        source_table="raw_service_databases",
        join_column="service_id",
        target_column="database_id",
        description="Connects a microservice to the downstream database or cache it reads/writes.",
        status=CertificationStatus.CERTIFIED,
        edge_properties=["access_mode", "pool_size"],
    ),
}

_FK_LINK_TEMPLATES: dict[tuple[str, str], dict[str, Any]] = {
    ("raw_endpoints", "service_id"): {
        "id": "EXPOSES",
        "source_object_type": "Service",
        "target_object_type": "Endpoint",
        "cardinality": "1:N",
        "join_column": "service_id",
        "target_column": "id",
        "description": "Maps API endpoints to their owning microservice.",
        "edge_properties": [],
    },
    ("raw_services", "owner_team_id"): {
        "id": "OWNED_BY",
        "source_object_type": "Service",
        "target_object_type": "Team",
        "cardinality": "N:1",
        "join_column": "id",
        "target_column": "owner_team_id",
        "description": "Associates a microservice with its owning on-call engineering team.",
        "edge_properties": [],
    },
    ("raw_pull_requests", "target_service_id"): {
        "id": "DEPLOYED_TO",
        "source_object_type": "PullRequest",
        "target_object_type": "Service",
        "cardinality": "N:1",
        "join_column": "id",
        "target_column": "target_service_id",
        "description": "Links a merged Pull Request deployment to its target microservice.",
        "edge_properties": ["deployed_version", "merged_at"],
    },
    ("raw_pull_requests", "migrates_database_id"): {
        "id": "MIGRATES_SCHEMA",
        "source_object_type": "PullRequest",
        "target_object_type": "Database",
        "cardinality": "M:N",
        "join_column": "id",
        "target_column": "migrates_database_id",
        "description": "Tracks schema migrations introduced by a Pull Request against a database.",
        "edge_properties": ["touches_schema"],
    },
    ("raw_incidents", "affected_service_id"): {
        "id": "AFFECTS",
        "source_object_type": "Incident",
        "target_object_type": "Service",
        "cardinality": "N:1",
        "join_column": "id",
        "target_column": "affected_service_id",
        "description": "Connects an active alert or outage to the primary affected microservice.",
        "edge_properties": ["severity", "status"],
    },
}

_DRAFT_SYNONYMS_BY_TABLE: dict[str, tuple[str, list[str]]] = {
    "raw_wifi_telemetry": (
        "WifiTelemetry",
        ["wifi", "wi-fi", "packet loss", "wireless", "sensor", "floor", "wifi telemetry"],
    ),
}


def _default_object_name(table_name: str) -> str:
    stripped = table_name.removeprefix("raw_")
    return "".join(part.capitalize() for part in stripped.split("_") if part)


class AutoOntologyScanner:
    """Introspects raw SQLite schemas and foreign keys to draft & register an OntologyCatalog."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def _list_tables(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        return [row[0] for row in rows]

    def _profile_properties(self, table_name: str) -> tuple[list[PropertyDef], str]:
        cols = self.conn.execute(f'PRAGMA table_info("{table_name}")').fetchall()
        sample_rows = self.conn.execute(f'SELECT * FROM "{table_name}" LIMIT 3').fetchall()

        properties: list[PropertyDef] = []
        primary_key = ""
        for col in cols:
            col_name = col["name"]
            is_pk = bool(col["pk"])
            if is_pk and not primary_key:
                primary_key = col_name
            samples: list[Any] = []
            for row in sample_rows:
                val = row[col_name]
                if val is not None and len(samples) < 3:
                    samples.append(val)
            properties.append(
                PropertyDef(
                    name=col_name,
                    data_type=col["type"] or "TEXT",
                    nullable=not bool(col["notnull"]),
                    is_primary_key=is_pk,
                    description=f"Auto-discovered column '{col_name}' from table '{table_name}'.",
                    sample_values=samples,
                )
            )
        if not primary_key and properties:
            primary_key = properties[0].name
        return properties, primary_key

    def _certified_metrics(self) -> dict[str, CertifiedMetricDef]:
        metrics = [
            CertifiedMetricDef(
                id="connection_saturation_ratio",
                name="Connection Saturation Ratio",
                target_object_type="Database",
                formula="active_connections / max_connections",
                threshold_description=">= 0.90 classifies database as CONNECTION_EXHAUSTED.",
            ),
            CertifiedMetricDef(
                id="blast_radius_severity_score",
                name="Blast Radius Severity Score",
                target_object_type="Service",
                formula="10 * count(upstream P0) + 4 * count(upstream P1) + 1 * count(upstream P2)",
                threshold_description="Higher scores prioritize immediate P0 incident escalation.",
            ),
            CertifiedMetricDef(
                id="deployment_suspect_score",
                name="Deployment Suspect Score",
                target_object_type="PullRequest",
                formula="temporal_proximity_weight + db_config_weight + schema_migration_weight",
                threshold_description="Ranks PRs merged within 120 minutes prior to an incident.",
            ),
        ]
        return {m.id: m for m in metrics}

    def _kinetic_actions(self) -> dict[str, ActionTypeDef]:
        actions = [
            ActionTypeDef(
                id="TriggerSafeRollback",
                name="TriggerSafeRollback",
                description="Reverts a Service from its faulty current_version to a stable target_version.",
                target_object_type="Service",
                parameters={
                    "service_id": "str",
                    "target_version": "str",
                    "incident_id": "str",
                    "justification": "str",
                },
                preconditions=[
                    "Service exists and status is CRITICAL or DEGRADED.",
                    "target_version differs from current_version.",
                    "Active Incident is linked to service_id.",
                ],
                side_effects=[
                    "Updates Service.current_version to target_version.",
                    "Restores Service.status to HEALTHY and resets error_rate_pct.",
                    "Marks Incident.status as MITIGATED.",
                ],
                requires_human_merge_for_tiers=[ServiceTier.P0, ServiceTier.P1],
            ),
            ActionTypeDef(
                id="ScaleDatabaseConnectionPool",
                name="ScaleDatabaseConnectionPool",
                description="Adjusts max_connections ceiling on a saturated Database.",
                target_object_type="Database",
                parameters={
                    "database_id": "str",
                    "new_max_connections": "int",
                    "incident_id": "str",
                    "justification": "str",
                },
                preconditions=[
                    "Database exists and 100 <= new_max_connections <= 2000.",
                ],
                side_effects=[
                    "Updates Database.max_connections and transitions status toward HEALTHY.",
                ],
                requires_human_merge_for_tiers=[ServiceTier.P0, ServiceTier.P1],
            ),
            ActionTypeDef(
                id="IsolateServiceTraffic",
                name="IsolateServiceTraffic",
                description="Enables circuit-breaker fallback between a caller and struggling target service.",
                target_object_type="Service",
                parameters={
                    "caller_service_id": "str",
                    "target_service_id": "str",
                    "fallback_mode": "str",
                    "justification": "str",
                },
                preconditions=[
                    "Both caller_service_id and target_service_id exist with a CALLS link.",
                ],
                side_effects=[
                    "Annotates CALLS link with circuit_breaker_open=True and fallback_mode.",
                ],
                requires_human_merge_for_tiers=[ServiceTier.P0, ServiceTier.P1],
            ),
            ActionTypeDef(
                id="CertifyOntologyDefinition",
                name="CertifyOntologyDefinition",
                description="Promotes an Auto-Ontology DRAFT object, link, metric, or action to CERTIFIED.",
                target_object_type="ObjectTypeDef",
                parameters={
                    "entity_kind": "str",
                    "entity_name": "str",
                    "reviewer": "str",
                },
                preconditions=[
                    "Definition exists in OntologyCatalog and reviewer is non-empty.",
                ],
                side_effects=[
                    "Sets certification status to CERTIFIED and records an audit entry.",
                ],
                requires_human_merge_for_tiers=[],
            ),
        ]
        return {a.id: a for a in actions}

    def discover(self) -> OntologyCatalog:
        """Scan SQLite tables and foreign keys to build the OntologyCatalog."""
        tables = self._list_tables()
        objects: dict[str, ObjectTypeDef] = {}
        links: dict[str, LinkTypeDef] = {}

        for table in tables:
            if table in _JOIN_TABLE_LINKS:
                link_def = _JOIN_TABLE_LINKS[table].model_copy(deep=True)
                links[link_def.id] = link_def
                continue

            props, pk = self._profile_properties(table)
            if table in _CORE_OBJECT_SPECS:
                spec = _CORE_OBJECT_SPECS[table]
                obj_def = ObjectTypeDef(
                    name=spec["name"],
                    source_table=table,
                    primary_key=pk,
                    title_property=spec["title_property"],
                    description=spec["description"],
                    status=CertificationStatus.CERTIFIED,
                    properties=props,
                    synonyms=list(spec["synonyms"]),
                )
            else:
                if table in _DRAFT_SYNONYMS_BY_TABLE:
                    obj_name, synonyms = _DRAFT_SYNONYMS_BY_TABLE[table]
                else:
                    obj_name = _default_object_name(table)
                    synonyms = [w for w in table.removeprefix("raw_").split("_") if w]
                title_prop = props[1].name if len(props) > 1 else pk
                obj_def = ObjectTypeDef(
                    name=obj_name,
                    source_table=table,
                    primary_key=pk,
                    title_property=title_prop,
                    description=f"Auto-discovered DRAFT concept from uncertified table '{table}'.",
                    status=CertificationStatus.DRAFT,
                    properties=props,
                    synonyms=list(synonyms),
                )
            objects[obj_def.name] = obj_def

        # Discover foreign-key links across all non-join tables.
        for table in tables:
            if table in _JOIN_TABLE_LINKS:
                continue
            fk_rows = self.conn.execute(f'PRAGMA foreign_key_list("{table}")').fetchall()
            for fk in fk_rows:
                key = (table, fk["from"])
                if key in _FK_LINK_TEMPLATES:
                    tpl = _FK_LINK_TEMPLATES[key]
                    link_def = LinkTypeDef(
                        id=tpl["id"],
                        source_object_type=tpl["source_object_type"],
                        target_object_type=tpl["target_object_type"],
                        cardinality=tpl["cardinality"],
                        source_table=table,
                        join_column=tpl["join_column"],
                        target_column=tpl["target_column"],
                        description=tpl["description"],
                        status=CertificationStatus.CERTIFIED,
                        edge_properties=list(tpl["edge_properties"]),
                    )
                    links[link_def.id] = link_def

        return OntologyCatalog(
            version="1.0.0",
            objects=objects,
            links=links,
            metrics=self._certified_metrics(),
            actions=self._kinetic_actions(),
        )

    @staticmethod
    def export_manifest(catalog: OntologyCatalog, path: str | Path) -> Path:
        """Persist the discovered OntologyCatalog as formatted JSON."""
        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(catalog.model_dump(mode="json"), indent=2), encoding="utf-8")
        return out_path
