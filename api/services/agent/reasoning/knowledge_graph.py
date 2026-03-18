"""Knowledge Graph from evidence (Innovation #5).

Extracts entities and relationships from evidence text, builds a
queryable graph, detects contradictions, and generates non-obvious
insights.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from api.services.agent.llm_runtime import call_json_response, has_openai_credentials

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

ENTITY_TYPES = frozenset({
    "person", "organization", "url", "concept",
    "metric", "date", "location",
})

RELATION_TYPES = frozenset({
    "mentions", "owns", "located_at", "related_to",
    "contradicts", "supports", "caused_by",
})


@dataclass
class Entity:
    """A named entity extracted from evidence."""

    name: str
    type: str  # one of ENTITY_TYPES
    properties: dict[str, Any] = field(default_factory=dict)

    def _key(self) -> str:
        return self.name.strip().lower()


@dataclass
class Relationship:
    """A directed relationship between two entities."""

    source: str
    target: str
    relation_type: str  # one of RELATION_TYPES
    confidence: float = 0.8
    evidence_text: str = ""


@dataclass
class Insight:
    """A non-obvious pattern identified from graph structure."""

    text: str
    supporting_entities: list[str] = field(default_factory=list)
    confidence: float = 0.5


@dataclass
class KnowledgeGraph:
    """The assembled knowledge graph."""

    entities: list[Entity] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)
    clusters: list[list[str]] = field(default_factory=list)  # groups of related entity names

    def entity_count(self) -> int:
        return len(self.entities)

    def relationship_count(self) -> int:
        return len(self.relationships)

    def summary(self) -> dict[str, Any]:
        """Compact summary for run metadata."""
        return {
            "entity_count": self.entity_count(),
            "relationship_count": self.relationship_count(),
            "cluster_count": len(self.clusters),
            "entity_types": list({e.type for e in self.entities}),
            "relation_types": list({r.relation_type for r in self.relationships}),
            "contradictions": [
                {"source": r.source, "target": r.target, "evidence": r.evidence_text[:120]}
                for r in self.relationships
                if r.relation_type == "contradicts"
            ][:5],
        }


# ---------------------------------------------------------------------------
# KnowledgeGraphBuilder
# ---------------------------------------------------------------------------

class KnowledgeGraphBuilder:
    """Build a knowledge graph from evidence text."""

    # ------------------------------------------------------------------
    # Entity extraction
    # ------------------------------------------------------------------

    def extract_entities(self, text: str) -> list[Entity]:
        """Extract named entities from text via LLM."""
        if not text.strip() or not has_openai_credentials():
            return []

        prompt = (
            "Extract named entities from the following text.\n\n"
            f"Text:\n{text[:2000]}\n\n"
            "Entity types: person, organization, url, concept, metric, date, location\n\n"
            "Return JSON:\n"
            '{"entities": [{"name": "...", "type": "person|organization|...", '
            '"properties": {}}]}'
        )

        try:
            payload = call_json_response(
                system_prompt="You are a named-entity extraction engine. Output strict JSON only.",
                user_prompt=prompt,
                temperature=0.0,
                timeout_seconds=12,
                max_tokens=800,
            )
        except Exception:
            logger.exception("KG: entity extraction failed")
            return []

        if not isinstance(payload, dict):
            return []

        raw = payload.get("entities")
        if not isinstance(raw, list):
            return []

        entities: list[Entity] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            etype = str(item.get("type") or "concept").strip().lower()
            if not name:
                continue
            if etype not in ENTITY_TYPES:
                etype = "concept"
            entities.append(
                Entity(
                    name=name,
                    type=etype,
                    properties=dict(item.get("properties") or {}),
                )
            )

        return entities

    # ------------------------------------------------------------------
    # Relationship extraction
    # ------------------------------------------------------------------

    def extract_relationships(
        self,
        text: str,
        entities: list[Entity],
    ) -> list[Relationship]:
        """Extract relationships between known entities from text."""
        if not entities or not text.strip() or not has_openai_credentials():
            return []

        entity_names = [e.name for e in entities[:40]]
        prompt = (
            "Identify relationships between the following entities based on the text.\n\n"
            f"Entities: {json.dumps(entity_names)}\n\n"
            f"Text:\n{text[:2000]}\n\n"
            "Relationship types: mentions, owns, located_at, related_to, "
            "contradicts, supports, caused_by\n\n"
            "Return JSON:\n"
            '{"relationships": [{"source": "...", "target": "...", '
            '"relation_type": "...", "confidence": 0.0-1.0, '
            '"evidence_text": "..."}]}'
        )

        try:
            payload = call_json_response(
                system_prompt="You are a relationship extraction engine. Output strict JSON only.",
                user_prompt=prompt,
                temperature=0.0,
                timeout_seconds=12,
                max_tokens=800,
            )
        except Exception:
            logger.exception("KG: relationship extraction failed")
            return []

        if not isinstance(payload, dict):
            return []

        raw = payload.get("relationships")
        if not isinstance(raw, list):
            return []

        name_set = {e.name.strip().lower() for e in entities}
        relationships: list[Relationship] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            source = str(item.get("source") or "").strip()
            target = str(item.get("target") or "").strip()
            rtype = str(item.get("relation_type") or "related_to").strip().lower()
            if not source or not target:
                continue
            if rtype not in RELATION_TYPES:
                rtype = "related_to"
            relationships.append(
                Relationship(
                    source=source,
                    target=target,
                    relation_type=rtype,
                    confidence=float(item.get("confidence") or 0.8),
                    evidence_text=str(item.get("evidence_text") or "")[:300],
                )
            )

        return relationships

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def build_graph(self, evidence_pool: list[str]) -> KnowledgeGraph:
        """Build a knowledge graph from a list of evidence strings.

        Merges entities by name similarity and detects clusters.
        """
        if not evidence_pool:
            return KnowledgeGraph()

        combined_text = "\n\n".join(evidence_pool[:20])[:6000]
        all_entities = self.extract_entities(combined_text)
        if not all_entities:
            return KnowledgeGraph()

        # Merge entities by lowercased name.
        merged: dict[str, Entity] = {}
        for e in all_entities:
            key = e._key()
            if key in merged:
                # Merge properties.
                merged[key].properties.update(e.properties)
            else:
                merged[key] = e
        unique_entities = list(merged.values())

        relationships = self.extract_relationships(combined_text, unique_entities)

        # Build clusters via simple connected-components.
        clusters = self._build_clusters(unique_entities, relationships)

        return KnowledgeGraph(
            entities=unique_entities,
            relationships=relationships,
            clusters=clusters,
        )

    @staticmethod
    def _build_clusters(
        entities: list[Entity],
        relationships: list[Relationship],
    ) -> list[list[str]]:
        """Simple union-find clustering on entity names."""
        parent: dict[str, str] = {}

        def find(x: str) -> str:
            while parent.get(x, x) != x:
                parent[x] = parent.get(parent[x], parent[x])
                x = parent[x]
            return x

        def union(a: str, b: str) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for e in entities:
            key = e.name.strip().lower()
            parent.setdefault(key, key)

        for r in relationships:
            sk = r.source.strip().lower()
            tk = r.target.strip().lower()
            if sk in parent and tk in parent:
                union(sk, tk)

        from collections import defaultdict
        groups: dict[str, list[str]] = defaultdict(list)
        for key in parent:
            groups[find(key)].append(key)

        return [members for members in groups.values() if len(members) > 1]

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def query_graph(
        self,
        graph: KnowledgeGraph,
        question: str,
    ) -> dict[str, Any]:
        """Return entities and relationships relevant to a question."""
        if not graph.entities or not question.strip():
            return {"entities": [], "relationships": []}

        q_lower = question.lower()
        relevant_entities = [
            e for e in graph.entities
            if e.name.lower() in q_lower or e.type in q_lower
        ]

        if not relevant_entities:
            # Broaden: grab top entities by relationship count.
            entity_mention_count: dict[str, int] = {}
            for r in graph.relationships:
                entity_mention_count[r.source] = entity_mention_count.get(r.source, 0) + 1
                entity_mention_count[r.target] = entity_mention_count.get(r.target, 0) + 1
            sorted_entities = sorted(
                graph.entities,
                key=lambda e: entity_mention_count.get(e.name, 0),
                reverse=True,
            )
            relevant_entities = sorted_entities[:5]

        relevant_names = {e.name.lower() for e in relevant_entities}
        relevant_relationships = [
            r for r in graph.relationships
            if r.source.lower() in relevant_names or r.target.lower() in relevant_names
        ]

        return {
            "entities": [
                {"name": e.name, "type": e.type, "properties": e.properties}
                for e in relevant_entities
            ],
            "relationships": [
                {
                    "source": r.source,
                    "target": r.target,
                    "relation_type": r.relation_type,
                    "confidence": r.confidence,
                }
                for r in relevant_relationships
            ],
        }

    # ------------------------------------------------------------------
    # Contradiction detection
    # ------------------------------------------------------------------

    def detect_contradictions(
        self,
        graph: KnowledgeGraph,
    ) -> list[dict[str, Any]]:
        """Return pairs of contradicting relationships."""
        contradictions: list[dict[str, Any]] = []

        # Explicit contradicts edges.
        for r in graph.relationships:
            if r.relation_type == "contradicts":
                contradictions.append(
                    {
                        "source": r.source,
                        "target": r.target,
                        "evidence": r.evidence_text[:200],
                        "confidence": r.confidence,
                    }
                )

        # Detect implicit contradictions: same source-target pair with
        # both "supports" and "contradicts" relations.
        pair_relations: dict[tuple[str, str], list[str]] = {}
        for r in graph.relationships:
            key = (r.source.lower(), r.target.lower())
            pair_relations.setdefault(key, []).append(r.relation_type)
        for pair, types in pair_relations.items():
            if "supports" in types and "contradicts" in types:
                # Already captured above; skip duplicates.
                pass

        return contradictions

    # ------------------------------------------------------------------
    # Insight generation
    # ------------------------------------------------------------------

    def generate_insights(self, graph: KnowledgeGraph) -> list[Insight]:
        """LLM-identify non-obvious patterns from graph structure."""
        if not graph.entities or not has_openai_credentials():
            return []

        graph_summary = {
            "entities": [
                {"name": e.name, "type": e.type}
                for e in graph.entities[:30]
            ],
            "relationships": [
                {"source": r.source, "target": r.target, "type": r.relation_type}
                for r in graph.relationships[:30]
            ],
            "clusters": graph.clusters[:10],
        }

        prompt = (
            "Analyze this knowledge graph and identify non-obvious patterns, "
            "connections, or insights that might not be immediately apparent.\n\n"
            f"Graph: {json.dumps(graph_summary)}\n\n"
            "Return JSON:\n"
            '{"insights": [{"text": "...", "supporting_entities": ["..."], '
            '"confidence": 0.0-1.0}]}'
        )

        try:
            payload = call_json_response(
                system_prompt="You are a knowledge graph analysis engine. Output strict JSON only.",
                user_prompt=prompt,
                temperature=0.3,
                timeout_seconds=12,
                max_tokens=600,
            )
        except Exception:
            logger.exception("KG: insight generation failed")
            return []

        if not isinstance(payload, dict):
            return []

        raw = payload.get("insights")
        if not isinstance(raw, list):
            return []

        insights: list[Insight] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            insights.append(
                Insight(
                    text=text[:400],
                    supporting_entities=list(item.get("supporting_entities") or []),
                    confidence=float(item.get("confidence") or 0.5),
                )
            )

        return insights
