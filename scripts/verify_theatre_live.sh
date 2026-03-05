#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(
  cd -- "$(dirname "$0")"/.. >/dev/null 2>&1
  pwd -P
)"

API_BASE="${MAIA_VERIFY_API_BASE:-http://127.0.0.1:8000}"
USER_ID="${MAIA_VERIFY_USER_ID:-default}"
WEBSITE_URL="${MAIA_VERIFY_WEBSITE_URL:-https://en.wikipedia.org/wiki/Artificial_intelligence}"
PDF_PATH="${MAIA_VERIFY_PDF_PATH:-$ROOT_DIR/libs/maia/tests/resources/multimodal.pdf}"
KEEP_ARTIFACTS="${MAIA_VERIFY_KEEP_ARTIFACTS:-false}"

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/maia-theatre-verify.XXXXXX")"
cleanup() {
  if [[ "$KEEP_ARTIFACTS" == "true" ]]; then
    echo "Keeping artifacts at: $TMP_DIR"
    return
  fi
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

die() {
  echo "[FAIL] $*" >&2
  exit 1
}

print_step() {
  echo
  echo "==> $*"
}

assert_api_up() {
  local health_file="$TMP_DIR/health.json"
  if ! curl -fsS "$API_BASE/api/health" >"$health_file"; then
    die "API is not reachable at $API_BASE. Start backend first."
  fi
}

json_field() {
  local input_file="$1"
  local python_expr="$2"
  python3 - "$input_file" "$python_expr" <<'PY'
import json
import sys

path = sys.argv[1]
expr = sys.argv[2]
with open(path, "r", encoding="utf-8") as fh:
    data = json.load(fh)

value = eval(expr, {"__builtins__": {}}, {"data": data})
if value is None:
    print("")
elif isinstance(value, (dict, list)):
    print(json.dumps(value))
else:
    print(str(value))
PY
}

run_stream() {
  local payload_file="$1"
  local out_file="$2"
  curl -fsS -N "$API_BASE/api/chat/stream" \
    -H "Content-Type: application/json" \
    -H "X-User-Id: $USER_ID" \
    --data-binary "@$payload_file" >"$out_file"
}

summarize_sse() {
  local sse_file="$1"
  local summary_file="$2"
  local event_csv="$3"
  python3 - "$sse_file" "$summary_file" "$event_csv" <<'PY'
import json
import sys
from pathlib import Path

sse_path = Path(sys.argv[1])
summary_path = Path(sys.argv[2])
event_types = [item.strip() for item in str(sys.argv[3]).split(",") if item.strip()]

text = sse_path.read_text(encoding="utf-8", errors="ignore")
events = []
for block in text.split("\n\n"):
    block = block.strip()
    if not block:
        continue
    event_name = ""
    data_lines = []
    for line in block.splitlines():
        if line.startswith("event: "):
            event_name = line[7:].strip()
        elif line.startswith("data: "):
            data_lines.append(line[6:])
    if not data_lines:
        continue
    try:
        payload = json.loads("\n".join(data_lines))
    except Exception:
        continue
    if event_name == "activity" or payload.get("type") == "activity":
        event = payload.get("event")
        if isinstance(event, dict):
            events.append(event)

run_id = ""
for row in events:
    candidate = str(row.get("run_id") or "").strip()
    if candidate:
        run_id = candidate
        break

counts = {
    event_type: sum(1 for row in events if row.get("event_type") == event_type)
    for event_type in event_types
}
summary = {
    "run_id": run_id,
    "total_activity_events": len(events),
    "counts": counts,
}
summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
PY
}

validate_run_events() {
  local mode="$1"
  local events_file="$2"
  local out_file="$3"
  python3 - "$mode" "$events_file" "$out_file" <<'PY'
import json
import sys
from pathlib import Path

mode = sys.argv[1]
events_path = Path(sys.argv[2])
out_path = Path(sys.argv[3])
rows = json.loads(events_path.read_text(encoding="utf-8"))
events = [row.get("payload", {}) for row in rows if row.get("type") == "event"]

def _data(event):
    data = event.get("data")
    if isinstance(data, dict):
        return data
    meta = event.get("metadata")
    if isinstance(meta, dict):
        return meta
    return {}

result = {"ok": False, "checks": {}}

if mode == "website":
    has_scroll = False
    has_navigate = False
    for event in events:
        if event.get("event_type") == "browser_scroll":
            data = _data(event)
            if (
                str(data.get("scene_surface") or "") == "website"
                and isinstance(data.get("scroll_percent"), (int, float))
                and str(data.get("scroll_direction") or "") in {"up", "down"}
            ):
                has_scroll = True
        if event.get("event_type") == "browser_navigate":
            data = _data(event)
            url = str(data.get("url") or "")
            if str(data.get("scene_surface") or "") == "website" and url.startswith(("http://", "https://")):
                has_navigate = True
    result["checks"] = {
        "has_browser_scroll_with_surface_and_metrics": has_scroll,
        "has_browser_navigate_with_surface_and_url": has_navigate,
    }
    result["ok"] = all(result["checks"].values())
elif mode == "pdf":
    has_page_change = False
    has_scan = False
    for event in events:
        if event.get("event_type") == "pdf_page_change":
            data = _data(event)
            if (
                str(data.get("scene_surface") or "") == "document"
                and isinstance(data.get("pdf_page"), (int, float))
                and isinstance(data.get("page_total"), (int, float))
            ):
                has_page_change = True
        if event.get("event_type") == "pdf_scan_region":
            data = _data(event)
            scan_region = str(data.get("scan_region") or "").strip()
            if (
                str(data.get("scene_surface") or "") == "document"
                and isinstance(data.get("scroll_percent"), (int, float))
                and bool(scan_region)
            ):
                has_scan = True
    result["checks"] = {
        "has_pdf_page_change_with_surface_and_page_fields": has_page_change,
        "has_pdf_scan_region_with_surface_and_scan_text": has_scan,
    }
    result["ok"] = all(result["checks"].values())
else:
    result["checks"] = {"unsupported_mode": False}
    result["ok"] = False

out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
PY
}

check_stream_thresholds() {
  local mode="$1"
  local summary_file="$2"
  python3 - "$mode" "$summary_file" <<'PY'
import json
import sys

mode = sys.argv[1]
summary = json.load(open(sys.argv[2], "r", encoding="utf-8"))
counts = summary.get("counts", {})

if mode == "website":
    ok = (
        counts.get("browser_open", 0) >= 1
        and counts.get("browser_navigate", 0) >= 1
        and counts.get("browser_scroll", 0) >= 1
        and counts.get("browser_extract", 0) >= 1
    )
elif mode == "pdf":
    ok = (
        counts.get("pdf_open", 0) >= 1
        and counts.get("pdf_page_change", 0) >= 1
        and counts.get("pdf_scan_region", 0) >= 1
        and counts.get("highlights_detected", 0) >= 1
    )
else:
    ok = False

print("1" if ok else "0")
PY
}

print_step "Checking API health"
assert_api_up
echo "[PASS] API reachable at $API_BASE"

[[ -f "$PDF_PATH" ]] || die "PDF fixture not found: $PDF_PATH"

print_step "Creating conversation"
conversation_json="$TMP_DIR/conversation.json"
curl -fsS -X POST "$API_BASE/api/conversations" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: $USER_ID" \
  -d '{"name":"Theatre live verification"}' >"$conversation_json"
CONVERSATION_ID="$(json_field "$conversation_json" "data.get('id')")"
[[ -n "$CONVERSATION_ID" ]] || die "Failed to create conversation."
echo "[PASS] Conversation created: $CONVERSATION_ID"

print_step "Uploading PDF fixture"
upload_json="$TMP_DIR/upload.json"
curl -fsS -X POST "$API_BASE/api/uploads/files" \
  -H "X-User-Id: $USER_ID" \
  -F "files=@$PDF_PATH;type=application/pdf" \
  -F "reindex=true" >"$upload_json"
PDF_FILE_ID="$(json_field "$upload_json" "((data.get('file_ids') or [''])[0])")"
if [[ -z "$PDF_FILE_ID" ]]; then
  upload_errors="$(json_field "$upload_json" "data.get('errors')")"
  die "PDF upload/index failed: $upload_errors"
fi
echo "[PASS] PDF indexed with file_id: $PDF_FILE_ID"

print_step "Running website stream scenario"
website_payload="$TMP_DIR/website_payload.json"
python3 - "$website_payload" "$CONVERSATION_ID" "$WEBSITE_URL" <<'PY'
import json
import sys
from pathlib import Path

payload_path = Path(sys.argv[1])
conversation_id = sys.argv[2]
url = sys.argv[3]
payload = {
    "message": (
        f"Inspect {url} in a live browser. Scroll through the page, navigate across same-domain links, "
        "and extract evidence before summarizing."
    ),
    "conversation_id": conversation_id,
    "agent_mode": "company_agent",
    "access_mode": "full_access",
}
payload_path.write_text(json.dumps(payload), encoding="utf-8")
PY
website_sse="$TMP_DIR/website.sse"
run_stream "$website_payload" "$website_sse"
website_summary="$TMP_DIR/website_summary.json"
summarize_sse "$website_sse" "$website_summary" "browser_open,browser_navigate,browser_scroll,browser_extract"
WEBSITE_RUN_ID="$(json_field "$website_summary" "data.get('run_id')")"
[[ -n "$WEBSITE_RUN_ID" ]] || die "Website scenario did not produce a run_id."
website_stream_ok="$(check_stream_thresholds "website" "$website_summary")"
if [[ "$website_stream_ok" != "1" ]]; then
  die "Website stream event thresholds failed: $(cat "$website_summary")"
fi
echo "[PASS] Website stream thresholds satisfied: $WEBSITE_RUN_ID"

website_events="$TMP_DIR/website_events.json"
curl -fsS "$API_BASE/api/agent/runs/$WEBSITE_RUN_ID/events" \
  -H "X-User-Id: $USER_ID" >"$website_events"
website_validation="$TMP_DIR/website_validation.json"
validate_run_events "website" "$website_events" "$website_validation"
website_persist_ok="$(json_field "$website_validation" "data.get('ok')")"
if [[ "$website_persist_ok" != "True" ]]; then
  die "Website persisted telemetry validation failed: $(cat "$website_validation")"
fi
echo "[PASS] Website persisted telemetry validation passed"

print_step "Running PDF stream scenario"
pdf_payload="$TMP_DIR/pdf_payload.json"
python3 - "$pdf_payload" "$CONVERSATION_ID" "$PDF_FILE_ID" <<'PY'
import json
import sys
from pathlib import Path

payload_path = Path(sys.argv[1])
conversation_id = sys.argv[2]
file_id = sys.argv[3]
payload = {
    "message": (
        "Read the attached PDF, scan pages, highlight machine-learning related terms, and summarize findings."
    ),
    "conversation_id": conversation_id,
    "agent_mode": "company_agent",
    "access_mode": "full_access",
    "attachments": [{"name": "verification.pdf", "file_id": file_id}],
    "index_selection": {
        "1": {
            "mode": "select",
            "file_ids": [file_id],
        }
    },
}
payload_path.write_text(json.dumps(payload), encoding="utf-8")
PY
pdf_sse="$TMP_DIR/pdf.sse"
run_stream "$pdf_payload" "$pdf_sse"
pdf_summary="$TMP_DIR/pdf_summary.json"
summarize_sse "$pdf_sse" "$pdf_summary" "pdf_open,pdf_page_change,pdf_scan_region,highlights_detected,pdf_evidence_linked"
PDF_RUN_ID="$(json_field "$pdf_summary" "data.get('run_id')")"
[[ -n "$PDF_RUN_ID" ]] || die "PDF scenario did not produce a run_id."
pdf_stream_ok="$(check_stream_thresholds "pdf" "$pdf_summary")"
if [[ "$pdf_stream_ok" != "1" ]]; then
  die "PDF stream event thresholds failed: $(cat "$pdf_summary")"
fi
echo "[PASS] PDF stream thresholds satisfied: $PDF_RUN_ID"

pdf_events="$TMP_DIR/pdf_events.json"
curl -fsS "$API_BASE/api/agent/runs/$PDF_RUN_ID/events" \
  -H "X-User-Id: $USER_ID" >"$pdf_events"
pdf_validation="$TMP_DIR/pdf_validation.json"
validate_run_events "pdf" "$pdf_events" "$pdf_validation"
pdf_persist_ok="$(json_field "$pdf_validation" "data.get('ok')")"
if [[ "$pdf_persist_ok" != "True" ]]; then
  die "PDF persisted telemetry validation failed: $(cat "$pdf_validation")"
fi
echo "[PASS] PDF persisted telemetry validation passed"

print_step "Verification summary"
echo "Website run_id: $WEBSITE_RUN_ID"
echo "Website counts: $(json_field "$website_summary" "data.get('counts')")"
echo "PDF run_id: $PDF_RUN_ID"
echo "PDF counts: $(json_field "$pdf_summary" "data.get('counts')")"
echo
echo "[PASS] Theatre live verification completed successfully."
