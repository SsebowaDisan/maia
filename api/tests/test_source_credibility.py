from __future__ import annotations

import pytest

from api.services.agent.research.source_credibility import (
    build_credibility_weights,
    score_source_credibility,
)


# ── unit: score_source_credibility ───────────────────────────────────────────

def test_high_credibility_domains():
    assert score_source_credibility("https://arxiv.org/abs/2401.00001") >= 0.90
    assert score_source_credibility("https://www.sec.gov/Archives/edgar/data/0001") >= 0.90
    assert score_source_credibility("https://reuters.com/article/test") >= 0.88


def test_medium_credibility_domains():
    score = score_source_credibility("https://en.wikipedia.org/wiki/Python")
    assert 0.55 <= score <= 0.75


def test_low_credibility_domains():
    score = score_source_credibility("https://reddit.com/r/tech/comments/abc")
    assert score <= 0.40


def test_subdomain_resolves_to_parent():
    # e.g. blog.reuters.com should still match reuters.com
    score = score_source_credibility("https://blog.reuters.com/article")
    assert score >= 0.80


def test_unknown_domain_returns_default():
    score = score_source_credibility("https://totally-unknown-domain-xyz123.biz/page")
    assert 0.40 <= score <= 0.70  # default band


def test_empty_url_returns_default():
    score = score_source_credibility("")
    assert 0.0 <= score <= 1.0


def test_gov_tld_gets_high_score():
    score = score_source_credibility("https://data.census.gov/table/abc")
    assert score >= 0.85


def test_edu_tld_gets_elevated_score():
    score = score_source_credibility("https://cs.stanford.edu/research/paper")
    assert score >= 0.75


# ── unit: build_credibility_weights ─────────────────────────────────────────

def test_build_credibility_weights_returns_dict():
    results = [
        {"url": "https://arxiv.org/abs/2401.00001", "title": "Paper A"},
        {"url": "https://reddit.com/r/ml/comments/xyz", "title": "Discussion B"},
    ]
    weights = build_credibility_weights(results)
    assert isinstance(weights, dict)
    assert "arxiv.org" in weights
    assert "reddit.com" in weights
    assert weights["arxiv.org"] > weights["reddit.com"]


def test_build_credibility_weights_empty_input():
    weights = build_credibility_weights([])
    assert isinstance(weights, dict)
    assert len(weights) == 0


def test_build_credibility_weights_deduplicates_domains():
    results = [
        {"url": "https://reuters.com/a", "title": "A"},
        {"url": "https://reuters.com/b", "title": "B"},
    ]
    weights = build_credibility_weights(results)
    assert len(weights) == 1
    assert "reuters.com" in weights


def test_build_credibility_weights_skips_invalid():
    results = [{"url": "", "title": "bad"}, {"title": "no url"}]
    weights = build_credibility_weights(results)
    assert isinstance(weights, dict)
