"""Skill-pack loader — discovers and parses SKILL.md-based skill packs.

Also re-exports ``seed_marketplace_agents`` from the YAML marketplace seeder
for backward compatibility (used by ``api/main.py`` at startup).
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Backward-compatible re-export so existing ``from .loader import seed_marketplace_agents``
# continues to work without changing callers.
from .marketplace_seeder import seed_marketplace_agents  # noqa: F401

logger = logging.getLogger(__name__)


@dataclass
class SkillPack:
    """A loaded skill pack with metadata, prompt, and assets."""

    # Identity
    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    tags: list[str] = field(default_factory=list)

    # Execution
    prompt: str = ""  # The main instruction body from SKILL.md
    model: str = ""  # Preferred model override (optional)
    temperature: float | None = None
    max_tokens: int | None = None

    # Tools & capabilities
    required_tools: list[str] = field(default_factory=list)
    required_connectors: list[str] = field(default_factory=list)
    mcp_servers: list[dict[str, Any]] = field(default_factory=list)

    # Assets
    assets_dir: Path | None = None
    example_inputs: list[dict[str, Any]] = field(default_factory=list)
    example_outputs: list[dict[str, Any]] = field(default_factory=list)

    # Source
    source_path: Path | None = None

    @property
    def qualified_name(self) -> str:
        return f"{self.name}@{self.version}"


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Extract YAML-like front matter from a markdown file.

    Returns (metadata_dict, body_text).
    Supports --- delimited frontmatter with key: value pairs.
    """
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.DOTALL)
    if not match:
        return {}, text

    meta_text = match.group(1)
    body = text[match.end() :]
    metadata: dict[str, Any] = {}

    for line in meta_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()

        # Handle list values (comma-separated or JSON array)
        if value.startswith("["):
            try:
                metadata[key] = json.loads(value)
            except json.JSONDecodeError:
                metadata[key] = value
        elif "," in value and key in (
            "tags",
            "required_tools",
            "required_connectors",
        ):
            metadata[key] = [v.strip() for v in value.split(",") if v.strip()]
        else:
            # Handle numeric values
            if value.replace(".", "", 1).isdigit():
                metadata[key] = float(value) if "." in value else int(value)
            elif value.lower() in ("true", "false"):
                metadata[key] = value.lower() == "true"
            elif value.lower() == "null" or value == "":
                metadata[key] = None
            else:
                # Strip quotes
                if (
                    len(value) >= 2
                    and value[0] == value[-1]
                    and value[0] in ('"', "'")
                ):
                    value = value[1:-1]
                metadata[key] = value

    return metadata, body


def load_skill_pack(path: Path) -> SkillPack:
    """Load a skill pack from a directory or single SKILL.md file.

    Directory layout::

        my_skill/
            SKILL.md          — front matter + prompt body (required)
            assets/           — optional directory for templates, examples
            examples/         — optional example inputs/outputs (JSON files)
    """
    if path.is_file() and path.name.upper() == "SKILL.MD":
        skill_dir = path.parent
        skill_file = path
    elif path.is_dir():
        skill_file = path / "SKILL.md"
        if not skill_file.exists():
            # Try lowercase
            skill_file = path / "skill.md"
        skill_dir = path
    else:
        raise FileNotFoundError(f"No SKILL.md found at {path}")

    if not skill_file.exists():
        raise FileNotFoundError(f"SKILL.md not found in {path}")

    raw = skill_file.read_text(encoding="utf-8")
    metadata, body = _parse_frontmatter(raw)

    # Build skill pack
    pack = SkillPack(
        name=metadata.get("name", skill_dir.name),
        version=str(metadata.get("version", "1.0.0")),
        description=metadata.get("description", ""),
        author=metadata.get("author", ""),
        tags=metadata.get("tags", []),
        prompt=body.strip(),
        model=metadata.get("model", ""),
        temperature=metadata.get("temperature"),
        max_tokens=metadata.get("max_tokens"),
        required_tools=metadata.get("required_tools", []),
        required_connectors=metadata.get("required_connectors", []),
        mcp_servers=metadata.get("mcp_servers", []),
        source_path=skill_dir,
    )

    # Load assets directory reference
    assets_dir = skill_dir / "assets"
    if assets_dir.is_dir():
        pack.assets_dir = assets_dir

    # Load example inputs/outputs
    examples_dir = skill_dir / "examples"
    if examples_dir.is_dir():
        for example_file in sorted(examples_dir.glob("*.json")):
            try:
                data = json.loads(example_file.read_text(encoding="utf-8"))
                if "input" in example_file.stem.lower():
                    pack.example_inputs.append(data)
                elif "output" in example_file.stem.lower():
                    pack.example_outputs.append(data)
            except (json.JSONDecodeError, OSError):
                pass

    logger.info(
        "Loaded skill pack: %s (v%s) from %s", pack.name, pack.version, skill_dir
    )
    return pack


def discover_skill_packs(root: Path) -> list[SkillPack]:
    """Discover all skill packs under a root directory.

    Looks for directories containing SKILL.md files.
    """
    packs: list[SkillPack] = []
    if not root.is_dir():
        return packs

    # Direct SKILL.md in root
    if (root / "SKILL.md").exists() or (root / "skill.md").exists():
        try:
            packs.append(load_skill_pack(root))
        except Exception as exc:
            logger.warning("Failed to load skill pack at %s: %s", root, exc)

    # Subdirectories
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        skill_file = child / "SKILL.md"
        if not skill_file.exists():
            skill_file = child / "skill.md"
        if skill_file.exists():
            try:
                packs.append(load_skill_pack(child))
            except Exception as exc:
                logger.warning("Failed to load skill pack at %s: %s", child, exc)

    logger.info("Discovered %d skill packs under %s", len(packs), root)
    return packs
