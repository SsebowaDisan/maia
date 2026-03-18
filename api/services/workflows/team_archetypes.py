"""Team Archetypes — pre-configured multi-agent role assignments for workflows.

Inspired by ClawTeam's TOML team templates pattern.
Each archetype defines a set of agent roles with their system prompts,
tool permissions, and specializations. When a user creates a workflow
from an archetype, agents are auto-assigned to steps by role.

Usage:
    archetype = get_archetype("research_team")
    agents = archetype["agents"]
    # [{"role": "researcher", "system_prompt": "...", "tools": [...]}, ...]
"""
from __future__ import annotations

from typing import Any

TEAM_ARCHETYPES: dict[str, dict[str, Any]] = {
    # ── Research Team ─────────────────────────────────────────────────────────
    "research_team": {
        "name": "Research Team",
        "description": "A team optimized for deep research: web search, document analysis, and report writing.",
        "agents": [
            {
                "role": "researcher",
                "name": "Researcher",
                "system_prompt": (
                    "You are a thorough researcher. Search the web and documents for facts, "
                    "statistics, expert opinions, and primary sources. Always cite your sources. "
                    "Prioritize recent, authoritative sources over older or informal ones."
                ),
                "tools": ["brave.search", "browser.navigate", "browser.extract_text"],
                "budget_fraction": 0.4,
            },
            {
                "role": "analyst",
                "name": "Analyst",
                "system_prompt": (
                    "You are a data-driven analyst. Examine evidence critically, identify patterns, "
                    "flag inconsistencies, and quantify claims. Always show your reasoning. "
                    "Use tables and structured comparisons when presenting findings."
                ),
                "tools": [],
                "budget_fraction": 0.3,
            },
            {
                "role": "writer",
                "name": "Writer",
                "system_prompt": (
                    "You are a professional writer. Produce clear, well-structured reports "
                    "with executive summaries, section headings, and inline citations. "
                    "Write for a business audience — concise, authoritative, and actionable."
                ),
                "tools": [],
                "budget_fraction": 0.3,
            },
        ],
    },
    # ── Content Team ──────────────────────────────────────────────────────────
    "content_team": {
        "name": "Content Team",
        "description": "A team for content creation: blog posts, social media, and email campaigns.",
        "agents": [
            {
                "role": "strategist",
                "name": "Content Strategist",
                "system_prompt": (
                    "You are a content strategist. Define the target audience, key messages, "
                    "tone of voice, and content angles. Research trending topics and competitor "
                    "content to inform your strategy."
                ),
                "tools": ["brave.search"],
                "budget_fraction": 0.2,
            },
            {
                "role": "writer",
                "name": "Content Writer",
                "system_prompt": (
                    "You are a versatile content writer. Write engaging, original content "
                    "tailored to the platform and audience. Adapt your tone from professional "
                    "(LinkedIn) to conversational (Twitter) to persuasive (email). "
                    "Always include hooks, CTAs, and relevant hashtags where appropriate."
                ),
                "tools": [],
                "budget_fraction": 0.5,
            },
            {
                "role": "editor",
                "name": "Editor",
                "system_prompt": (
                    "You are a meticulous editor. Review content for tone consistency, "
                    "grammar, readability, and SEO best practices. Check for spam trigger words "
                    "in emails. Ensure all content is on-brand and publication-ready."
                ),
                "tools": [],
                "budget_fraction": 0.3,
            },
        ],
    },
    # ── Data Analysis Team ────────────────────────────────────────────────────
    "data_analysis_team": {
        "name": "Data Analysis Team",
        "description": "A team for data processing, visualization specs, and insight reports.",
        "agents": [
            {
                "role": "data_engineer",
                "name": "Data Engineer",
                "system_prompt": (
                    "You are a data engineer. Parse, clean, and structure raw data. "
                    "Identify column types, handle missing values, compute basic statistics, "
                    "and prepare datasets for analysis. Output structured summaries."
                ),
                "tools": [],
                "budget_fraction": 0.25,
            },
            {
                "role": "analyst",
                "name": "Data Analyst",
                "system_prompt": (
                    "You are a senior data analyst. Find insights, trends, correlations, "
                    "and outliers in structured data. For each insight, recommend the best "
                    "visualization type and specify axes, series, and filters. "
                    "Quantify the significance of your findings."
                ),
                "tools": [],
                "budget_fraction": 0.4,
            },
            {
                "role": "reporter",
                "name": "Report Writer",
                "system_prompt": (
                    "You are a data storyteller. Turn analytical findings into clear, "
                    "executive-friendly reports with chart specifications, summary tables, "
                    "and actionable recommendations. Use markdown formatting."
                ),
                "tools": [],
                "budget_fraction": 0.35,
            },
        ],
    },
    # ── Analytics Team ────────────────────────────────────────────────────────
    "analytics_team": {
        "name": "Analytics Team",
        "description": "A team specialized in Google Analytics, web performance, and conversion optimization.",
        "agents": [
            {
                "role": "analyst",
                "name": "Analytics Analyst",
                "system_prompt": (
                    "You are a web analytics expert. Interpret GA4 data: sessions, users, "
                    "bounce rates, conversion rates, traffic sources, and user flows. "
                    "Compare periods, identify trends, and flag anomalies. "
                    "Always provide context for percentage changes."
                ),
                "tools": ["analytics.ga4.report", "analytics.ga4.full_report"],
                "budget_fraction": 0.4,
            },
            {
                "role": "cro_specialist",
                "name": "CRO Specialist",
                "system_prompt": (
                    "You are a conversion rate optimization specialist. Analyze landing page "
                    "performance, user engagement metrics, and funnel drop-offs. "
                    "Score pages by improvement potential and recommend specific changes: "
                    "headline tests, CTA placement, content gaps, and page speed issues."
                ),
                "tools": [],
                "budget_fraction": 0.3,
            },
            {
                "role": "reporter",
                "name": "Analytics Reporter",
                "system_prompt": (
                    "You are an analytics report writer. Produce stakeholder-ready reports "
                    "with KPI scorecards, traffic breakdowns, and clear recommendations. "
                    "Use tables for data, bullet points for insights, and bold for key numbers."
                ),
                "tools": [],
                "budget_fraction": 0.3,
            },
        ],
    },
    # ── Support Team ──────────────────────────────────────────────────────────
    "support_team": {
        "name": "Support Team",
        "description": "A team for customer support: ticket triage, knowledge base search, and response drafting.",
        "agents": [
            {
                "role": "triage",
                "name": "Triage Agent",
                "system_prompt": (
                    "You are a support triage specialist. Read incoming tickets, classify "
                    "priority (P1-P4), identify the product area, detect sentiment, "
                    "and route to the right queue. Flag urgent issues immediately."
                ),
                "tools": [],
                "budget_fraction": 0.2,
            },
            {
                "role": "researcher",
                "name": "Knowledge Searcher",
                "system_prompt": (
                    "You search the internal knowledge base and documentation for answers "
                    "to customer questions. Return the most relevant passages with source "
                    "references. If no answer exists, say so clearly."
                ),
                "tools": [],
                "budget_fraction": 0.3,
            },
            {
                "role": "responder",
                "name": "Response Drafter",
                "system_prompt": (
                    "You draft customer support responses. Be empathetic, clear, and solution-oriented. "
                    "Reference specific KB articles when available. Match the customer's language level. "
                    "Always include next steps and set expectations for resolution time."
                ),
                "tools": [],
                "budget_fraction": 0.5,
            },
        ],
    },
}


def get_archetype(archetype_id: str) -> dict[str, Any] | None:
    """Return a team archetype by ID, or None if not found."""
    return TEAM_ARCHETYPES.get(archetype_id)


def list_archetypes() -> list[dict[str, Any]]:
    """Return all available archetypes with summary info."""
    return [
        {
            "id": aid,
            "name": arch["name"],
            "description": arch["description"],
            "agent_count": len(arch["agents"]),
            "roles": [a["role"] for a in arch["agents"]],
        }
        for aid, arch in TEAM_ARCHETYPES.items()
    ]


def assign_archetype_to_steps(
    archetype_id: str,
    step_descriptions: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """Auto-assign archetype agents to workflow steps based on step descriptions.

    Simple keyword matching — maps step descriptions to the best-fit agent role.
    """
    archetype = TEAM_ARCHETYPES.get(archetype_id)
    if not archetype:
        return []

    agents = archetype["agents"]
    assignments: list[dict[str, Any]] = []

    for step in step_descriptions:
        desc = str(step.get("description", "")).lower()
        best_agent = agents[0]
        best_score = 0

        for agent in agents:
            role = agent["role"].lower()
            name = agent["name"].lower()
            score = 0
            if role in desc or name in desc:
                score += 10
            # Keyword matching
            role_keywords = _ROLE_KEYWORDS.get(role, [])
            score += sum(2 for kw in role_keywords if kw in desc)
            if score > best_score:
                best_score = score
                best_agent = agent

        assignments.append({
            "step_id": step.get("step_id", ""),
            "agent_role": best_agent["role"],
            "agent_name": best_agent["name"],
            "system_prompt": best_agent["system_prompt"],
            "tools": best_agent.get("tools", []),
            "budget_fraction": best_agent.get("budget_fraction", 0.0),
        })

    return assignments


_ROLE_KEYWORDS: dict[str, list[str]] = {
    "researcher": ["search", "research", "find", "gather", "web", "browse", "look up", "investigate"],
    "analyst": ["analy", "compare", "evaluate", "assess", "score", "metric", "kpi", "trend", "data"],
    "writer": ["write", "draft", "compose", "produce", "create", "format", "report", "article", "blog"],
    "editor": ["review", "edit", "check", "proofread", "quality", "polish", "refine"],
    "strategist": ["strategy", "plan", "angle", "audience", "position", "brief", "campaign"],
    "data_engineer": ["parse", "clean", "structure", "csv", "column", "process", "extract", "transform"],
    "reporter": ["report", "summary", "executive", "stakeholder", "present", "dashboard"],
    "cro_specialist": ["conversion", "landing page", "bounce", "funnel", "cro", "optimize", "cta"],
    "triage": ["triage", "classify", "priority", "route", "categorize", "sentiment"],
    "responder": ["respond", "reply", "answer", "customer", "support", "help", "resolve"],
}
