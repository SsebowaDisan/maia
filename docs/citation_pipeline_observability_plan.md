# Citation Pipeline Observability Plan

## Goal
Make the current upload -> index -> retrieval -> citation -> highlight -> delivery pipeline fully observable before replacing any subsystem.

This plan is intentionally for the existing Maia pipeline, not a `v2` rewrite.

Success means any bad answer or bad citation can be traced through one `trace_id` from:
- uploaded bytes
- indexed page units
- retrieved chunks
- selected refs
- answer gate decision
- highlight resolution
- final response payload

## Principles
- Do not rewrite first. Instrument first.
- Every turn gets one `trace_id`.
- Every layer emits structured events, not only text logs.
- Every final answer carries the gate result that allowed it to ship.
- Highlight clicks must explain whether they used stored geometry or fallback resolution.

## Core Data Contracts

### IndexedChunk
- `file_id`
- `page`
- `text`
- `unit_id`
- `bbox[]`
- `char_range`
- `source_hash`

### CitationRef
- `ref_id`
- `file_id`
- `page`
- `quoted_text`
- `unit_ids[]`
- `highlight_boxes[]`
- `strength`

### AnswerGate
- no answer paragraph without supporting refs
- no single-ref dominance above threshold
- no answer if evidence is off-topic
- no highlight click without resolvable geometry

## End-to-End Flow

### 1. Upload
Entry point:
- [uploads.py](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\api\routers\uploads.py)
- [uploads_support.py](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\api\routers\uploads_support.py)
- [indexing.py](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\api\services\upload\indexing.py)

Must record:
- `trace_id`
- `upload_id`
- original filename
- stored path
- mime type
- size
- `source_hash`
- scope
- user id
- dedupe decision

Events:
- `upload.received`
- `upload.persisted`
- `upload.reused_existing`
- `upload.rejected`
- `upload.completed`

### 2. Index
Core files:
- [indexing.py](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\api\services\upload\indexing.py)
- [indexing_paddle_helpers.py](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\api\services\upload\indexing_paddle_helpers.py)
- [index_pipeline.py](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\libs\ktem\ktem\index\file\file_pipelines\index_pipeline.py)
- [txt_loader.py](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\libs\maia\maia\loaders\txt_loader.py)

Must record:
- parser route
- OCR route
- page count
- chunk count
- per-page unit count
- geometry count
- char range count
- indexing duration
- status

Events:
- `index.started`
- `index.route_selected`
- `index.page_extracted`
- `index.chunk_created`
- `index.persisted`
- `index.failed`
- `index.completed`

### 3. Retrieval
Core files:
- [fast_qa_retrieval.py](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\api\services\chat\fast_qa_retrieval.py)
- [fast_qa_retrieval_helpers.py](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\api\services\chat\fast_qa_retrieval_helpers.py)
- [retrieval.py](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\api\services\chat\fast_qa_turn_sections\retrieval.py)
- [fast_qa_reasoning_helpers.py](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\api\services\chat\fast_qa_reasoning_helpers.py)

Must record:
- original query
- rewritten query
- selected file scope
- candidate chunk ids
- candidate pages
- selected chunk ids
- lexical support score
- evidence sufficiency result

Events:
- `retrieval.started`
- `retrieval.query_rewritten`
- `retrieval.candidates_loaded`
- `retrieval.selected`
- `retrieval.filtered`
- `retrieval.sufficiency_checked`
- `retrieval.completed`

### 4. Citation
Core files:
- [refs.py](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\api\services\chat\citation_sections\refs.py)
- [context.py](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\api\services\chat\citation_sections\context.py)
- [injection.py](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\api\services\chat\citation_sections\injection.py)
- [public_ops.py](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\api\services\chat\citation_sections\public_ops.py)
- [shared.py](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\api\services\chat\citation_sections\shared.py)
- [resolution.py](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\api\services\chat\citation_sections\resolution.py)

Must record:
- paragraph id
- claim text
- assigned `CitationRef[]`
- unmatched claims
- coverage ratio
- dominance ratio

Events:
- `citation.started`
- `citation.ref_built`
- `citation.claim_matched`
- `citation.claim_unmatched`
- `citation.coverage_failed`
- `citation.completed`

### 5. Answer
Core files:
- [answering.py](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\api\services\chat\fast_qa_turn_sections\answering.py)
- [delivery.py](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\api\services\chat\fast_qa_turn_sections\delivery.py)
- [fast_qa_generation_helpers.py](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\api\services\chat\fast_qa_generation_helpers.py)

Must record:
- paragraph count
- supported paragraph count
- unsupported paragraph count
- off-topic score
- single-ref dominance ratio
- model failure status
- final allow/deny/fallback decision

Events:
- `answer.started`
- `answer.paragraph_checked`
- `answer.gate_failed`
- `answer.fallback_used`
- `answer.completed`

### 6. Highlight
Core files:
- [pdf_highlight_locator.py](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\api\services\upload\pdf_highlight_locator.py)
- [uploads.py](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\api\routers\uploads.py)
- [CitationPdfPreview.tsx](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\frontend\user_interface\src\app\components\CitationPdfPreview.tsx)
- [citationFocus.ts](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\frontend\user_interface\src\app\components\chatMain\citationFocus.ts)
- [uploads.ts](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\frontend\user_interface\src\api\client\uploads.ts)

Must record:
- `ref_id`
- file/page
- stored geometry presence
- fallback route used
- resolution duration
- success/failure reason

Events:
- `highlight.requested`
- `highlight.from_stored_geometry`
- `highlight.from_page_units`
- `highlight.from_ocr_fallback`
- `highlight.failed`
- `highlight.completed`

### 7. Delivery
Core files:
- [delivery.py](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\api\services\chat\fast_qa_turn_sections\delivery.py)
- [chat.py](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\api\routers\chat.py)
- [chat.ts](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\frontend\user_interface\src\api\client\chat.ts)

Must record:
- response id
- conversation id
- final refs
- answer gate result
- response mode
- canvas document id
- timing breakdown

Events:
- `delivery.started`
- `delivery.canvas_created`
- `delivery.response_sent`
- `delivery.completed`

## Proposed Trace Payload
Use one JSON payload per turn keyed by `trace_id`.

See:
- [citation_trace.schema.json](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\docs\extra\citation_trace.schema.json)

High-level shape:

```json
{
  "trace_id": "uuid",
  "user_id": "string",
  "conversation_id": "string",
  "question": "string",
  "upload": {},
  "index": {},
  "retrieval": {},
  "citation": {},
  "answer_gate": {},
  "highlight": {},
  "delivery": {}
}
```

## Implementation Plan

### Phase 1: Trace plumbing
Add:
- `trace_id` generator and propagation
- debug event collector
- request-scoped trace store

Suggested files:
- new `api/services/chat/citation_trace.py`
- new `api/services/upload/citation_trace.py`
- use from [uploads.py](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\api\routers\uploads.py)
- use from [chat.py](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\api\routers\chat.py)

### Phase 2: Upload + index instrumentation
Implement event emission in:
- [uploads.py](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\api\routers\uploads.py)
- [uploads_support.py](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\api\routers\uploads_support.py)
- [indexing.py](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\api\services\upload\indexing.py)
- [indexing_paddle_helpers.py](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\api\services\upload\indexing_paddle_helpers.py)
- [index_pipeline.py](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\libs\ktem\ktem\index\file\file_pipelines\index_pipeline.py)
- [txt_loader.py](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\libs\maia\maia\loaders\txt_loader.py)

### Phase 3: Retrieval instrumentation
Implement in:
- [fast_qa_retrieval.py](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\api\services\chat\fast_qa_retrieval.py)
- [fast_qa_retrieval_helpers.py](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\api\services\chat\fast_qa_retrieval_helpers.py)
- [retrieval.py](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\api\services\chat\fast_qa_turn_sections\retrieval.py)
- [fast_qa_reasoning_helpers.py](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\api\services\chat\fast_qa_reasoning_helpers.py)

### Phase 4: Citation + answer gate
Implement:
- paragraph ids
- claim/ref map
- dominance computation
- off-topic denial

Files:
- [refs.py](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\api\services\chat\citation_sections\refs.py)
- [injection.py](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\api\services\chat\citation_sections\injection.py)
- [public_ops.py](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\api\services\chat\citation_sections\public_ops.py)
- [answering.py](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\api\services\chat\fast_qa_turn_sections\answering.py)

### Phase 5: Highlight instrumentation
Implement:
- highlight resolution source
- timing
- geometry presence

Files:
- [pdf_highlight_locator.py](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\api\services\upload\pdf_highlight_locator.py)
- [uploads.py](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\api\routers\uploads.py)
- [citationFocus.ts](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\frontend\user_interface\src\app\components\chatMain\citationFocus.ts)
- [CitationPdfPreview.tsx](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\frontend\user_interface\src\app\components\CitationPdfPreview.tsx)

### Phase 6: UI debug view
Expose:
- selected chunks
- selected pages
- built refs
- answer gate result
- highlight source and timing

Suggested files:
- new `frontend/user_interface/src/app/components/infoPanel/CitationTracePanel.tsx`
- wire from [chat.ts](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\frontend\user_interface\src\api\client\chat.ts)
- surface in [app.tsx](C:\Users\SBW\OneDrive%20-%20Axon%20Group\Documents\GitHub\maia\frontend\user_interface\src\app\components\chatMain\app.tsx)

## Minimum Questions the Trace Must Answer
For any bad answer or click failure:

1. What exact file was uploaded?
2. Was the file reused or freshly indexed?
3. How many pages were extracted?
4. How many chunks were created?
5. Which chunks were retrieved?
6. Why were they retrieved?
7. Which refs were built?
8. Which paragraphs failed the answer gate?
9. Did the clicked ref have stored geometry?
10. If not, what fallback was used and how long did it take?

## Acceptance Criteria
- Any PDF turn can be traced with one `trace_id`
- Off-topic answers emit `answer_origin=evidence_limited_grounded_fallback`
- No answer paragraph ships without support status recorded
- No citation click occurs without highlight resolution metadata
- Debug payload is available in logs and in the info panel

