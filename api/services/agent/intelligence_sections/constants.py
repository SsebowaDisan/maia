from __future__ import annotations

import re

EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")
URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
NUMBER_RE = re.compile(r"\b\d+(?:[\.,]\d+)?\b")

STOPWORDS = {
    "about",
    "after",
    "also",
    "been",
    "being",
    "between",
    "company",
    "from",
    "have",
    "into",
    "more",
    "most",
    "other",
    "that",
    "their",
    "there",
    "these",
    "this",
    "those",
    "using",
    "with",
    "your",
    "http",
    "https",
    "www",
}

NEGATION_TERMS = {"no", "not", "never", "without", "none", "cannot", "can't"}
DELIVERY_ACTION_IDS = ("gmail.send", "email.send", "mailer.report_send")
