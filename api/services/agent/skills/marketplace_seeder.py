"""Marketplace skill seeder.

Reads all *.yaml files in this directory and upserts them into the
``maia_marketplace_agent`` table as platform-published agents.

Idempotent: agents that are already ``published`` are skipped.
Called once at server startup via ``api/main.py``.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

SKILLS_DIR = Path(__file__).parent
_PLATFORM_PUBLISHER_ID = "maia-platform"


def _auto_publish(agent_id: str) -> None:
    """Transition a pending_review platform entry straight to published."""
    try:
        from sqlmodel import Session, select

        from api.services.marketplace.registry import MarketplaceAgent
        from ktem.db.engine import engine

        with Session(engine) as session:
            entry = session.exec(
                select(MarketplaceAgent).where(MarketplaceAgent.agent_id == agent_id)
            ).first()
            if entry and entry.status == "pending_review":
                entry.status = "published"
                entry.published_at = time.time()
                session.add(entry)
                session.commit()
    except Exception as exc:
        logger.warning("skill_auto_publish_failed agent_id=%s error=%s", agent_id, exc)


def seed_marketplace_agents() -> list[str]:
    """Load *.yaml skill files and upsert into the marketplace registry.

    Returns the list of newly seeded agent IDs (empty when all are already present).
    """
    from api.services.marketplace.registry import get_marketplace_agent, publish_agent

    seeded: list[str] = []
    for yaml_path in sorted(SKILLS_DIR.glob("*.yaml")):
        try:
            definition: Any = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
            if not isinstance(definition, dict):
                logger.warning("skill_seed_skip file=%s reason=not_a_dict", yaml_path.name)
                continue

            agent_id = str(definition.get("id") or "").strip()
            if not agent_id:
                logger.warning("skill_seed_skip file=%s reason=missing_id", yaml_path.name)
                continue

            # Skip if already published — do not overwrite installed versions.
            existing = get_marketplace_agent(agent_id)
            if existing:
                continue

            tags: list[str] = list(definition.get("tags") or [])
            required_connectors: list[str] = list(definition.get("required_connectors") or [])

            publish_agent(
                publisher_id=_PLATFORM_PUBLISHER_ID,
                definition=definition,
                metadata={
                    "agent_id": agent_id,
                    "name": definition.get("name", agent_id),
                    "description": definition.get("description", ""),
                    "tags": tags,
                    "required_connectors": required_connectors,
                    "pricing_tier": "free",
                },
            )
            _auto_publish(agent_id)
            seeded.append(agent_id)
            logger.info("skill_seeded agent_id=%s", agent_id)

        except Exception as exc:
            logger.warning("skill_seed_failed file=%s error=%s", yaml_path.name, exc)

    if seeded:
        logger.info(
            "marketplace_seeds_total count=%d agents=%s",
            len(seeded),
            seeded,
        )
    return seeded
