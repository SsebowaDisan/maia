from difflib import SequenceMatcher


def _normalize_with_index(text: str) -> tuple[str, list[int]]:
    normalized_chars: list[str] = []
    index_map: list[int] = []
    previous_space = False
    for idx, char in enumerate(str(text or "").lower()):
        if char.isalnum():
            normalized_chars.append(char)
            index_map.append(idx)
            previous_space = False
            continue
        if char.isspace() or char in {".", ",", ";", ":", "!", "?", "-", "_", "/", "\\", "(", ")", "[", "]", "{", "}"}:
            if previous_space:
                continue
            normalized_chars.append(" ")
            index_map.append(idx)
            previous_space = True
    normalized = "".join(normalized_chars).strip()
    # rebuild index map after strip
    if not normalized:
        return "", []
    left = 0
    while left < len(normalized_chars) and normalized_chars[left] == " ":
        left += 1
    right = len(normalized_chars) - 1
    while right >= 0 and normalized_chars[right] == " ":
        right -= 1
    return normalized, index_map[left : right + 1]


def find_text_fuzzy(search_span: str, context: str, min_length: int = 5):
    search_norm, _ = _normalize_with_index(search_span)
    context_norm, context_idx_map = _normalize_with_index(context)
    if len(search_norm) <= min_length or len(context_norm) <= min_length:
        return []
    match = SequenceMatcher(
        None,
        search_norm,
        context_norm,
        autojunk=False,
    ).find_longest_match(0, len(search_norm), 0, len(context_norm))
    if match.size <= max(len(search_norm) * 0.35, min_length):
        return []
    try:
        start = context_idx_map[match.b]
        end = context_idx_map[min(len(context_idx_map) - 1, match.b + match.size - 1)] + 1
    except Exception:
        return []
    if end <= start:
        return []
    return [(start, end)]


def find_start_end_phrase_fuzzy(
    start_phrase,
    end_phrase,
    context,
    min_length: int = 5,
    max_excerpt_length: int = 300,
):
    matches = []
    matched_length = 0

    for phrase in [start_phrase, end_phrase]:
        if phrase is None:
            continue
        fuzzy = find_text_fuzzy(str(phrase), str(context), min_length=min_length)
        if not fuzzy:
            continue
        matches.append(fuzzy[0])
        matched_length += max(0, fuzzy[0][1] - fuzzy[0][0])

    if len(matches) == 2 and matches[1][0] < matches[0][0]:
        matches = [matches[0]]

    if not matches:
        return None, 0

    start_idx = min(start for start, _ in matches)
    end_idx = max(end for _, end in matches)
    if end_idx - start_idx > max_excerpt_length:
        end_idx = start_idx + max_excerpt_length
    return (start_idx, end_idx), matched_length


def find_text(search_span, context, min_length=5):
    search_span, context = search_span.lower(), context.lower()

    sentence_list = search_span.split("\n")
    context = context.replace("\n", " ")

    matches_span = []
    # don't search for small text
    if len(search_span) > min_length:
        for sentence in sentence_list:
            match_results = SequenceMatcher(
                None,
                sentence,
                context,
                autojunk=False,
            ).get_matching_blocks()

            matched_blocks = []
            for _, start, length in match_results:
                if length > max(len(sentence) * 0.25, min_length):
                    matched_blocks.append((start, start + length))

            if matched_blocks:
                start_index = min(start for start, _ in matched_blocks)
                end_index = max(end for _, end in matched_blocks)
                length = end_index - start_index

                if length > max(len(sentence) * 0.35, min_length):
                    matches_span.append((start_index, end_index))

    if matches_span:
        # merge all matches into one span
        final_span = min(start for start, _ in matches_span), max(
            end for _, end in matches_span
        )
        matches_span = [final_span]

    return matches_span


def find_start_end_phrase(
    start_phrase, end_phrase, context, min_length=5, max_excerpt_length=300
):
    start_phrase, end_phrase = start_phrase.lower(), end_phrase.lower()
    context = context.lower()

    context = context.replace("\n", " ")

    matches = []
    matched_length = 0
    for sentence in [start_phrase, end_phrase]:
        if sentence is None:
            continue

        match = SequenceMatcher(
            None, sentence, context, autojunk=False
        ).find_longest_match()
        if match.size > max(len(sentence) * 0.35, min_length):
            matches.append((match.b, match.b + match.size))
            matched_length += match.size

    # check if second match is before the first match
    if len(matches) == 2 and matches[1][0] < matches[0][0]:
        # if so, keep only the first match
        matches = [matches[0]]

    if matches:
        start_idx = min(start for start, _ in matches)
        end_idx = max(end for _, end in matches)

        # check if the excerpt is too long
        if end_idx - start_idx > max_excerpt_length:
            end_idx = start_idx + max_excerpt_length

        final_match = (start_idx, end_idx)
    else:
        final_match = None

    return final_match, matched_length


def replace_think_tag_with_details(text):
    text = text.replace(
        "<think>",
        '<details><summary><span style="color:grey">Thought</span></summary><blockquote>',  # noqa
    )
    text = text.replace("</think>", "</blockquote></details>")
    return text


def strip_think_tag(text):
    if "</think>" in text:
        text = text.split("</think>")[1]
    return text
