"""Stub — old citation shared replaced by api.services.rag.citations."""
ALLOWED_CITATION_MODES = {"inline", "footnote"}
CITATION_MODE_INLINE = "inline"
CITATION_MODE_FOOTNOTE = "footnote"

def normalize_info_evidence_html(*args, **kwargs):
    return args[0] if args else ""

def _sentence_grade_extract(*args, **kwargs):
    return []
