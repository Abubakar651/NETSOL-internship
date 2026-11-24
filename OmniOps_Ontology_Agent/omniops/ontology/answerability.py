"""Pre-flight question answerability checker (NVIDIA Auto-Ontology pattern)."""

from __future__ import annotations

import re

from .registry import OntologyRegistry
from .schema import AnswerabilityReport

_ID_PREFIX_TO_OBJECT: dict[str, str] = {
    "SVC-": "Service",
    "INC-": "Incident",
    "PR-": "PullRequest",
    "DB-": "Database",
    "EP-": "Endpoint",
    "TEAM-": "Team",
}

_LINK_KEYWORDS: dict[str, tuple[str, ...]] = {
    "CALLS": ("calls", "caller", "upstream", "downstream", "blast radius", "depends", "dependency", "impact", "impacted"),
    "READS_WRITES": ("reads", "writes", "connection", "connections", "pool", "database", "redis", "postgres"),
    "DEPLOYED_TO": ("deployed", "deployment", "merged", "suspect", "caused", "culprit", "root cause"),
    "MIGRATES_SCHEMA": ("migration", "migrates", "schema", "column", "index"),
    "AFFECTS": ("affects", "incident", "outage", "failing", "500"),
    "EXPOSES": ("endpoint", "route", "path", "sla"),
    "OWNED_BY": ("team", "owner", "oncall", "slack", "escalate"),
}

_METRIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "connection_saturation_ratio": ("saturation", "connection", "connections", "exhausted", "pool"),
    "blast_radius_severity_score": ("blast radius", "severity score", "impact", "upstream", "p0"),
    "deployment_suspect_score": ("suspect", "culprit", "deployment", "pr", "root cause", "caused"),
}

_ACTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "TriggerSafeRollback": ("rollback", "revert", "restore", "fix", "mitigate", "remediate"),
    "ScaleDatabaseConnectionPool": ("scale", "increase pool", "max_connections"),
    "IsolateServiceTraffic": ("isolate", "circuit breaker", "throttle", "shed"),
    "CertifyOntologyDefinition": ("certify", "approve schema"),
}

_STOPWORDS = {
    "what", "which", "who", "when", "where", "why", "how", "is", "are", "was", "were",
    "the", "a", "an", "in", "on", "at", "to", "for", "of", "and", "or", "with", "by",
    "do", "does", "did", "can", "could", "should", "tell", "me", "analyze", "check",
    "show", "find", "please", "about", "today", "currently", "recent", "this", "that",
}


def _phrase_in_text(phrase: str, lower_text: str) -> bool:
    escaped = re.escape(phrase.lower())
    return re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", lower_text) is not None


class AnswerabilityChecker:
    """Checks whether a natural-language question maps to certified Ontology entities."""

    def __init__(self, registry: OntologyRegistry) -> None:
        self.registry = registry

    def evaluate(self, question: str) -> AnswerabilityReport:
        clean_q = question.strip()
        if not clean_q:
            return AnswerabilityReport(
                question=question,
                answerable=False,
                confidence=0.0,
                guidance="Provide a non-empty operational question referencing services, incidents, databases, or PRs.",
            )

        lower_q = clean_q.lower()
        upper_q = clean_q.upper()

        # 1. Check DRAFT concepts first so uncertified tables are never queried silently.
        uncertified: list[str] = []
        for obj_name, obj_def in self.registry.get_draft_objects().items():
            terms = [obj_name, obj_def.source_table, *obj_def.synonyms]
            if any(_phrase_in_text(term, lower_q) for term in terms):
                uncertified.append(obj_name)

        if uncertified:
            return AnswerabilityReport(
                question=clean_q,
                answerable=False,
                confidence=0.92,
                uncertified_concepts=sorted(set(uncertified)),
                guidance=(
                    f"Concepts {sorted(set(uncertified))} are currently in DRAFT status in the Auto-Ontology "
                    "catalog. An SME must promote them via CertifyOntologyDefinition before agents can query them."
                ),
            )

        # 2. Match certified ObjectTypes via ID prefixes, object names, and synonyms.
        matched_objects: set[str] = set()
        certified_objects = self.registry.get_certified_objects()

        for prefix, obj_name in _ID_PREFIX_TO_OBJECT.items():
            if prefix in upper_q and obj_name in certified_objects:
                matched_objects.add(obj_name)

        for obj_name, obj_def in certified_objects.items():
            terms = [obj_name, *obj_def.synonyms]
            if any(_phrase_in_text(term, lower_q) for term in terms):
                matched_objects.add(obj_name)

        # 3. Match certified Links, Metrics, and Kinetic Actions.
        certified_links = self.registry.get_certified_links()
        matched_links = sorted(
            link_id
            for link_id, keywords in _LINK_KEYWORDS.items()
            if link_id in certified_links and any(_phrase_in_text(kw, lower_q) for kw in keywords)
        )

        certified_metrics = self.registry.get_certified_metrics()
        matched_metrics = sorted(
            metric_id
            for metric_id, keywords in _METRIC_KEYWORDS.items()
            if metric_id in certified_metrics and any(_phrase_in_text(kw, lower_q) for kw in keywords)
        )

        certified_actions = self.registry.get_certified_actions()
        matched_actions = sorted(
            action_id
            for action_id, keywords in _ACTION_KEYWORDS.items()
            if action_id in certified_actions and any(_phrase_in_text(kw, lower_q) for kw in keywords)
        )

        if matched_objects or matched_links or matched_metrics or matched_actions:
            signal_count = len(matched_objects) + len(matched_links) + len(matched_metrics) + len(matched_actions)
            confidence = min(0.98, 0.72 + 0.04 * signal_count)
            return AnswerabilityReport(
                question=clean_q,
                answerable=True,
                confidence=round(confidence, 2),
                matched_object_types=sorted(matched_objects),
                matched_links=matched_links,
                matched_metrics=matched_metrics,
                matched_actions=matched_actions,
                guidance="Question maps to certified Ontology concepts and is cleared for MCP investigation.",
            )

        # 4. Out-of-domain / unmodeled question.
        tokens = re.findall(r"[a-z0-9_-]{3,}", lower_q)
        unmodeled = sorted({tok for tok in tokens if tok not in _STOPWORDS})[:8]
        available = ", ".join(sorted(certified_objects.keys()))
        return AnswerabilityReport(
            question=clean_q,
            answerable=False,
            confidence=0.88,
            unmodeled_concepts=unmodeled,
            guidance=(
                f"No certified ontology concepts matched this query. Certified ObjectTypes available: {available}."
            ),
        )
