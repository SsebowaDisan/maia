from __future__ import annotations

from types import SimpleNamespace

from api.services.ollama import index_migration


class _FakeIndex:
    def __init__(self, index_id: int, name: str, embedding: str) -> None:
        self.id = index_id
        self.name = name
        self.config = {"embedding": embedding}


class _FakeIndexManager:
    def __init__(self, indices: list[_FakeIndex]) -> None:
        self.indices = indices
        self.updates: list[tuple[int, str, dict]] = []

    def update_index(self, index_id: int, name: str, config: dict) -> None:
        self.updates.append((index_id, name, dict(config)))
        for index in self.indices:
            if index.id == index_id:
                index.config = dict(config)
                return


class _FakeIngestionManager:
    def __init__(self) -> None:
        self.jobs: list[dict] = []

    def create_file_job(self, *, user_id: str, index_id: int, reindex: bool, files: list[dict]) -> dict:
        job_id = f"file-{index_id}-{len(self.jobs) + 1}"
        job = {
            "id": job_id,
            "kind": "files",
            "total_items": len(files),
            "index_id": index_id,
            "reindex": reindex,
            "user_id": user_id,
        }
        self.jobs.append(job)
        return job

    def create_url_job(
        self,
        *,
        user_id: str,
        index_id: int,
        reindex: bool,
        urls: list[str],
        web_crawl_depth: int,
        web_crawl_max_pages: int,
        web_crawl_same_domain_only: bool,
        include_pdfs: bool,
        include_images: bool,
    ) -> dict:
        job_id = f"url-{index_id}-{len(self.jobs) + 1}"
        job = {
            "id": job_id,
            "kind": "urls",
            "total_items": len(urls),
            "index_id": index_id,
            "reindex": reindex,
            "user_id": user_id,
            "web_crawl_depth": web_crawl_depth,
            "web_crawl_max_pages": web_crawl_max_pages,
            "web_crawl_same_domain_only": web_crawl_same_domain_only,
            "include_pdfs": include_pdfs,
            "include_images": include_images,
        }
        self.jobs.append(job)
        return job


def test_apply_embedding_to_all_indices_updates_config_and_queues_jobs(monkeypatch):
    indices = [
        _FakeIndex(index_id=1, name="File Collection", embedding="default"),
        _FakeIndex(index_id=2, name="Graph Collection", embedding="ollama-embed::nomic-embed-text"),
    ]
    manager = _FakeIndexManager(indices=indices)
    context = SimpleNamespace(app=SimpleNamespace(index_manager=manager))
    ingestion = _FakeIngestionManager()

    targets_by_index = {
        1: {"files": [{"name": "a.pdf", "path": "C:/tmp/a.pdf", "size": 10}], "urls": [], "skipped_sources": 0, "total_sources": 1},
        2: {"files": [], "urls": ["https://example.com"], "skipped_sources": 0, "total_sources": 1},
    }

    def _fake_collect_reindex_targets_for_index(*, index, user_id):
        assert user_id == "user-1"
        return targets_by_index[index.id]

    monkeypatch.setattr(
        index_migration,
        "collect_reindex_targets_for_index",
        _fake_collect_reindex_targets_for_index,
    )

    result = index_migration.apply_embedding_to_all_indices(
        context=context,
        user_id="user-1",
        embedding_name="ollama-embed::nomic-embed-text",
        ingestion_manager=ingestion,
    )

    assert result["indexes_total"] == 2
    assert result["indexes_updated"] == 1
    assert result["jobs_total"] == 2
    assert len(result["jobs"]) == 2
    assert manager.updates[0][0] == 1
    assert indices[0].config["embedding"] == "ollama-embed::nomic-embed-text"
