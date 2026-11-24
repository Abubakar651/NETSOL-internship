"""SME Certification Gate and runtime OntologyRegistry (Auto-Ontology + Palantir)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel

from .schema import (
    DOMAIN_MODEL_MAP,
    ActionTypeDef,
    CertificationStatus,
    CertifiedMetricDef,
    LinkTypeDef,
    ObjectTypeDef,
    OntologyCatalog,
    OntologyLink,
)


class OntologyError(Exception):
    """Base error for ontology registry lookup and governance failures."""


class UncertifiedOntologyError(OntologyError):
    """Raised when an operation attempts to access an uncertified (DRAFT) definition."""


class UnknownOntologyEntityError(OntologyError):
    """Raised when an object type, link type, metric, or action is not in the catalog."""


class OntologyRegistry:
    """Enforces certification gates and loads validated objects and links from SQLite."""

    def __init__(self, catalog: OntologyCatalog, conn: sqlite3.Connection) -> None:
        self.catalog = catalog
        self.conn = conn
        self.certification_audit_log: list[dict[str, Any]] = []

    def get_certified_objects(self) -> dict[str, ObjectTypeDef]:
        return {
            name: obj
            for name, obj in self.catalog.objects.items()
            if obj.status == CertificationStatus.CERTIFIED
        }

    def get_draft_objects(self) -> dict[str, ObjectTypeDef]:
        return {
            name: obj
            for name, obj in self.catalog.objects.items()
            if obj.status == CertificationStatus.DRAFT
        }

    def get_certified_links(self) -> dict[str, LinkTypeDef]:
        return {
            link_id: link
            for link_id, link in self.catalog.links.items()
            if link.status == CertificationStatus.CERTIFIED
        }

    def get_certified_metrics(self) -> dict[str, CertifiedMetricDef]:
        return {
            metric_id: metric
            for metric_id, metric in self.catalog.metrics.items()
            if metric.status == CertificationStatus.CERTIFIED
        }

    def get_certified_actions(self) -> dict[str, ActionTypeDef]:
        return {
            action_id: action
            for action_id, action in self.catalog.actions.items()
            if action.status == CertificationStatus.CERTIFIED
        }

    def require_certified_object(self, object_type: str) -> ObjectTypeDef:
        obj_def = self.catalog.objects.get(object_type)
        if obj_def is None:
            raise UnknownOntologyEntityError(f"Unknown ObjectType '{object_type}'.")
        if obj_def.status != CertificationStatus.CERTIFIED:
            raise UncertifiedOntologyError(
                f"ObjectType '{object_type}' is in DRAFT status and must be certified before production queries."
            )
        return obj_def

    def require_certified_link(self, link_type_id: str) -> LinkTypeDef:
        link_def = self.catalog.links.get(link_type_id)
        if link_def is None:
            raise UnknownOntologyEntityError(f"Unknown LinkType '{link_type_id}'.")
        if link_def.status != CertificationStatus.CERTIFIED:
            raise UncertifiedOntologyError(
                f"LinkType '{link_type_id}' is in DRAFT status and must be certified before traversal."
            )
        return link_def

    def certify_definition(
        self,
        entity_kind: Literal["object", "link", "metric", "action"],
        entity_name: str,
        reviewer: str,
    ) -> dict[str, Any]:
        """Promote a DRAFT ontology definition to CERTIFIED and append an audit entry."""
        clean_reviewer = reviewer.strip()
        if not clean_reviewer:
            raise ValueError("Reviewer identifier must not be empty.")

        collection_map: dict[str, dict[str, Any]] = {
            "object": self.catalog.objects,
            "link": self.catalog.links,
            "metric": self.catalog.metrics,
            "action": self.catalog.actions,
        }
        if entity_kind not in collection_map:
            raise UnknownOntologyEntityError(f"Unsupported entity_kind '{entity_kind}'.")

        target_collection = collection_map[entity_kind]
        target = target_collection.get(entity_name)
        if target is None:
            raise UnknownOntologyEntityError(
                f"{entity_kind.capitalize()} '{entity_name}' does not exist in the OntologyCatalog."
            )

        previous_status = target.status.value
        target.status = CertificationStatus.CERTIFIED
        audit_entry = {
            "entity_kind": entity_kind,
            "entity_name": entity_name,
            "previous_status": previous_status,
            "new_status": CertificationStatus.CERTIFIED.value,
            "reviewer": clean_reviewer,
            "certified_at": datetime.now(timezone.utc).isoformat(),
        }
        self.certification_audit_log.append(audit_entry)
        return audit_entry

    @staticmethod
    def _decode_row(object_type: str, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        if object_type == "PullRequest":
            raw_files = data.get("changed_files")
            if isinstance(raw_files, str):
                data["changed_files"] = json.loads(raw_files)
            data["touches_db_config"] = bool(data.get("touches_db_config"))
            data["touches_schema"] = bool(data.get("touches_schema"))
        return data

    def load_certified_instances(self, object_type: str) -> list[BaseModel | dict[str, Any]]:
        """Load and validate all rows for a certified ObjectType."""
        obj_def = self.require_certified_object(object_type)
        rows = self.conn.execute(f'SELECT * FROM "{obj_def.source_table}"').fetchall()
        model_cls = DOMAIN_MODEL_MAP.get(object_type)

        results: list[BaseModel | dict[str, Any]] = []
        for row in rows:
            decoded = self._decode_row(object_type, row)
            if model_cls is not None:
                results.append(model_cls.model_validate(decoded))
            else:
                results.append(decoded)
        return results

    def load_certified_links(self, link_type_id: str) -> list[OntologyLink]:
        """Materialize directed OntologyLink edges for a certified LinkType."""
        link_def = self.require_certified_link(link_type_id)
        rows = self.conn.execute(f'SELECT * FROM "{link_def.source_table}"').fetchall()
        links: list[OntologyLink] = []
        for row in rows:
            source_id = row[link_def.join_column]
            target_id = row[link_def.target_column]
            if source_id is None or target_id is None:
                continue
            edge_props: dict[str, Any] = {}
            for prop_name in link_def.edge_properties:
                val = row[prop_name]
                if prop_name == "hard_dependency":
                    val = bool(val)
                edge_props[prop_name] = val
            links.append(
                OntologyLink(
                    link_type=link_def.id,
                    source_id=str(source_id),
                    target_id=str(target_id),
                    properties=edge_props,
                )
            )
        return links
