"""B4-01 — Salesforce CRM connector tools.

Tools: crm.sf_get_contact, crm.sf_get_deal, crm.sf_update_deal,
       crm.sf_create_task, crm.sf_list_deals_by_stage
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def _headers(credentials: dict) -> dict[str, str]:
    token = str(credentials.get("access_token") or credentials.get("api_key") or "")
    instance = str(credentials.get("instance_url") or "https://login.salesforce.com")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "_instance": instance}


def _instance(credentials: dict) -> str:
    return str(credentials.get("instance_url") or "https://login.salesforce.com").rstrip("/")


def _get(path: str, credentials: dict, timeout: int) -> dict[str, Any]:
    url = f"{_instance(credentials)}{path}"
    hdrs = {k: v for k, v in _headers(credentials).items() if not k.startswith("_")}
    req = urllib.request.Request(url, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {"status": resp.status, "data": json.loads(resp.read()), "error": None}
    except urllib.error.HTTPError as exc:
        return {"status": exc.code, "data": None, "error": exc.read().decode("utf-8", errors="ignore")[:300]}
    except Exception as exc:
        return {"status": 0, "data": None, "error": str(exc)[:300]}


def _patch(path: str, body: dict, credentials: dict, timeout: int) -> dict[str, Any]:
    url = f"{_instance(credentials)}{path}"
    hdrs = {k: v for k, v in _headers(credentials).items() if not k.startswith("_")}
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=hdrs, method="PATCH")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {"status": resp.status, "data": None, "error": None}
    except urllib.error.HTTPError as exc:
        return {"status": exc.code, "data": None, "error": exc.read().decode("utf-8", errors="ignore")[:300]}
    except Exception as exc:
        return {"status": 0, "data": None, "error": str(exc)[:300]}


def _post_sf(path: str, body: dict, credentials: dict, timeout: int) -> dict[str, Any]:
    url = f"{_instance(credentials)}{path}"
    hdrs = {k: v for k, v in _headers(credentials).items() if not k.startswith("_")}
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {"status": resp.status, "data": json.loads(resp.read() or b"{}"), "error": None}
    except urllib.error.HTTPError as exc:
        return {"status": exc.code, "data": None, "error": exc.read().decode("utf-8", errors="ignore")[:300]}
    except Exception as exc:
        return {"status": 0, "data": None, "error": str(exc)[:300]}


_API = "/services/data/v59.0"


def _sf_get_contact(params: dict, credentials: dict, timeout_seconds: int = 30, **_kw: Any) -> dict:
    contact_id = str(params.get("contact_id") or "")
    if not contact_id:
        raise ValueError("crm.sf_get_contact requires 'contact_id'.")
    return _get(f"{_API}/sobjects/Contact/{contact_id}", credentials, timeout_seconds)


def _sf_get_deal(params: dict, credentials: dict, timeout_seconds: int = 30, **_kw: Any) -> dict:
    opp_id = str(params.get("deal_id") or "")
    if not opp_id:
        raise ValueError("crm.sf_get_deal requires 'deal_id'.")
    return _get(f"{_API}/sobjects/Opportunity/{opp_id}", credentials, timeout_seconds)


def _sf_update_deal(params: dict, credentials: dict, timeout_seconds: int = 30, **_kw: Any) -> dict:
    opp_id = str(params.get("deal_id") or "")
    fields = dict(params.get("fields") or {})
    if not opp_id:
        raise ValueError("crm.sf_update_deal requires 'deal_id'.")
    return _patch(f"{_API}/sobjects/Opportunity/{opp_id}", fields, credentials, timeout_seconds)


def _sf_create_task(params: dict, credentials: dict, timeout_seconds: int = 30, **_kw: Any) -> dict:
    subject = str(params.get("subject") or "Task")
    who_id = str(params.get("who_id") or "")
    body: dict[str, Any] = {"Subject": subject}
    if who_id:
        body["WhoId"] = who_id
    return _post_sf(f"{_API}/sobjects/Task/", body, credentials, timeout_seconds)


def _sf_list_deals_by_stage(params: dict, credentials: dict, timeout_seconds: int = 30, **_kw: Any) -> dict:
    stage = urllib.parse.quote(str(params.get("stage") or "Prospecting"))
    soql = urllib.parse.quote(f"SELECT Id,Name,StageName,Amount FROM Opportunity WHERE StageName='{stage}'")
    return _get(f"{_API}/query?q={soql}", credentials, timeout_seconds)


def register(registry: dict) -> None:
    registry["crm.sf_get_contact"] = _sf_get_contact
    registry["crm.sf_get_deal"] = _sf_get_deal
    registry["crm.sf_update_deal"] = _sf_update_deal
    registry["crm.sf_create_task"] = _sf_create_task
    registry["crm.sf_list_deals_by_stage"] = _sf_list_deals_by_stage
