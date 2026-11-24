"""In-memory directed property graph engine synchronized with the certified OntologyRegistry."""

from __future__ import annotations

import copy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from omniops.ontology import OntologyLink, OntologyRegistry


class GraphError(Exception):
    """Base exception for SemanticGraphEngine lookup errors."""


class ObjectNotFoundError(GraphError):
    """Raised when a requested Ontology ObjectType or Object ID does not exist."""


class GraphSnapshot(BaseModel):
    """Serializable, copy-on-write snapshot of all certified objects and directed links."""

    model_config = ConfigDict(extra="forbid")

    objects: dict[str, dict[str, dict[str, Any]]] = Field(default_factory=dict)
    links: list[OntologyLink] = Field(default_factory=list)

    def clone(self) -> GraphSnapshot:
        """Return an independent deep copy of this graph snapshot."""
        return GraphSnapshot(
            objects=copy.deepcopy(self.objects),
            links=[link.model_copy(deep=True) for link in self.links],
        )


def _stringify_value(val: Any) -> str:
    if isinstance(val, list):
        return " ".join(str(item) for item in val)
    return str(val)


class SemanticGraphEngine:
    """Provides typed object queries, hybrid search, and topology exports over a GraphSnapshot."""

    def __init__(self, snapshot: GraphSnapshot) -> None:
        self.snapshot = snapshot

    @classmethod
    def from_registry(cls, registry: OntologyRegistry) -> SemanticGraphEngine:
        """Materialize a SemanticGraphEngine from all certified types and links in the registry."""
        objects: dict[str, dict[str, dict[str, Any]]] = {}
        for obj_name, obj_def in registry.get_certified_objects().items():
            pk = obj_def.primary_key
            bucket: dict[str, dict[str, Any]] = {}
            for instance in registry.load_certified_instances(obj_name):
                data = instance.model_dump(mode="json") if isinstance(instance, BaseModel) else dict(instance)
                bucket[str(data[pk])] = data
            objects[obj_name] = bucket

        links: list[OntologyLink] = []
        for link_id in registry.get_certified_links():
            links.extend(registry.load_certified_links(link_id))

        return cls(GraphSnapshot(objects=objects, links=links))

    def find_object_type(self, object_id: str) -> str | None:
        """Return the ObjectType owning object_id, or None if not present."""
        for obj_type, bucket in self.snapshot.objects.items():
            if object_id in bucket:
                return obj_type
        return None

    def get_raw_object(self, object_type: str, object_id: str) -> dict[str, Any]:
        """Return a deep copy of an object's properties without link metadata."""
        bucket = self.snapshot.objects.get(object_type)
        if bucket is None:
            raise ObjectNotFoundError(f"Unknown or uncertified ObjectType '{object_type}'.")
        obj = bucket.get(object_id)
        if obj is None:
            raise ObjectNotFoundError(f"{object_type} '{object_id}' not found.")
        return copy.deepcopy(obj)

    def get_object(self, object_type: str, object_id: str) -> dict[str, Any]:
        """Return object properties enriched with inbound_links and outbound_links."""
        data = self.get_raw_object(object_type, object_id)
        data["inbound_links"] = [
            link.model_dump(mode="json")
            for link in self.snapshot.links
            if link.target_id == object_id
        ]
        data["outbound_links"] = [
            link.model_dump(mode="json")
            for link in self.snapshot.links
            if link.source_id == object_id
        ]
        return data

    def list_objects(self, object_type: str) -> list[dict[str, Any]]:
        """List all instances of a given certified ObjectType sorted by primary key."""
        bucket = self.snapshot.objects.get(object_type)
        if bucket is None:
            raise ObjectNotFoundError(f"Unknown or uncertified ObjectType '{object_type}'.")
        return [copy.deepcopy(bucket[key]) for key in sorted(bucket)]

    def search_objects(
        self,
        object_type: str,
        filters: dict[str, Any] | None = None,
        keyword: str | None = None,
    ) -> list[dict[str, Any]]:
        """Perform hybrid exact-property filtering and keyword substring search."""
        items = self.list_objects(object_type)
        results: list[dict[str, Any]] = []
        norm_kw = keyword.strip().lower() if keyword else ""

        for item in items:
            if filters:
                matched = True
                for f_key, f_val in filters.items():
                    if f_key not in item:
                        matched = False
                        break
                    item_val = item[f_key]
                    if isinstance(item_val, str) and isinstance(f_val, str):
                        if item_val.lower() != f_val.lower():
                            matched = False
                            break
                    elif item_val != f_val:
                        matched = False
                        break
                if not matched:
                    continue

            if norm_kw:
                haystack = " ".join(_stringify_value(v) for v in item.values() if v is not None).lower()
                if norm_kw not in haystack:
                    continue

            results.append(item)
        return results

    def get_neighbors(
        self,
        object_id: str,
        link_types: list[str] | None = None,
        direction: Literal["out", "in", "both"] = "both",
    ) -> list[dict[str, Any]]:
        """Return connected objects along specified link types and direction."""
        allowed_types = set(link_types) if link_types is not None else None
        neighbors: list[dict[str, Any]] = []

        for link in self.snapshot.links:
            if allowed_types is not None and link.link_type not in allowed_types:
                continue

            if direction in ("out", "both") and link.source_id == object_id:
                neighbor_type = self.find_object_type(link.target_id)
                neighbor_obj = (
                    self.get_raw_object(neighbor_type, link.target_id) if neighbor_type else None
                )
                neighbors.append(
                    {
                        "link_type": link.link_type,
                        "direction": "outbound",
                        "neighbor_id": link.target_id,
                        "neighbor_type": neighbor_type,
                        "neighbor": neighbor_obj,
                        "properties": copy.deepcopy(link.properties),
                    }
                )

            if direction in ("in", "both") and link.target_id == object_id:
                neighbor_type = self.find_object_type(link.source_id)
                neighbor_obj = (
                    self.get_raw_object(neighbor_type, link.source_id) if neighbor_type else None
                )
                neighbors.append(
                    {
                        "link_type": link.link_type,
                        "direction": "inbound",
                        "neighbor_id": link.source_id,
                        "neighbor_type": neighbor_type,
                        "neighbor": neighbor_obj,
                        "properties": copy.deepcopy(link.properties),
                    }
                )

        return neighbors

    def export_topology(self) -> dict[str, Any]:
        """Export visual topology nodes and edges for UI and MCP inspection."""
        node_types = ("Service", "Database", "PullRequest", "Incident")
        nodes: list[dict[str, Any]] = []
        for obj_type in node_types:
            for item in self.list_objects(obj_type):
                label = item.get("name") or item.get("title") or item["id"]
                nodes.append(
                    {
                        "id": item["id"],
                        "object_type": obj_type,
                        "label": label,
                        "data": item,
                    }
                )

        topology_links = {"CALLS", "READS_WRITES", "DEPLOYED_TO", "MIGRATES_SCHEMA", "AFFECTS"}
        edges = [
            link.model_dump(mode="json")
            for link in self.snapshot.links
            if link.link_type in topology_links
        ]
        return {"nodes": nodes, "edges": edges}
