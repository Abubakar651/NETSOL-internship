"""Omnigraph Git-style copy-on-write state branching, 3-way diff, and merge audit log."""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field

from omniops.ontology import OntologyLink

from .engine import GraphSnapshot, SemanticGraphEngine


class BranchError(Exception):
    """Base error for Omnigraph version-control operations."""


class BranchExistsError(BranchError):
    """Raised when attempting to create a branch name that already exists."""


class BranchNotFoundError(BranchError):
    """Raised when referencing an unknown branch."""


class MergeConflictError(BranchError):
    """Raised when 3-way diff detects conflicting concurrent edits on target branch."""


class StateDiffItem(BaseModel):
    """Single field-level or link-level change between two GraphSnapshots."""

    model_config = ConfigDict(extra="forbid")

    object_type: str
    object_id: str
    field: str
    base_value: Any
    branch_value: Any


class CommitRecord(BaseModel):
    """Immutable audit log entry representing one graph state commit."""

    model_config = ConfigDict(extra="forbid")

    commit_hash: str
    parent_hash: str | None
    branch_name: str
    author: str
    actor_role: str
    action_type: str
    summary: str
    timestamp: str
    diff: list[StateDiffItem] = Field(default_factory=list)


class BranchInfo(BaseModel):
    """Metadata describing an Omnigraph branch."""

    model_config = ConfigDict(extra="forbid")

    branch_name: str
    base_commit_hash: str
    head_commit_hash: str
    created_by: str
    status: Literal["ACTIVE", "MERGED", "REJECTED"]
    pending_action: dict[str, Any] | None = None


class ThreeWayDiffReport(BaseModel):
    """Result of comparing base -> branch against base -> main."""

    model_config = ConfigDict(extra="forbid")

    branch_name: str
    base_commit_hash: str
    main_head_hash: str
    branch_head_hash: str
    changes: list[StateDiffItem] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    can_merge: bool


def _link_key(link: OntologyLink) -> str:
    return f"{link.source_id}->{link.target_id}"


def _compute_snapshot_diff(base: GraphSnapshot, updated: GraphSnapshot) -> list[StateDiffItem]:
    diffs: list[StateDiffItem] = []

    all_types = sorted(set(base.objects) | set(updated.objects))
    for obj_type in all_types:
        base_bucket = base.objects.get(obj_type, {})
        upd_bucket = updated.objects.get(obj_type, {})
        all_ids = sorted(set(base_bucket) | set(upd_bucket))
        for obj_id in all_ids:
            base_obj = base_bucket.get(obj_id)
            upd_obj = upd_bucket.get(obj_id)
            if base_obj is None:
                diffs.append(
                    StateDiffItem(
                        object_type=obj_type,
                        object_id=obj_id,
                        field="__created__",
                        base_value=None,
                        branch_value=copy.deepcopy(upd_obj),
                    )
                )
                continue
            if upd_obj is None:
                diffs.append(
                    StateDiffItem(
                        object_type=obj_type,
                        object_id=obj_id,
                        field="__deleted__",
                        base_value=copy.deepcopy(base_obj),
                        branch_value=None,
                    )
                )
                continue

            all_fields = sorted(set(base_obj) | set(upd_obj))
            for field in all_fields:
                b_val = base_obj.get(field)
                u_val = upd_obj.get(field)
                if b_val != u_val:
                    diffs.append(
                        StateDiffItem(
                            object_type=obj_type,
                            object_id=obj_id,
                            field=field,
                            base_value=copy.deepcopy(b_val),
                            branch_value=copy.deepcopy(u_val),
                        )
                    )

    base_links = {(link.link_type, _link_key(link)): link.properties for link in base.links}
    upd_links = {(link.link_type, _link_key(link)): link.properties for link in updated.links}
    for key in sorted(set(base_links) | set(upd_links)):
        link_type, edge_id = key
        b_props = base_links.get(key)
        u_props = upd_links.get(key)
        if b_props != u_props:
            diffs.append(
                StateDiffItem(
                    object_type=f"Link:{link_type}",
                    object_id=edge_id,
                    field="properties",
                    base_value=copy.deepcopy(b_props),
                    branch_value=copy.deepcopy(u_props),
                )
            )

    return diffs


def _apply_diff_to_snapshot(snapshot: GraphSnapshot, changes: list[StateDiffItem]) -> None:
    for item in changes:
        if item.object_type.startswith("Link:"):
            link_type = item.object_type.split(":", 1)[1]
            src_id, tgt_id = item.object_id.split("->", 1)
            existing = next(
                (
                    link
                    for link in snapshot.links
                    if link.link_type == link_type
                    and link.source_id == src_id
                    and link.target_id == tgt_id
                ),
                None,
            )
            if item.branch_value is None and existing is not None:
                snapshot.links.remove(existing)
            elif existing is not None:
                existing.properties = copy.deepcopy(item.branch_value)
            elif item.branch_value is not None:
                snapshot.links.append(
                    OntologyLink(
                        link_type=link_type,
                        source_id=src_id,
                        target_id=tgt_id,
                        properties=copy.deepcopy(item.branch_value),
                    )
                )
            continue

        bucket = snapshot.objects.setdefault(item.object_type, {})
        if item.field == "__created__":
            bucket[item.object_id] = copy.deepcopy(item.branch_value)
        elif item.field == "__deleted__":
            bucket.pop(item.object_id, None)
        else:
            bucket[item.object_id][item.field] = copy.deepcopy(item.branch_value)


def _hash_commit(
    parent_hash: str | None,
    branch_name: str,
    action_type: str,
    snapshot: GraphSnapshot,
    seq: int,
) -> str:
    payload = {
        "seq": seq,
        "parent": parent_hash,
        "branch": branch_name,
        "action": action_type,
        "snapshot": snapshot.model_dump(mode="json"),
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return digest[:12]


class OmnigraphBranchManager:
    """Manages Git-style branches, commits, 3-way diffs, and merges over GraphSnapshots."""

    def __init__(self, initial_snapshot: GraphSnapshot, author: str = "system") -> None:
        self.commit_snapshots: dict[str, GraphSnapshot] = {}
        self.branches: dict[str, BranchInfo] = {}
        self.commit_log: list[CommitRecord] = []

        root_snapshot = initial_snapshot.clone()
        root_hash = _hash_commit(None, "main", "InitializeOntologyGraph", root_snapshot, seq=0)
        self.commit_snapshots[root_hash] = root_snapshot
        self.branches["main"] = BranchInfo(
            branch_name="main",
            base_commit_hash=root_hash,
            head_commit_hash=root_hash,
            created_by=author,
            status="ACTIVE",
        )
        self.commit_log.append(
            CommitRecord(
                commit_hash=root_hash,
                parent_hash=None,
                branch_name="main",
                author=author,
                actor_role="System",
                action_type="InitializeOntologyGraph",
                summary="Initial certified ontology graph snapshot on main.",
                timestamp=datetime.now(timezone.utc).isoformat(),
                diff=[],
            )
        )

    def _require_branch(self, branch_name: str) -> BranchInfo:
        info = self.branches.get(branch_name)
        if info is None:
            raise BranchNotFoundError(f"Branch '{branch_name}' does not exist.")
        return info

    def get_snapshot(self, branch_name: str = "main") -> GraphSnapshot:
        info = self._require_branch(branch_name)
        return self.commit_snapshots[info.head_commit_hash].clone()

    def get_engine(self, branch_name: str = "main") -> SemanticGraphEngine:
        return SemanticGraphEngine(self.get_snapshot(branch_name))

    def create_branch(
        self,
        branch_name: str,
        author: str,
        base_branch: str = "main",
    ) -> BranchInfo:
        if branch_name in self.branches:
            raise BranchExistsError(f"Branch '{branch_name}' already exists.")
        base_info = self._require_branch(base_branch)
        branch = BranchInfo(
            branch_name=branch_name,
            base_commit_hash=base_info.head_commit_hash,
            head_commit_hash=base_info.head_commit_hash,
            created_by=author,
            status="ACTIVE",
        )
        self.branches[branch_name] = branch
        return branch.model_copy(deep=True)

    def commit_mutation(
        self,
        branch_name: str,
        mutator: Callable[[GraphSnapshot], None],
        *,
        author: str,
        actor_role: str,
        action_type: str,
        summary: str,
        pending_action: dict[str, Any] | None = None,
    ) -> CommitRecord:
        info = self._require_branch(branch_name)
        if info.status != "ACTIVE":
            raise BranchError(f"Cannot commit to branch '{branch_name}' with status '{info.status}'.")

        parent_hash = info.head_commit_hash
        parent_snap = self.commit_snapshots[parent_hash]
        next_snap = parent_snap.clone()
        mutator(next_snap)

        diff = _compute_snapshot_diff(parent_snap, next_snap)
        commit_hash = _hash_commit(
            parent_hash, branch_name, action_type, next_snap, seq=len(self.commit_log)
        )
        self.commit_snapshots[commit_hash] = next_snap
        info.head_commit_hash = commit_hash
        if pending_action is not None:
            info.pending_action = copy.deepcopy(pending_action)

        record = CommitRecord(
            commit_hash=commit_hash,
            parent_hash=parent_hash,
            branch_name=branch_name,
            author=author,
            actor_role=actor_role,
            action_type=action_type,
            summary=summary,
            timestamp=datetime.now(timezone.utc).isoformat(),
            diff=diff,
        )
        self.commit_log.append(record)
        return record.model_copy(deep=True)

    def compute_three_way_diff(
        self,
        branch_name: str,
        target_branch: str = "main",
    ) -> ThreeWayDiffReport:
        branch_info = self._require_branch(branch_name)
        target_info = self._require_branch(target_branch)

        base_snap = self.commit_snapshots[branch_info.base_commit_hash]
        branch_snap = self.commit_snapshots[branch_info.head_commit_hash]
        target_snap = self.commit_snapshots[target_info.head_commit_hash]

        branch_diffs = _compute_snapshot_diff(base_snap, branch_snap)
        target_diffs = _compute_snapshot_diff(base_snap, target_snap)

        target_map = {(d.object_type, d.object_id, d.field): d for d in target_diffs}
        conflicts: list[str] = []
        for item in branch_diffs:
            key = (item.object_type, item.object_id, item.field)
            if key in target_map and target_map[key].branch_value != item.branch_value:
                conflicts.append(
                    f"Conflict on {item.object_type} '{item.object_id}.{item.field}': "
                    f"target has {target_map[key].branch_value!r}, branch proposes {item.branch_value!r}."
                )

        return ThreeWayDiffReport(
            branch_name=branch_name,
            base_commit_hash=branch_info.base_commit_hash,
            main_head_hash=target_info.head_commit_hash,
            branch_head_hash=branch_info.head_commit_hash,
            changes=branch_diffs,
            conflicts=conflicts,
            can_merge=len(conflicts) == 0,
        )

    def merge_branch(
        self,
        branch_name: str,
        approver: str,
        approval_note: str = "",
        target_branch: str = "main",
    ) -> CommitRecord:
        if branch_name == target_branch:
            raise BranchError("Cannot merge a branch into itself.")
        branch_info = self._require_branch(branch_name)
        if branch_info.status != "ACTIVE":
            raise BranchError(f"Branch '{branch_name}' is already '{branch_info.status}'.")

        report = self.compute_three_way_diff(branch_name, target_branch=target_branch)
        if not report.can_merge:
            raise MergeConflictError("; ".join(report.conflicts))

        def apply_merge(snap: GraphSnapshot) -> None:
            _apply_diff_to_snapshot(snap, report.changes)

        summary = f"Merge branch '{branch_name}' into '{target_branch}' approved by {approver}"
        if approval_note:
            summary = f"{summary} ({approval_note})"

        commit = self.commit_mutation(
            target_branch,
            apply_merge,
            author=approver,
            actor_role="HumanSRE",
            action_type="MergeBranchToMain",
            summary=summary,
        )
        branch_info.status = "MERGED"
        return commit

    def reject_branch(
        self,
        branch_name: str,
        reviewer: str,
        reason: str = "",
    ) -> BranchInfo:
        if branch_name == "main":
            raise BranchError("Cannot reject the main production branch.")
        branch_info = self._require_branch(branch_name)
        if branch_info.status != "ACTIVE":
            raise BranchError(f"Branch '{branch_name}' is already '{branch_info.status}'.")
        branch_info.status = "REJECTED"
        self.commit_log.append(
            CommitRecord(
                commit_hash=branch_info.head_commit_hash,
                parent_hash=branch_info.base_commit_hash,
                branch_name=branch_name,
                author=reviewer,
                actor_role="HumanSRE",
                action_type="RejectBranch",
                summary=f"Rejected branch '{branch_name}': {reason or 'No reason specified.'}",
                timestamp=datetime.now(timezone.utc).isoformat(),
                diff=[],
            )
        )
        return branch_info.model_copy(deep=True)

    def list_branches(self) -> list[BranchInfo]:
        return [info.model_copy(deep=True) for info in self.branches.values()]

    def get_audit_log(self) -> list[CommitRecord]:
        return [record.model_copy(deep=True) for record in self.commit_log]
