from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


def selected_source_ids(selected_payload: dict[str, list[Any]]) -> set[str]:
    ids: set[str] = set()
    for value in (selected_payload or {}).values():
        if not isinstance(value, list) or len(value) < 2:
            continue
        mode = str(value[0] or "").strip().lower()
        if mode != "select":
            continue
        file_ids = value[1] if isinstance(value[1], list) else []
        for file_id in file_ids:
            normalized = str(file_id or "").strip()
            if normalized:
                ids.add(normalized)
    return ids


def snippet_score(row: dict[str, Any]) -> float:
    try:
        return float(row.get("score", 0.0) or 0.0)
    except Exception:
        return 0.0


def annotate_primary_sources(
    *,
    question: str,
    snippets: list[dict[str, Any]],
    selected_payload: dict[str, list[Any]],
    target_urls: list[str] | None,
    selected_source_ids_fn,
    normalize_http_url_fn,
    extract_urls_fn,
    normalize_host_fn,
    host_matches_fn,
    snippet_score_fn,
) -> tuple[list[dict[str, Any]], str]:
    if not snippets:
        return [], ""

    selected_ids = selected_source_ids_fn(selected_payload)
    resolved_target_urls = (
        [value for value in (target_urls or []) if normalize_http_url_fn(value)]
        or extract_urls_fn(question, max_urls=6)
    )
    has_url_targets = bool(resolved_target_urls)
    target_url_set = {value for value in resolved_target_urls if value}
    target_hosts = {
        normalize_host_fn(value)
        for value in resolved_target_urls
        if normalize_host_fn(value)
    }
    target_paths = {
        str(urlparse(value).path or "").strip().lower()
        for value in resolved_target_urls
        if value
    }

    annotated: list[dict[str, Any]] = []
    primary_count = 0
    for row in snippets:
        item = dict(row)
        source_id = str(item.get("source_id", "") or "").strip()
        source_url = normalize_http_url_fn(
            item.get("source_url")
            or item.get("page_url")
            or item.get("url")
            or item.get("source_name")
        )
        source_host = normalize_host_fn(source_url)
        source_path = str(urlparse(source_url).path or "").strip().lower() if source_url else ""

        exact_url_match = bool(source_url and source_url in target_url_set)
        path_match = bool(source_path and source_path in target_paths and source_path not in {"", "/"})
        host_match = bool(
            source_host
            and target_hosts
            and any(host_matches_fn(source_host, host) for host in target_hosts)
        )
        selected_match = bool(source_id and source_id in selected_ids)

        if has_url_targets:
            is_primary = exact_url_match or path_match or host_match
        else:
            is_primary = selected_match or exact_url_match or path_match or host_match

        item["source_url"] = source_url
        item["is_primary_source"] = bool(is_primary)
        if is_primary:
            primary_count += 1
            item["score"] = snippet_score_fn(item) + 80.0
        annotated.append(item)

    if primary_count <= 0:
        return annotated, ""

    sort_rows = sorted(
        annotated,
        key=lambda row: (
            0 if bool(row.get("is_primary_source")) else 1,
            -snippet_score_fn(row),
            str(row.get("source_name", "") or ""),
            str(row.get("page_label", "") or ""),
        ),
    )
    if resolved_target_urls:
        primary_note = f"Primary source target from user or conversation context: {', '.join(resolved_target_urls[:3])}"
    elif selected_ids:
        primary_note = (
            "Primary source target from user-selected file(s): "
            f"{', '.join(sorted(selected_ids)[:3])}"
        )
    else:
        primary_note = "Primary source target inferred from user-provided sources."
    return sort_rows, primary_note


def prioritize_primary_evidence(
    snippets: list[dict[str, Any]],
    *,
    max_keep: int,
    max_secondary: int,
    snippet_score_fn,
) -> list[dict[str, Any]]:
    if not snippets:
        return []
    keep_limit = max(1, int(max_keep))
    ordered = sorted(
        [dict(row) for row in snippets],
        key=lambda row: (
            0 if bool(row.get("is_primary_source")) else 1,
            -snippet_score_fn(row),
            str(row.get("source_name", "") or ""),
            str(row.get("page_label", "") or ""),
        ),
    )
    primary_rows = [row for row in ordered if bool(row.get("is_primary_source"))]
    secondary_rows = [row for row in ordered if not bool(row.get("is_primary_source"))]
    if not primary_rows:
        # No primary sources — apply source-diversity selection across all snippets.
        return _diverse_select(ordered, keep_limit)

    keep_secondary = min(max(0, int(max_secondary)), max(0, keep_limit - 1))
    result: list[dict[str, Any]] = []
    # Fill primary slots with source diversity — don't let one file consume all slots.
    result.extend(_diverse_select(primary_rows, keep_limit))
    if len(result) < keep_limit:
        remaining_slots = min(keep_limit - len(result), keep_secondary)
        result.extend(_diverse_select(secondary_rows, remaining_slots))
    return result[:keep_limit]


def _diverse_select(
    ordered: list[dict[str, Any]],
    keep_limit: int,
) -> list[dict[str, Any]]:
    """Round-robin selection across unique sources so no single source dominates.

    Pass 1: pick the top-scoring chunk from each unique source.
    Pass 2: fill remaining slots with next-best chunks, still rotating sources.
    """
    if not ordered or keep_limit <= 0:
        return []
    # Group by source name (stable order preserved from pre-sorted input).
    from collections import OrderedDict
    buckets: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for row in ordered:
        key = str(row.get("source_name", "") or row.get("source_id", "") or "").strip()
        buckets.setdefault(key, []).append(row)
    result: list[dict[str, Any]] = []
    # Keep iterating through source buckets round-robin until we hit keep_limit.
    while len(result) < keep_limit:
        added_any = False
        for key in list(buckets.keys()):
            if len(result) >= keep_limit:
                break
            if buckets[key]:
                result.append(buckets[key].pop(0))
                added_any = True
        if not added_any:
            break
    return result


def build_no_relevant_evidence_answer(
    question: str,
    *,
    target_url: str,
    response_language: str | None,
    normalize_http_url_fn,
    extract_first_url_fn,
) -> str:
    normalized_language = " ".join(str(response_language or "").split()).strip().lower()
    localized: dict[str, tuple[str, str]] = {
        "es": (
            "No pude encontrar evidencia indexada para {url} en este contexto del proyecto. "
            "No es visible en el contenido indexado. Si lo necesitas, ejecuta el indexado del sitio web o una busqueda en linea para esa URL y vuelve a preguntar.",
            "No pude encontrar evidencia relevante en los archivos indexados del proyecto ni en el contexto reciente de la conversacion para esta pregunta. "
            "No es visible en el contenido indexado.",
        ),
        "fr": (
            "Je n'ai pas trouve de preuves indexees pour {url} dans ce contexte de projet. "
            "Ce n'est pas visible dans le contenu indexe. Si besoin, lancez l'indexation du site web ou une recherche en ligne pour cette URL, puis reposez la question.",
            "Je n'ai pas trouve de preuves pertinentes dans les fichiers de projet indexes ni dans le contexte recent de la conversation pour cette question. "
            "Ce n'est pas visible dans le contenu indexe.",
        ),
        "de": (
            "Ich konnte in diesem Projektkontext keine indexierten Belege fuer {url} finden. "
            "Im indexierten Inhalt nicht sichtbar. Falls noetig, starten Sie die Website-Indexierung oder eine Online-Suche fuer diese URL und fragen Sie dann erneut.",
            "Ich konnte in den indexierten Projektdateien und im aktuellen Gespraechskontext keine relevanten Belege fuer diese Frage finden. "
            "Im indexierten Inhalt nicht sichtbar.",
        ),
        "it": (
            "Non ho trovato evidenze indicizzate per {url} in questo contesto di progetto. "
            "Non visibile nei contenuti indicizzati. Se necessario, esegui l'indicizzazione del sito web o una ricerca online per quell'URL e chiedi di nuovo.",
            "Non ho trovato evidenze rilevanti nei file di progetto indicizzati e nel contesto recente della conversazione per questa domanda. "
            "Non visibile nei contenuti indicizzati.",
        ),
        "pt": (
            "Nao encontrei evidencia indexada para {url} neste contexto do projeto. "
            "Nao esta visivel no conteudo indexado. Se necessario, execute a indexacao do site ou uma pesquisa online para essa URL e pergunte novamente.",
            "Nao encontrei evidencia relevante nos arquivos indexados do projeto nem no contexto recente da conversa para esta pergunta. "
            "Nao esta visivel no conteudo indexado.",
        ),
        "nl": (
            "Ik kon geen geindexeerd bewijs voor {url} vinden in deze projectcontext. "
            "Niet zichtbaar in geindexeerde inhoud. Start zo nodig website-indexering of online zoeken voor die URL en vraag het daarna opnieuw.",
            "Ik kon geen relevant bewijs vinden in geindexeerde projectbestanden en recente gesprekscontext voor deze vraag. "
            "Niet zichtbaar in geindexeerde inhoud.",
        ),
    }
    resolved_target_url = normalize_http_url_fn(target_url) or extract_first_url_fn(question)
    localized_pair = localized.get(normalized_language)
    if resolved_target_url:
        if localized_pair:
            return localized_pair[0].format(url=resolved_target_url)
        return (
            f"I could not find indexed evidence for {resolved_target_url} in this project context. "
            "Not visible in indexed content. If needed, run website indexing or online search for that URL, then ask again."
        )
    if localized_pair:
        return localized_pair[1]
    return (
        "I could not find relevant evidence in indexed project files and recent conversation context for this question. "
        "Not visible in indexed content."
    )
