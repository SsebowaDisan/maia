"""Terminal color helpers — ANSI escape codes for rich CLI output."""

from __future__ import annotations


def _code(n: int) -> str:
    return f"\033[{n}m"


RESET = _code(0)
BOLD = _code(1)
DIM = _code(2)
ITALIC = _code(3)

RED = _code(31)
GREEN = _code(32)
YELLOW = _code(33)
BLUE = _code(34)
MAGENTA = _code(35)
CYAN = _code(36)
WHITE = _code(37)
GRAY = _code(90)

BG_RED = _code(41)
BG_GREEN = _code(42)
BG_YELLOW = _code(43)
BG_BLUE = _code(44)
BG_MAGENTA = _code(45)
BG_CYAN = _code(46)

AGENT_COLORS = [MAGENTA, BLUE, GREEN, YELLOW, CYAN, RED]

INTENT_COLORS: dict[str, str] = {
    "propose": BLUE,
    "challenge": RED,
    "clarify": YELLOW,
    "review": MAGENTA,
    "handoff": GREEN,
    "summarize": GRAY,
    "agree": GREEN,
    "escalate": RED,
}

ACTIVITY_ICONS: dict[str, str] = {
    "thinking": "\u2728",
    "searching": "\U0001f50d",
    "reading": "\U0001f4d6",
    "writing": "\u270f\ufe0f",
    "browsing": "\U0001f310",
    "coding": "\U0001f4bb",
    "analyzing": "\U0001f4ca",
    "tool_calling": "\U0001f527",
    "waiting": "\u23f3",
    "reviewing": "\U0001f50e",
    "idle": "\U0001f4a4",
    "error": "\u26a0\ufe0f",
}

VERDICT_COLORS: dict[str, str] = {
    "approve": GREEN,
    "revise": YELLOW,
    "reject": RED,
    "escalate": RED,
}


def agent_color(agent_id: str) -> str:
    """Consistent color for an agent based on ID hash."""
    h = sum(ord(c) for c in agent_id)
    return AGENT_COLORS[h % len(AGENT_COLORS)]


def colored(text: str, color: str) -> str:
    return f"{color}{text}{RESET}"


def bold(text: str) -> str:
    return f"{BOLD}{text}{RESET}"


def dim(text: str) -> str:
    return f"{DIM}{text}{RESET}"


def badge(text: str, color: str) -> str:
    return f"{color}{BOLD}[{text}]{RESET}"
