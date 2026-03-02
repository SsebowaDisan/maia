import os
import tempfile
from importlib import import_module
from importlib.util import find_spec

import pytest

# Use a per-run temp cache path for theflow to avoid stale diskcache lock contention
# from previous interrupted runs.
if "THEFLOW_TEMP_PATH" not in os.environ:
    os.environ["THEFLOW_TEMP_PATH"] = tempfile.mkdtemp(
        prefix="maia_pytest_theflow_"
    )


@pytest.fixture(scope="function")
def mock_google_search(monkeypatch):
    import googlesearch

    def result(*args, **kwargs):
        yield googlesearch.SearchResult(
            url="https://www.cinnamon.is/en/",
            title="Cinnamon AI",
            description="Cinnamon AI is an enterprise AI company.",
        )

    monkeypatch.setattr(googlesearch, "search", result)


def if_haystack_not_installed():
    return find_spec("haystack") is None


def if_sentence_bert_not_installed():
    return find_spec("sentence_transformers") is None


def if_sentence_fastembed_not_installed():
    return find_spec("fastembed") is None


def if_unstructured_pdf_not_installed():
    # Keep marker construction import-light; deeper capability checks happen in test runtime.
    return find_spec("unstructured") is None


def if_cohere_not_installed():
    return find_spec("cohere") is None


def if_llama_cpp_not_installed():
    return find_spec("llama_cpp") is None


def if_voyageai_not_installed():
    return find_spec("voyageai") is None


def if_milvus_lite_not_installed():
    return find_spec("milvus_lite") is None


def ensure_unstructured_pdf_runtime():
    try:
        import_module("unstructured.partition.auto")
        import_module("magic")
    except Exception as exc:
        pytest.skip(f"unstructured PDF support is unavailable: {exc}")


skip_when_haystack_not_installed = pytest.mark.skipif(
    if_haystack_not_installed(), reason="Haystack is not installed"
)

skip_when_sentence_bert_not_installed = pytest.mark.skipif(
    if_sentence_bert_not_installed(), reason="SBert is not installed"
)

skip_when_fastembed_not_installed = pytest.mark.skipif(
    if_sentence_fastembed_not_installed(), reason="fastembed is not installed"
)

skip_when_unstructured_pdf_not_installed = pytest.mark.skipif(
    if_unstructured_pdf_not_installed(), reason="unstructured is not installed"
)

skip_when_cohere_not_installed = pytest.mark.skipif(
    if_cohere_not_installed(), reason="cohere is not installed"
)

skip_openai_lc_wrapper_test = pytest.mark.skipif(
    True, reason="OpenAI LC wrapper test is skipped"
)

skip_llama_cpp_not_installed = pytest.mark.skipif(
    if_llama_cpp_not_installed(), reason="llama_cpp is not installed"
)

skip_when_voyageai_not_installed = pytest.mark.skipif(
    if_voyageai_not_installed(), reason="voyageai is not installed"
)

skip_when_milvus_lite_not_installed = pytest.mark.skipif(
    if_milvus_lite_not_installed(), reason="milvus_lite is not installed"
)
