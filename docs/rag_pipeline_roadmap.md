# RAG Pipeline Roadmap

This document is the source of truth for the Maia RAG pipeline rollout.

Rule:
- We work one phase at a time.
- A phase is marked done only when its success criteria are met.
- Later phases must not redefine the contract of earlier phases.
- Cross-cutting tracks are allowed, but they must not destabilize the current phase contract.

Current focus:
- Phase 1: Upload

Status legend:
- `[ ]` not started
- `[-]` in progress
- `[x]` done

## Phase Overview

1. `Upload`
2. `Classify`
3. `Extract`
4. `Normalize`
5. `Chunk`
6. `Embed`
7. `Index`
8. `Citation Prep`
9. `Retrieve`
10. `Rerank`
11. `Coverage Check`
12. `Answer`
13. `Citations`
14. `Deliver`

## Target System

Maia RAG is being built toward this operating model:
- group-aware retrieval across large Maia collections of files and URLs
- evidence-grounded answers with precise PDF/web citation jumps
- support for technical and multimodal content such as tables, equations, and scanned PDFs
- optional math/calculation flows grounded in extracted document evidence
- end-to-end observability across upload, indexing, retrieval, citation, and delivery

Concrete product requirements:
- users can create groups containing very large collections of PDFs and URLs
- when a user prompts against a group, retrieval must search across the group scope only
- answers must cite evidence that can jump into the source PDF or URL
- users can upload a PDF through the chat composer and ask questions immediately after the file becomes `rag_ready`
- technical PDFs with images, tables, and equations must remain first-class ingestion targets
- math / calculation questions must produce evidence-grounded computed results, not free-form guesses

## Research-Informed Design Decisions (2026-03-30)

The roadmap below is informed by current primary-source docs and papers:
- OpenAI Retrieval / File Search docs:
  - vector-store metadata filtering
  - file citations
  - searchable file stores
- Weaviate docs:
  - hybrid search
  - metadata filters
  - inverted indexes for BM25 / hybrid / filterable properties
- Azure AI Search + Document Intelligence docs:
  - document layout extraction
  - OCR / layout / image-location metadata
  - large PDF limits and structured extraction behavior
- Docling docs:
  - advanced PDF understanding
  - layout, reading order, tables, formulas, figures
  - local model pipeline options
- Nougat paper:
  - scientific-document OCR into markup
  - useful as a specialized fallback for equation-heavy academic PDFs

Research-backed decisions:
1. Group-aware RAG should be built on metadata-filtered hybrid retrieval, not ad hoc post-filtering.
2. Technical PDF support requires structure-preserving extraction before chunking.
3. Citation quality depends on preserving geometry/alignment through extraction and normalization.
4. `rag_ready` must come before exact citation completion.
5. Math/calculation should be a separate evidence-to-calculation stage after retrieval, not a hidden part of answer synthesis.
6. Observability must emit stage events across ingestion, retrieval, citation, and answer gating.

## Prerequisites

These are required environment capabilities, but they are not pipeline phases:
- local or remote LLM configured for answer synthesis
- local or remote embedding model configured for indexing/retrieval
- document store / vector store selected and stable
- multimodal loaders available for OCR / document analysis

Why this is not a phase:
- environment setup does not produce a stable user-facing contract by itself
- it should not block phase tracking once the platform baseline is usable

## Cross-Cutting Tracks

These tracks span multiple phases and should be advanced only when the underlying phase contracts are stable:

### A. Group Management And Permissions
- user-owned file groups / collections
- append / replace file assignment flows
- permission filtering on retrieval and file listing
- group-scoped query restrictions
- scale target: group retrieval remains usable for very large groups via metadata-filtered search, not full collection scans

Primary phase touchpoints:
- `Upload`
- `Index`
- `Retrieve`
- `Deliver`

### B. Evidence Geometry And Citation Precision
- page/unit/character alignment
- highlight boxes and evidence anchors
- fallback page/snippet anchors when exact geometry is unavailable
- web-page paragraph / DOM anchors where URL extraction supports them

Primary phase touchpoints:
- `Extract`
- `Normalize`
- `Citation Prep`
- `Citations`

### C. Math And Evidence-Based Calculation
- formula extraction
- variable extraction from text/tables
- unit handling and conversion
- explicit calculation traces grounded in evidence
- equation-heavy PDF fallback path when standard OCR/extraction loses math fidelity

Primary phase touchpoints:
- `Extract`
- `Chunk`
- `Retrieve`
- `Coverage Check`
- `Answer`

### D. Observability And Debugging
- `trace_id` propagation
- structured stage events
- metrics for extraction, retrieval, citations, and answer gating
- debug view for selected evidence and citation paths

Primary phase touchpoints:
- all phases

Rule:
- these tracks must layer onto the pipeline; they must not redefine earlier done phases

## Phase 1: Upload `[-]`

Goal:
- Accept the file cleanly and persist it without pretending it is already retrievable.

Scope:
- raw file intake
- file persistence
- source record creation
- ingestion job creation/queueing
- upload response contract

Out of scope:
- parsing
- OCR
- chunking
- embeddings
- retrieval readiness
- citation readiness

Success criteria:
- file is persisted exactly once per upload request
- source record is created exactly once
- ingestion job is created or reused deterministically
- upload response is stable and explicit
- upload step does not set `rag_ready=true`
- upload step does not set `citation_ready=true`
- UI can show only upload states for this phase:
  - `uploading`
  - `uploaded`
  - `queued`
  - `failed`

Deliverables:
- one clean upload API contract
- one clean upload state model
- no duplicated upload-path logic

Open issues:
- readiness is still leaking into neighboring steps
- legacy sync upload contract still exists in the backend but is now explicitly deprecated
- upload is still too tightly coupled to immediate downstream ingestion behavior
- old half-ready file states still exist in existing records
- top-level readiness fields are now exposed correctly, but they still belong conceptually to later phases

Definition of done:
- a fresh PDF upload ends in a clean queued/started ingestion handoff
- no fake RAG answer is attempted before later phases complete
- no duplicate upload path remains in active use

Current validation evidence:
- `pnpm --dir frontend/user_interface test`
- `pnpm --dir frontend/user_interface build`
- `.venv311\Scripts\python.exe -m pytest api/tests/test_upload_indexing.py -q`
- live `POST /api/uploads/files/jobs` probe:
  - fresh upload returns queued job
  - duplicate in-flight upload reuses the same job id
  - `GET /api/uploads/files?include_chat_temp=true` exposes canonical top-level `scope`, `rag_ready`, `citation_ready`, `citation_status`

Remaining work to close Phase 1 under the stricter architecture:
1. Ensure Upload itself ends at:
   - raw file persisted
   - source row created
   - ingestion job queued/reused
   and nothing more.
2. Separate upload-only state from later readiness state in the user-facing contract:
   - `uploading`
   - `uploaded`
   - `queued`
   - `failed`
3. Ensure later readiness fields (`rag_ready`, `citation_ready`) are consumed as downstream phase state, not as part of upload success semantics.
4. Verify a fresh PDF upload can be observed end-to-end without relying on any legacy path or mixed contract behavior.

Progress since last update:
- active frontend upload flows now use `/api/uploads/files/jobs`
- the sync backend route `/api/uploads/files` is explicitly deprecated and emits deprecation headers

## Phase 2: Classify `[ ]`

Goal:
- Decide the correct processing route for each source.

Scope:
- file type detection
- parser route selection
- OCR vs native text route
- route metadata
- multimodal route flags:
  - text-first PDF
  - OCR-heavy PDF
  - equation-heavy / scientific PDF
  - HTML / URL
  - Office document
  - image-first document

Success criteria:
- each file is classified once
- classification result is explicit and logged
- route choice is deterministic for the same file content
- classification does not depend on downstream retrieval logic

Definition of done:
- same file content yields same route decision
- heavy scanned PDFs and native-text PDFs separate reliably
- route metadata is available to later phases without recomputation
- route decision is explicit enough to support:
  - standard extraction
  - multimodal layout extraction
  - scientific/equation fallback when necessary

## Phase 3: Extract `[ ]`

Goal:
- Turn the source into usable text and structural data.

Scope:
- text extraction
- OCR when required
- page data
- headings/sections
- extraction debug output
- tables / formulas / figures metadata when extractors support it
- raw aligned text suitable for later geometry mapping
- reading order preservation for technical PDFs
- URL visible-text extraction plus stable paragraph/heading anchors when possible

Success criteria:
- text can be produced or failure is explicit
- extraction failure does not masquerade as empty retrieval
- extracted structure is preserved well enough for downstream chunking and citation prep
- extraction retains enough signal for equations, tables, and figure-linked text where the backend supports it

Definition of done:
- successful extraction creates canonical raw text output for downstream stages

## Phase 4: Normalize `[ ]`

Goal:
- Clean extracted content into a canonical document form.

Scope:
- whitespace cleanup
- duplicated block cleanup
- section/page anchor preservation
- metadata normalization
- preserve both:
  - raw aligned text
  - canonical retrieval text
- avoid destroying formula tokens or table cell adjacency during canonicalization

Success criteria:
- normalized content is deterministic
- page/section anchors survive normalization
- normalization does not destroy later citation alignment data

Definition of done:
- downstream chunking consumes only canonical normalized content

## Phase 5: Chunk `[ ]`

Goal:
- Split normalized content into retrieval units.

Scope:
- chunk strategy selection
- chunk metadata
- page/section linkage
- structure-aware chunking for sections, subsections, tables, formulas, captions
- recursive fallback when document structure is weak
- chunk strategy may differ by route:
  - standard text documents
  - technical/layout-rich PDFs
  - URLs / HTML

Success criteria:
- chunks retain source/file/page identity
- chunking is consistent for the same normalized document
- chunk metadata includes enough structure for group filtering, citation binding, and technical reasoning
- formulas and tables are not arbitrarily split in ways that destroy later calculations

Definition of done:
- chunk objects are stable and ready for embeddings

## Phase 6: Embed `[ ]`

Goal:
- Generate vector representations for chunks.

Scope:
- embedding requests
- embedding persistence
- embedding failure handling
- model/version metadata for traceability

Success criteria:
- all accepted chunks either embed successfully or fail explicitly
- embeddings are attributable to a specific model/config

Definition of done:
- chunk vectors are available for indexing

## Phase 7: Index `[ ]`

Goal:
- Write chunks into retrieval stores and mark the source retrievable.

Scope:
- vector index writes
- metadata index writes
- full-text index writes if applicable
- readiness transition
- group and permission metadata materialized for retrieval filters
- indexing shape supports large-group retrieval by prefiltering on group/file metadata before dense search

Success criteria:
- `rag_ready=true` is set only here
- document relations exist before readiness is exposed
- retrieval scope can be constrained by file id, group id, source type, and owner
- group filtering does not require scanning the full corpus

Definition of done:
- RAG can answer from the file after this phase completes

## Phase 8: Citation Prep `[ ]`

Goal:
- Prepare precise evidence navigation after RAG is already available.

Scope:
- page-unit mapping
- span/highlight targeting
- citation cache build
- citation anchor tiers:
  - page/snippet fallback
  - basic evidence anchors
  - exact geometry-backed highlights
- optional internal milestones:
  - `citation_basic_ready`
  - `citation_exact_ready`

Success criteria:
- `citation_ready=true` is set only here
- RAG remains usable while citation prep is still running
- citation fallback is explicit when exact geometry is unavailable
- citations for URLs have a stable anchor strategy even when exact DOM geometry is unavailable

Definition of done:
- evidence jumps are reliable and explicit

## Phase 9: Retrieve `[ ]`

Goal:
- Find candidate evidence from Maia sources.

Scope:
- selected-source filtering
- hybrid retrieval
- retrieval result shaping
- group scope resolution
- chat-upload single-file scope resolution
- source-type-aware filtering (PDF vs URL vs document)
- metadata-first narrowing for large groups before vector / keyword expansion

Success criteria:
- retrieval only uses Maia-scoped sources in RAG mode
- selected-source scope is respected
- group filtering and permission filtering are enforced before candidate expansion
- large-group retrieval remains bounded by filters and top-k, not corpus-wide fanout

Definition of done:
- retrieval produces a candidate evidence set with clear provenance

## Phase 10: Rerank `[ ]`

Goal:
- Improve evidence quality before answer generation.

Scope:
- relevance reranking
- duplicate suppression
- source-quality weighting
- diversity across files/pages/sections
- technical-source preference where applicable

Success criteria:
- trivial/noisy chunks are demoted
- stronger chunks rise consistently
- reranking does not collapse all support onto one low-quality dominant snippet

Definition of done:
- top evidence set is visibly better than raw retrieval output

## Phase 11: Coverage Check `[ ]`

Goal:
- Decide whether the evidence is enough, partial, conflicting, or missing.

Scope:
- sufficiency checks
- partial coverage checks
- conflict checks
- no-evidence handling
- calculation-readiness checks when the user asks for computed results
- variable completeness checks for formulas and table-derived calculations

Success criteria:
- no fake confident answer when evidence is weak
- no fake conflict from a single source
- unresolved formulas / missing variables are surfaced honestly
- missing numeric inputs prevent fake calculations

Definition of done:
- answer path selection is evidence-driven and predictable

## Phase 12: Answer `[ ]`

Goal:
- Generate a grounded answer from retrieved evidence only.

Scope:
- synthesis
- grounded answer structure
- partial/conflict-aware answer variants
- optional evidence-based calculation path
- answer gating when support is off-topic or too thin
- step-by-step calculation rendering when the user explicitly asks for math or derived values

Success criteria:
- no general-knowledge escape in RAG mode
- answer reflects actual evidence quality
- computed answers show formula, substitution, and result only when evidence supports them
- citations bind both the source claim and each calculation input when applicable

Definition of done:
- answer body is consistent with coverage state

## Phase 13: Citations `[ ]`

Goal:
- Bind claims to evidence references and jump targets.

Scope:
- ref assignment
- evidence cards
- file/page jump payload
- highlight source metadata:
  - exact geometry
  - fallback page/snippet match
- PDF and URL citation payload parity where possible

Success criteria:
- citations open the correct source
- PDF/file evidence focus is stable
- citation payload clearly tells the UI whether a jump is exact or fallback
- URL citations open the right page section or closest stable fallback anchor

Definition of done:
- citations are usable, not decorative

## Phase 14: Deliver `[ ]`

Goal:
- Present the answer and evidence cleanly in the app.

Scope:
- canvas output
- right-panel evidence state
- source scope visibility
- progress and readiness messaging
- evidence panel for groups, files, URLs, and citations
- warnings for low-relevance or low-confidence evidence
- room for interactive tables/charts later without redefining answer contract
- group-scoped answer UX that makes the searched group explicit

Success criteria:
- one answer surface per mode
- upload/RAG state is understandable to the user
- users can tell what scope was searched, what evidence was used, and what remains unresolved

Definition of done:
- user can understand what happened, what is ready, and what remains

## Update Rule

When a phase is finished:
- change its status from `[-]` or `[ ]` to `[x]`
- add the completion date
- add the validating tests or live checks used to declare it done
