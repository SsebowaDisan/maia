"""B4-02 — GitHub connector tools.

Tools: vcs.create_pr, vcs.get_pr, vcs.list_issues, vcs.create_issue
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

_BASE = "https://api.github.com"


def _headers(credentials: dict) -> dict[str, str]:
    token = str(credentials.get("api_key") or credentials.get("access_token") or "")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _get(url: str, creds: dict, timeout: int) -> dict[str, Any]:
    req = urllib.request.Request(url, headers=_headers(creds))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {"status": resp.status, "data": json.loads(resp.read()), "error": None}
    except urllib.error.HTTPError as exc:
        return {"status": exc.code, "data": None, "error": exc.read().decode("utf-8", errors="ignore")[:300]}
    except Exception as exc:
        return {"status": 0, "data": None, "error": str(exc)[:300]}


def _post(url: str, body: dict, creds: dict, timeout: int) -> dict[str, Any]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=_headers(creds), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {"status": resp.status, "data": json.loads(resp.read()), "error": None}
    except urllib.error.HTTPError as exc:
        return {"status": exc.code, "data": None, "error": exc.read().decode("utf-8", errors="ignore")[:300]}
    except Exception as exc:
        return {"status": 0, "data": None, "error": str(exc)[:300]}


def _vcs_create_pr(params: dict, credentials: dict, timeout_seconds: int = 30, **_kw: Any) -> dict:
    repo = str(params.get("repo") or "")  # owner/repo
    title = str(params.get("title") or "")
    head = str(params.get("head") or "")
    base = str(params.get("base") or "main")
    body_text = str(params.get("body") or "")
    if not (repo and title and head):
        raise ValueError("vcs.create_pr requires 'repo', 'title', 'head'.")
    return _post(f"{_BASE}/repos/{repo}/pulls", {"title": title, "head": head, "base": base, "body": body_text}, credentials, timeout_seconds)


def _vcs_get_pr(params: dict, credentials: dict, timeout_seconds: int = 30, **_kw: Any) -> dict:
    repo = str(params.get("repo") or "")
    pr_number = int(params.get("pr_number") or 0)
    if not (repo and pr_number):
        raise ValueError("vcs.get_pr requires 'repo' and 'pr_number'.")
    return _get(f"{_BASE}/repos/{repo}/pulls/{pr_number}", credentials, timeout_seconds)


def _vcs_list_issues(params: dict, credentials: dict, timeout_seconds: int = 30, **_kw: Any) -> dict:
    repo = str(params.get("repo") or "")
    state = str(params.get("state") or "open")
    if not repo:
        raise ValueError("vcs.list_issues requires 'repo'.")
    return _get(f"{_BASE}/repos/{repo}/issues?state={state}&per_page=20", credentials, timeout_seconds)


def _vcs_create_issue(params: dict, credentials: dict, timeout_seconds: int = 30, **_kw: Any) -> dict:
    repo = str(params.get("repo") or "")
    title = str(params.get("title") or "")
    body_text = str(params.get("body") or "")
    if not (repo and title):
        raise ValueError("vcs.create_issue requires 'repo' and 'title'.")
    return _post(f"{_BASE}/repos/{repo}/issues", {"title": title, "body": body_text}, credentials, timeout_seconds)


def register(registry: dict) -> None:
    registry["vcs.create_pr"] = _vcs_create_pr
    registry["vcs.get_pr"] = _vcs_get_pr
    registry["vcs.list_issues"] = _vcs_list_issues
    registry["vcs.create_issue"] = _vcs_create_issue
