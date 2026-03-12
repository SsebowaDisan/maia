from __future__ import annotations

import logging
import re
from typing import Any, Callable

_logger = logging.getLogger(__name__)

from api.services.agent.llm_runtime import call_json_response, env_bool
from api.services.agent.models import AgentSource
from api.services.agent.tools.base import (
    ToolExecutionContext,
    ToolExecutionResult,
    ToolTraceEvent,
)
from api.services.agent.tools.research_helpers import (
    classify_provider_failure as _classify_provider_failure,
    fuse_search_results as _fuse_search_results,
    mmr_rerank as _mmr_rerank,
    safe_snippet as _safe_snippet,
)
from api.services.agent.tools.research_web_helpers import _build_provider_plan, _website_scene_payload


def _llm_gap_fill_queries(
    *,
    original_query: str,
    covered_labels: list[str],
    covered_excerpts: list[str],
    max_queries: int = 4,
) -> list[str]:
    """Generate targeted gap-fill search queries using an LLM.

    Analyses what has already been collected and returns queries that cover
    different angles, subtopics, or perspectives not yet addressed, producing
    far more meaningful gap coverage than regex entity extraction.
    """
    if not env_bool("MAIA_AGENT_LLM_GAP_FILL_QUERIES_ENABLED", default=True):
        return []
    clean_labels = [str(lbl or "").strip() for lbl in covered_labels if str(lbl or "").strip()]
    clean_excerpts = [str(ex or "").strip() for ex in covered_excerpts if str(ex or "").strip()]
    if not clean_labels and not clean_excerpts:
        return []
    payload = {
        "original_query": str(original_query or "").strip()[:320],
        "already_covered_titles": clean_labels[:12],
        "excerpt_samples": [ex[:200] for ex in clean_excerpts[:6]],
    }
    response = call_json_response(
        system_prompt=(
            "You generate precise web search queries to fill gaps in research coverage for enterprise intelligence. "
            "Return strict JSON only."
        ),
        user_prompt=(
            "The research agent already collected the sources listed in 'already_covered_titles' while researching the query below.\n"
            "Your task: generate search queries that target DIFFERENT angles not yet covered — "
            "competing viewpoints, specific data points, related companies, expert opinions, recent developments, or niche subtopics.\n"
            "Return JSON only in this schema:\n"
            '{ "gap_queries": ["specific query 1", "specific query 2"] }\n'
            "Rules:\n"
            f"- Generate exactly {max_queries} distinct search queries.\n"
            "- Each query must address a gap: a subtopic, competitor, statistic, or perspective absent from already_covered_titles.\n"
            "- Keep each query under 120 characters and optimised for web search (no filler words).\n"
            "- Do NOT repeat the original query verbatim or near-verbatim.\n"
            "- Prioritise specificity: 'Salesforce CRM market share 2024' beats 'CRM market information'.\n"
            "- If the topic is a company, include queries for financials, leadership, competitors, and recent news.\n"
            "- If the topic is a product/technology, include queries for pricing, alternatives, user reviews, and benchmarks.\n\n"
            f"Input:\n{payload}"
        ),
        temperature=0.1,
        timeout_seconds=10,
        max_tokens=360,
    )
    if not isinstance(response, dict):
        return []
    raw = response.get("gap_queries")
    if not isinstance(raw, list):
        return []
    original_lower = str(original_query or "").strip().lower()
    clean: list[str] = []
    seen: set[str] = set()
    for item in raw:
        text = " ".join(str(item or "").split()).strip()[:160]
        key = text.lower()
        if not text or key == original_lower or key in seen:
            continue
        seen.add(key)
        clean.append(text)
        if len(clean) >= max_queries:
            break
    return clean


def run_enrichment_and_finalize_stage(
    *,
    context: ToolExecutionContext,
    depth_tier: str,
    max_search_rounds: int,
    query: str,
    query_variants: list[str],
    min_unique_sources: int,
    results_per_query: int,
    requested_provider: str,
    allow_provider_fallback: bool,
    requested_search_budget: int,
    planned_result_budget: int,
    max_query_variants: int,
    fused_top_k: int,
    domain_scope_hosts: list[str],
    domain_scope_mode: str,
    trace_events: list[ToolTraceEvent],
    sources: list[AgentSource],
    bullets: list[str],
    state: dict[str, Any],
    _research_branches: list[dict[str, Any]],
    get_connector_registry_fn: Callable[..., Any],
):
    get_connector_registry = get_connector_registry_fn
    ok = bool(state.get("ok"))
    used_provider = str(state.get("used_provider") or requested_provider)
    provider_attempted = state.get("provider_attempted")
    if not isinstance(provider_attempted, list):
        provider_attempted = []
    provider_failures = state.get("provider_failures")
    if not isinstance(provider_failures, list):
        provider_failures = []
    domain_scope_filtered_out = int(state.get("domain_scope_filtered_out") or 0)
    # ── S1: Supplemental source federation (arxiv, sec_edgar, newsapi, reddit) ─
    if ok:
        _registry = get_connector_registry()
        _sup_plan = _build_provider_plan(
            depth_tier=depth_tier,
            query=query_variants[0] if query_variants else query,
            registry_names=_registry.names(),
        )
        _seen_sup_urls: set[str] = {str(s.url or "") for s in sources}
        for _conn_id, _result_count in _sup_plan:
            try:
                _connector = _registry.build(_conn_id, settings=context.settings)
                _sup_start = ToolTraceEvent(
                    event_type="api_call_started",
                    title=f"Query {_conn_id}",
                    detail=_safe_snippet(query_variants[0] if query_variants else query, 120),
                    data={"provider": _conn_id, "result_limit": _result_count},
                )
                trace_events.append(_sup_start)
                yield _sup_start
                _sup_payload = _connector.search_web(
                    query=query_variants[0] if query_variants else query,
                    count=_result_count,
                )
                _sup_rows = _sup_payload.get("results") if isinstance(_sup_payload, dict) else []
                if not isinstance(_sup_rows, list):
                    _sup_rows = []
                _sup_done = ToolTraceEvent(
                    event_type="api_call_completed",
                    title=f"{_conn_id} completed",
                    detail=f"{len(_sup_rows)} result(s)",
                    data={"provider": _conn_id, "result_count": len(_sup_rows)},
                )
                trace_events.append(_sup_done)
                yield _sup_done
                from api.services.agent.research.source_credibility import (
                    apply_freshness_weight,
                    score_source_credibility,
                    score_source_freshness,
                )
                for _row in _sup_rows:
                    if not isinstance(_row, dict):
                        continue
                    _url = str(_row.get("url") or "").strip()
                    if not _url or _url in _seen_sup_urls:
                        continue
                    _seen_sup_urls.add(_url)
                    _name = str(_row.get("title") or _url or "Source").strip()
                    _desc = str(_row.get("description") or "").strip()
                    _excerpt = _safe_snippet(_desc or _name or _url, 220)
                    _cred = score_source_credibility(_url)
                    _fresh = score_source_freshness(_url, _desc)
                    _composite = apply_freshness_weight(_cred, _fresh)
                    sources.append(
                        AgentSource(
                            source_type="web",
                            label=_name,
                            url=_url or None,
                            score=max(0.5, min(0.98, 0.60 + _composite * 0.40)),
                            credibility_score=_cred,
                            metadata={
                                "provider": _conn_id,
                                "excerpt": _excerpt,
                                "extract": _excerpt,
                            },
                        )
                    )
                    if len(bullets) < 32:
                        bullets.append(f"- {_name}: {_safe_snippet(_desc or _name)}")
            except Exception as _sup_exc:
                _sup_failure = _classify_provider_failure(_sup_exc)
                _sup_failure["provider"] = _conn_id
                provider_failures.append(_sup_failure)

        # ── S2: Execute research tree branches ────────────────────────────────
        # Each branch targets a different angle (Financial, Academic, News…) and
        # uses its preferred providers.  A per-provider circuit breaker skips any
        # provider that has already failed 3+ times in this run.
        if _research_branches:
            # Load/init the circuit-breaker failure counter from context.
            _circuit_failures: dict[str, int] = context.settings.get(
                "__provider_circuit_failures"
            )
            if not isinstance(_circuit_failures, dict):
                _circuit_failures = {}
                context.settings["__provider_circuit_failures"] = _circuit_failures
            _circuit_threshold = 3
            _seen_branch_urls: set[str] = {str(s.url or "") for s in sources}

            for _branch in _research_branches:
                _blabel = _branch["branch_label"]
                _bsub = _branch["sub_question"]
                _bproviders = _branch.get("preferred_providers") or ["brave_search"]

                # Pick the first provider not tripped by the circuit breaker.
                _chosen_provider: str | None = None
                for _bp in _bproviders:
                    if _circuit_failures.get(_bp, 0) < _circuit_threshold:
                        _chosen_provider = _bp
                        break
                if _chosen_provider is None:
                    _logger.warning(
                        "research_branch_skipped branch=%s reason=all_providers_circuit_open",
                        _blabel,
                    )
                    continue

                _branch_new = 0
                try:
                    _bconnector = get_connector_registry().build(
                        _chosen_provider, settings=context.settings
                    )
                    _bpayload = _bconnector.search_web(query=_bsub, count=results_per_query)
                    _brows = _bpayload.get("results") if isinstance(_bpayload, dict) else []
                    if not isinstance(_brows, list):
                        _brows = []
                    from api.services.agent.research.source_credibility import (
                        apply_freshness_weight,
                        score_source_credibility,
                        score_source_freshness,
                    )
                    for _brow in _brows:
                        if not isinstance(_brow, dict):
                            continue
                        _burl = str(_brow.get("url") or "").strip()
                        if not _burl or _burl in _seen_branch_urls:
                            continue
                        _seen_branch_urls.add(_burl)
                        _bname = str(_brow.get("title") or _burl).strip()
                        _bdesc = str(_brow.get("description") or _brow.get("snippet") or "").strip()
                        _bexcerpt = _safe_snippet(_bdesc or _bname, 220)
                        _bcred = score_source_credibility(_burl)
                        _bfresh = score_source_freshness(_burl, _bdesc)
                        _bcomp = apply_freshness_weight(_bcred, _bfresh)
                        sources.append(
                            AgentSource(
                                source_type="web",
                                label=_bname,
                                url=_burl or None,
                                score=max(0.5, min(0.98, 0.60 + _bcomp * 0.40)),
                                credibility_score=_bcred,
                                metadata={
                                    "provider": _chosen_provider,
                                    "branch": _blabel,
                                    "excerpt": _bexcerpt,
                                    "extract": _bexcerpt,
                                },
                            )
                        )
                        if len(bullets) < 48:
                            bullets.append(f"- {_bname}: {_safe_snippet(_bdesc or _bname)}")
                        _branch_new += 1
                except Exception as _bexc:
                    _bfail = _classify_provider_failure(_bexc)
                    _circuit_failures[_chosen_provider] = (
                        _circuit_failures.get(_chosen_provider, 0) + 1
                    )
                    provider_failures.append({**_bfail, "provider": _chosen_provider, "branch": _blabel})
                    _logger.warning(
                        "research_branch_failed branch=%s provider=%s failures=%d reason=%s",
                        _blabel,
                        _chosen_provider,
                        _circuit_failures[_chosen_provider],
                        _bfail.get("reason"),
                    )

                _branch_done = ToolTraceEvent(
                    event_type="research_branch_completed",
                    title=f"Branch complete: {_blabel}",
                    detail=f"{_branch_new} new result(s) via {_chosen_provider}",
                    data={
                        "branch_label": _blabel,
                        "result_count": _branch_new,
                        "provider_used": _chosen_provider,
                        "preferred_providers": _bproviders,
                    },
                )
                trace_events.append(_branch_done)
                yield _branch_done

    # ── T3: Emit evidence_crystallized for top sources ─────────────────────
    _crystal_cap = 4 if depth_tier in ("deep_research", "deep_analytics", "expert") else 2
    _crystal_count = 0
    for _src in sources:
        if _crystal_count >= _crystal_cap:
            break
        _src_score = float(getattr(_src, "score", 0.0) or 0.0)
        if _src_score < 0.72:
            continue
        _src_label = str(getattr(_src, "label", "") or "").strip()
        _src_url = str(getattr(_src, "url", "") or "").strip()
        _src_excerpt = str((getattr(_src, "metadata", {}) or {}).get("excerpt", "") or "").strip()
        _crystal_event = ToolTraceEvent(
            event_type="evidence_crystallized",
            title=f"Evidence found: {_src_label[:48] or _src_url[:48]}",
            detail=_safe_snippet(_src_excerpt or _src_label, 120),
            data={
                "source_name": _src_label,
                "source_url": _src_url,
                "extract": _safe_snippet(_src_excerpt, 120),
                "strength_score": round(_src_score, 3),
                "provider": (getattr(_src, "metadata", {}) or {}).get("provider", used_provider),
                "highlight_regions": [
                    {"x": 8, "y": 20, "width": 84, "height": 12, "color": "gold"}
                ],
            },
        )
        trace_events.append(_crystal_event)
        yield _crystal_event
        _crystal_count += 1

    # ── T4: Emit trust_score_updated after sources are crystallized ─────────
    if sources:
        _scores = [float(getattr(s, "score", 0.0) or 0.0) for s in sources]
        _avg_trust = round(sum(_scores) / len(_scores), 3)
        _gate = "green" if _avg_trust >= 0.80 else "amber" if _avg_trust >= 0.55 else "red"
        _contested = sum(1 for s in sources if float(getattr(s, "score", 0.0) or 0.0) < 0.60)
        _trust_event = ToolTraceEvent(
            event_type="trust_score_updated",
            title="Trust score updated",
            detail=f"Source credibility: {_gate} ({_avg_trust:.2f})",
            data={
                "trust_score": _avg_trust,
                "gate_color": _gate,
                "reason": f"{len(sources)} sources evaluated; {_contested} low-credibility",
                "source_count": len(sources),
            },
        )
        trace_events.append(_trust_event)
        yield _trust_event

    if bullets:
        highlight_terms = []
        for source in sources[:6]:
            label = str(source.label or "").strip()
            if label:
                highlight_terms.extend(re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}", label))
        dedup_terms = []
        for term in highlight_terms:
            lowered = term.lower()
            if lowered not in dedup_terms:
                dedup_terms.append(lowered)
            if len(dedup_terms) >= 8:
                break
        if dedup_terms:
            highlight_event = ToolTraceEvent(
                event_type="browser_keyword_highlight",
                title="Highlight search keywords",
                detail=", ".join(dedup_terms[:6]),
                data={"keywords": dedup_terms[:8]},
            )
            trace_events.append(highlight_event)
            yield highlight_event
        snippet_text = _safe_snippet(" | ".join(bullets), 320)
        if snippet_text:
            copy_event = ToolTraceEvent(
                event_type="clipboard_copy",
                title="Copy web snippets",
                detail=snippet_text,
                data={"clipboard_text": snippet_text},
            )
            trace_events.append(copy_event)
            yield copy_event

    unique_urls = list(
        dict.fromkeys(
            [str(source.url or "").strip() for source in sources if str(source.url or "").strip()]
        )
    )
    if len(unique_urls) < min_unique_sources:
        shortfall_event = ToolTraceEvent(
            event_type="tool_progress",
            title="Research coverage shortfall detected",
            detail=(
                f"Collected {len(unique_urls)} unique sources; target is {min_unique_sources}. "
                "Continue with additional targeted queries."
            ),
            data=_website_scene_payload(
                lane="research-coverage-check",
                primary_index=max(1, len(unique_urls)),
                secondary_index=max(1, min_unique_sources),
                payload={
                    "source_count": len(unique_urls),
                    "target_source_count": min_unique_sources,
                    "coverage_ok": False,
                    "domain_scope_hosts": domain_scope_hosts[:6],
                    "domain_scope_mode": domain_scope_mode,
                },
            ),
        )
        trace_events.append(shortfall_event)
        yield shortfall_event

    # ── Iterative gap-fill rounds ─────────────────────────────────────────
    # For deep_research / expert tiers (max_search_rounds ≥ 2), run up to
    # (max_search_rounds - 1) additional targeted search passes when coverage
    # is below the minimum.  Each round extracts topics from the top sources
    # collected so far and fires gap-fill queries for them.
    if ok and max_search_rounds >= 2 and len(unique_urls) < min_unique_sources:
        _seen_gap_urls: set[str] = set(unique_urls)
        _gap_round_limit = max_search_rounds - 1  # round 1 already done above

        for _gap_round in range(1, _gap_round_limit + 1):
            # Coverage already met by a previous gap round — stop early.
            if len(_seen_gap_urls) >= min_unique_sources:
                break

            # Build label/excerpt lists from top-scoring sources for gap analysis.
            _top_labels = [
                str(getattr(s, "label", "") or "").strip()
                for s in sorted(sources, key=lambda x: float(getattr(x, "score", 0) or 0), reverse=True)[:12]
            ]
            _top_excerpts = [
                str((getattr(s, "metadata", {}) or {}).get("excerpt", "") or "").strip()
                for s in sources[:8]
            ]

            # Primary: LLM-generated gap queries targeting uncovered angles.
            _gap_queries = _llm_gap_fill_queries(
                original_query=query,
                covered_labels=_top_labels,
                covered_excerpts=_top_excerpts,
                max_queries=4,
            )

            # Fallback: regex named-entity extraction when LLM is disabled or returns nothing.
            if not _gap_queries:
                _all_terms: list[str] = []
                for _text in _top_labels[:10] + _top_excerpts[:6]:
                    _all_terms.extend(re.findall(r"\b[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,}){0,3}\b", _text))
                _unique_terms: list[str] = []
                _seen_t: set[str] = set()
                for _t in _all_terms:
                    _lt = _t.lower()
                    if _lt not in _seen_t and _lt not in query.lower():
                        _seen_t.add(_lt)
                        _unique_terms.append(_t)
                    if len(_unique_terms) >= 6:
                        break
                _gap_queries = [f"{query} {_t}" for _t in _unique_terms[:4]]

            if not _gap_queries:
                break
            _gap_budget = max(results_per_query, min(20, min_unique_sources - len(_seen_gap_urls)))

            _gap_start = ToolTraceEvent(
                event_type="tool_progress",
                title=f"Gap-fill search round {_gap_round + 1}",
                detail=f"Targeting {len(_gap_queries)} topic angles to fill {min_unique_sources - len(_seen_gap_urls)} source gap",
                data={
                    "gap_round": _gap_round + 1,
                    "gap_queries": _gap_queries[:4],
                    "target_additional": min_unique_sources - len(_seen_gap_urls),
                },
            )
            trace_events.append(_gap_start)
            yield _gap_start

            _gap_search_runs: list[dict[str, Any]] = []
            for _gq in _gap_queries:
                try:
                    _gap_connector = get_connector_registry().build("brave_search", settings=context.settings)
                    _gap_payload = _gap_connector.search_web(query=_gq, count=_gap_budget)
                    if isinstance(_gap_payload, dict):
                        _gap_search_runs.append({"query": _gq, "results": _gap_payload.get("results") or []})
                except Exception as _gap_exc:
                    _gfail = _classify_provider_failure(_gap_exc)
                    _logger.warning(
                        "gap_fill_search_failed query=%s reason=%s",
                        _safe_snippet(_gq, 120),
                        _gfail.get("reason"),
                    )

            if _gap_search_runs:
                _gap_fused = _fuse_search_results(_gap_search_runs, top_k=_gap_budget * len(_gap_queries))
                for _gr in _gap_fused:
                    if not isinstance(_gr, dict):
                        continue
                    _gurl = str(_gr.get("url") or "").strip()
                    if not _gurl or _gurl in _seen_gap_urls:
                        continue
                    _seen_gap_urls.add(_gurl)
                    _gname = str(_gr.get("title") or _gurl or "Web result").strip()
                    _gsnippet = str(_gr.get("description") or _gr.get("snippet") or "").strip()
                    _gexcerpt = _safe_snippet(_gsnippet or _gname, 220)
                    try:
                        _grrf = float(_gr.get("rrf_score") or 0.0)
                    except Exception:
                        _grrf = 0.0
                    from api.services.agent.research.source_credibility import (
                        apply_freshness_weight,
                        score_source_credibility,
                        score_source_freshness,
                    )
                    _gcred = score_source_credibility(_gurl)
                    _gfresh = score_source_freshness(_gurl, _gsnippet)
                    _gcomposite = apply_freshness_weight(_gcred, _gfresh)
                    _gbase = max(0.5, min(0.92, 0.62 + (_grrf * 100)))
                    _gscore = round((0.70 * _gbase + 0.30 * (0.60 + _gcomposite * 0.40)), 4)
                    sources.append(
                        AgentSource(
                            source_type="web",
                            label=_gname,
                            url=_gurl or None,
                            score=max(0.5, min(0.92, _gscore)),
                            metadata={
                                "provider": "brave_search_gap",
                                "excerpt": _gexcerpt,
                                "extract": _gexcerpt,
                                "gap_round": _gap_round + 1,
                            },
                        )
                    )
                    if len(bullets) < 48:
                        bullets.append(f"- {_gname}: {_safe_snippet(_gsnippet or _gname)}")

            _gap_done = ToolTraceEvent(
                event_type="tool_progress",
                title=f"Gap-fill round {_gap_round + 1} complete",
                detail=f"Now at {len(_seen_gap_urls)} unique sources (target: {min_unique_sources})",
                data={
                    "gap_round": _gap_round + 1,
                    "source_count_now": len(_seen_gap_urls),
                    "target_source_count": min_unique_sources,
                    "coverage_ok": len(_seen_gap_urls) >= min_unique_sources,
                },
            )
            trace_events.append(_gap_done)
            yield _gap_done

        # Refresh unique_urls after gap-fill passes
        unique_urls = list(
            dict.fromkeys(
                [str(source.url or "").strip() for source in sources if str(source.url or "").strip()]
            )
        )

    content = "\n".join(bullets)
    summary = (
        f"Collected {len(sources)} web sources ({len(unique_urls)} unique URLs) "
        f"using {used_provider}: {query}"
    )
    if sources:
        # Apply MMR reranking for domain diversity on deep-research tiers before
        # saving so the report generator gets a varied source set rather than
        # clustering on the top-ranked domain.
        if depth_tier in {"deep_research", "deep_analytics", "expert"} and len(sources) > 20:
            _mmr_cap = min(200, len(sources))
            _source_dicts = [
                {"url": str(s.url or ""), "rrf_score": float(getattr(s, "score", 0.0) or 0.0)}
                for s in sources
            ]
            _mmr_order = _mmr_rerank(_source_dicts, top_k=_mmr_cap, lambda_param=0.72)
            _url_order = [str(r.get("url") or "") for r in _mmr_order]
            _src_by_url = {str(s.url or ""): s for s in sources}
            sources = [_src_by_url[u] for u in _url_order if u in _src_by_url]
            # Append any sources not captured by MMR at the end (safety).
            _mmr_url_set = set(_url_order)
            for _s in list(_src_by_url.values()):
                if str(_s.url or "") not in _mmr_url_set:
                    sources.append(_s)

        context.settings["__latest_web_sources"] = [
            source.to_dict()
            for source in sources[:200]
        ]
        context.settings["__latest_web_query"] = query
        context.settings["__latest_web_provider"] = used_provider
        context.settings["__latest_web_source_count"] = len(unique_urls)
        context.settings["__latest_web_source_target"] = min_unique_sources
        context.settings["__latest_research_depth_tier"] = depth_tier
        context.settings["__latest_web_domain_scope_hosts"] = domain_scope_hosts[:6]
        context.settings["__latest_web_domain_scope_mode"] = domain_scope_mode
        context.settings["__latest_web_domain_scope_filtered_out"] = int(domain_scope_filtered_out)
    next_steps = [
        "Validate top 2 sources against internal company data.",
        "Convert findings into a competitor/market briefing.",
    ]
    if len(unique_urls) < min_unique_sources:
        next_steps.insert(
            0,
            f"Run another research pass to reach at least {min_unique_sources} unique sources.",
        )
    return ToolExecutionResult(
        summary=summary,
        content=content,
        data={
            "query": query,
            "query_variants": query_variants,
            "max_query_variants": max_query_variants,
            "results_per_query": results_per_query,
            "search_budget_requested": requested_search_budget,
            "search_budget_effective": planned_result_budget,
            "fused_top_k": fused_top_k,
            "research_depth_tier": depth_tier,
            "provider": used_provider,
            "provider_requested": requested_provider,
            "provider_fallback_enabled": allow_provider_fallback,
            "provider_attempted": provider_attempted[:4],
            "provider_failures": provider_failures[:4],
            "source_count": len(sources),
            "unique_source_count": len(unique_urls),
            "min_unique_sources": min_unique_sources,
            "coverage_ok": len(unique_urls) >= min_unique_sources,
            "items": [source.to_dict() for source in sources],
            "domain_scope_hosts": domain_scope_hosts[:6],
            "domain_scope_mode": domain_scope_mode,
            "domain_scope_filtered_out": int(domain_scope_filtered_out),
        },
        sources=sources,
        next_steps=next_steps,
        events=trace_events,
    )

