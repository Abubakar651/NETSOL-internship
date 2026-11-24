"""Pydantic v2 schema definitions for OmniOps Semantic, Kinetic, and Discovery layers."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CertificationStatus(str, Enum):
    """SME approval status for ontology metadata definitions (Auto-Ontology pattern)."""

    DRAFT = "DRAFT"
    CERTIFIED = "CERTIFIED"


class ServiceTier(str, Enum):
    """Business criticality tier of a microservice."""

    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


class ServiceStatus(str, Enum):
    """Operational runtime status of a microservice."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"


class DatabaseEngine(str, Enum):
    """Supported persistence and cache engine types."""

    POSTGRESQL = "PostgreSQL"
    REDIS = "Redis"
    KAFKA = "Kafka"


class DatabaseStatus(str, Enum):
    """Operational status of a database or cache."""

    HEALTHY = "HEALTHY"
    HIGH_LOAD = "HIGH_LOAD"
    LOCKED = "LOCKED"


class RiskLevel(str, Enum):
    """Change-risk classification for a Pull Request."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class IncidentSeverity(str, Enum):
    """Incident severity level."""

    SEV1 = "SEV1"
    SEV2 = "SEV2"
    SEV3 = "SEV3"


class IncidentStatus(str, Enum):
    """Lifecycle status of an operational incident."""

    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    MITIGATED = "MITIGATED"
    RESOLVED = "RESOLVED"


class CallType(str, Enum):
    """Inter-service communication transport protocol."""

    SYNC_HTTP = "SYNC_HTTP"
    GRPC = "GRPC"
    ASYNC_EVENT = "ASYNC_EVENT"


class StrictModel(BaseModel):
    """Base model forbidding unexpected fields so ontology contracts remain strict."""

    model_config = ConfigDict(extra="forbid")


class PropertyDef(StrictModel):
    """Metadata describing one property on an Ontology ObjectType."""

    name: str
    data_type: str
    nullable: bool = False
    is_primary_key: bool = False
    description: str = ""
    sample_values: list[Any] = Field(default_factory=list)


class ObjectTypeDef(StrictModel):
    """Schema blueprint for a Palantir-style ObjectType backed by a physical table."""

    name: str
    source_table: str
    primary_key: str
    title_property: str
    description: str
    status: CertificationStatus = CertificationStatus.DRAFT
    properties: list[PropertyDef] = Field(default_factory=list)
    synonyms: list[str] = Field(default_factory=list)


class LinkTypeDef(StrictModel):
    """Schema blueprint for a directed LinkType connecting two ObjectTypes."""

    id: str
    source_object_type: str
    target_object_type: str
    cardinality: str
    source_table: str
    join_column: str
    target_column: str
    description: str
    status: CertificationStatus = CertificationStatus.DRAFT
    edge_properties: list[str] = Field(default_factory=list)


class CertifiedMetricDef(StrictModel):
    """Pre-certified analytical formula so agents never invent ad-hoc metrics."""

    id: str
    name: str
    target_object_type: str
    formula: str
    threshold_description: str
    status: CertificationStatus = CertificationStatus.CERTIFIED


class ActionTypeDef(StrictModel):
    """Governed Palantir Kinetic Action contract with pre-conditions and side effects."""

    id: str
    name: str
    description: str
    target_object_type: str
    parameters: dict[str, str]
    preconditions: list[str]
    side_effects: list[str]
    requires_human_merge_for_tiers: list[ServiceTier] = Field(
        default_factory=lambda: [ServiceTier.P0, ServiceTier.P1]
    )
    status: CertificationStatus = CertificationStatus.CERTIFIED


class OntologyCatalog(StrictModel):
    """Complete Auto-Ontology discovery and certification catalog."""

    version: str = "1.0.0"
    objects: dict[str, ObjectTypeDef] = Field(default_factory=dict)
    links: dict[str, LinkTypeDef] = Field(default_factory=dict)
    metrics: dict[str, CertifiedMetricDef] = Field(default_factory=dict)
    actions: dict[str, ActionTypeDef] = Field(default_factory=dict)


class AnswerabilityReport(StrictModel):
    """Pre-flight evaluation indicating whether a query maps to certified ontology concepts."""

    question: str
    answerable: bool
    confidence: float = Field(ge=0.0, le=1.0)
    matched_object_types: list[str] = Field(default_factory=list)
    matched_links: list[str] = Field(default_factory=list)
    matched_metrics: list[str] = Field(default_factory=list)
    matched_actions: list[str] = Field(default_factory=list)
    uncertified_concepts: list[str] = Field(default_factory=list)
    unmodeled_concepts: list[str] = Field(default_factory=list)
    guidance: str = ""


class TeamObject(StrictModel):
    """Engineering squad owning microservices and on-call escalation."""

    id: str = Field(pattern=r"^TEAM-[A-Z0-9-]+$")
    name: str
    slack_channel: str
    oncall_engineer: str
    escalation_policy: str


class ServiceObject(StrictModel):
    """Microservice instance in the Palantir Semantic Layer."""

    id: str = Field(pattern=r"^SVC-[A-Z0-9-]+$")
    name: str
    tier: ServiceTier
    status: ServiceStatus
    current_version: str
    last_stable_version: str
    error_rate_pct: float = Field(ge=0.0, le=100.0)
    p99_latency_ms: int = Field(ge=0)
    owner_team_id: str = Field(pattern=r"^TEAM-[A-Z0-9-]+$")


class EndpointObject(StrictModel):
    """HTTP or RPC API endpoint exposed by a microservice."""

    id: str = Field(pattern=r"^EP-[A-Z0-9-]+$")
    service_id: str = Field(pattern=r"^SVC-[A-Z0-9-]+$")
    method: str = Field(pattern=r"^(GET|POST|PUT|DELETE|PATCH)$")
    path: str = Field(pattern=r"^/.*$")
    p99_latency_ms: int = Field(ge=0)
    error_rate_pct: float = Field(ge=0.0, le=100.0)
    sla_latency_ms: int = Field(gt=0)


class DatabaseObject(StrictModel):
    """Stateful datastore or cache dependency with connection saturation metrics."""

    id: str = Field(pattern=r"^DB-[A-Z0-9-]+$")
    name: str
    engine: DatabaseEngine
    status: DatabaseStatus
    active_connections: int = Field(ge=0)
    max_connections: int = Field(gt=0)
    cpu_utilization_pct: float = Field(ge=0.0, le=100.0)
    schema_version: str

    @property
    def connection_saturation_ratio(self) -> float:
        """Certified metric: active_connections / max_connections."""
        return round(self.active_connections / self.max_connections, 4)

    @property
    def is_connection_exhausted(self) -> bool:
        """True when connection saturation meets or exceeds the 90% certified threshold."""
        return self.connection_saturation_ratio >= 0.90


class PullRequestObject(StrictModel):
    """Merged code or schema deployment tracked for causal incident correlation."""

    id: str = Field(pattern=r"^PR-[0-9]+$")
    title: str
    author: str
    target_service_id: str = Field(pattern=r"^SVC-[A-Z0-9-]+$")
    deployed_version: str
    merged_at: datetime
    changed_files: list[str]
    touches_db_config: bool
    touches_schema: bool
    risk_level: RiskLevel
    migrates_database_id: str | None = Field(default=None, pattern=r"^DB-[A-Z0-9-]+$")


class IncidentObject(StrictModel):
    """Active or historical operational alert affecting a microservice."""

    id: str = Field(pattern=r"^INC-[0-9]+$")
    title: str
    severity: IncidentSeverity
    status: IncidentStatus
    affected_service_id: str = Field(pattern=r"^SVC-[A-Z0-9-]+$")
    detected_at: datetime
    symptom_summary: str
    root_cause_pr_id: str | None = Field(default=None, pattern=r"^PR-[0-9]+$")


class OntologyLink(StrictModel):
    """Concrete directed edge between two certified Ontology objects."""

    link_type: str
    source_id: str
    target_id: str
    properties: dict[str, Any] = Field(default_factory=dict)


DOMAIN_MODEL_MAP: dict[str, type[BaseModel]] = {
    "Team": TeamObject,
    "Service": ServiceObject,
    "Endpoint": EndpointObject,
    "Database": DatabaseObject,
    "PullRequest": PullRequestObject,
    "Incident": IncidentObject,
}
