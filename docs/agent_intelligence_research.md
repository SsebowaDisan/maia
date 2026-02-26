# Maia Agent Intelligence Upgrade (Research-Backed)

## Goal
Make Maia more reliable, grounded, and visibly intelligent during long-running company-agent tasks, while keeping every phase live-streamed.

## Primary Sources (Papers)
- ReAct: Synergizing Reasoning and Acting in Language Models  
  https://arxiv.org/abs/2210.03629
- Self-Refine: Iterative Refinement with Self-Feedback  
  https://arxiv.org/abs/2303.17651
- Reflexion: Language Agents with Verbal Reinforcement Learning  
  https://arxiv.org/abs/2303.11366
- Chain-of-Verification (CoVe): Reduce Hallucination with Verification Steps  
  https://arxiv.org/abs/2309.11495
- Toolformer: Language Models Can Teach Themselves to Use Tools  
  https://arxiv.org/abs/2302.04761
- Self-RAG: Learning to Retrieve, Generate, and Critique  
  https://arxiv.org/abs/2310.11511
- CRAG: Corrective Retrieval Augmented Generation  
  https://arxiv.org/abs/2401.15884
- Tree of Thoughts: Deliberate Problem Solving with LLMs  
  https://arxiv.org/abs/2305.10601
- HyDE: Hypothetical Document Embeddings  
  https://aclanthology.org/2023.acl-long.99/
- RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval  
  https://arxiv.org/abs/2401.18059

## What Was Implemented In Maia

### 1) Task Intelligence Layer (ReAct + CoVe inspired)
File: `api/services/agent/intelligence.py`
- Added structured task understanding extraction:
  - target URL
  - target host
  - delivery email
  - delivery/report/web intent
- Added verification report generation:
  - plan execution check
  - website evidence check
  - source grounding check
  - report generation check
  - delivery check
  - stability check
- Added remediation hints for common failures:
  - OAuth/auth issues
  - role/permission issues

### 2) Post-Run Verification Events (CoVe style)
File: `api/services/agent/orchestrator.py`
- Added live events:
  - `task_understanding_started`
  - `task_understanding_ready`
  - `verification_started`
  - `verification_check`
  - `verification_completed`
- Added verification summary into final answer for transparency.

### 3) Multi-Query Search + Fusion (CRAG/RAG-fusion style)
File: `api/services/agent/tools/research_tools.py`
- Added query rewriting for web research:
  - prompt query normalization
  - URL-host scoped variants
  - compact fallback variants
- Added reciprocal rank fusion of multi-query search results.
- Added retrieval-quality live events:
  - `retrieval_query_rewrite`
  - `retrieval_fused`
  - `retrieval_quality_assessed`

### 4) Event Catalog Extended
File: `api/services/agent/events.py`
- Registered new event types and stage/status mappings for the above flow.

### 5) Evidence Integrity Engine (Claim Support + Contradiction Scan)
Files:
- `api/services/agent/intelligence.py`
- `api/services/agent/tools/browser_tools.py`
- `api/services/agent/tools/research_tools.py`

What it does:
- Extracts claim candidates from executed tool summaries.
- Scores claim support against captured evidence snippets.
- Detects potential contradiction signals across sources:
  - negation mismatch
  - numeric mismatch on overlapping topic terms
- Streams the checks through the existing live verification timeline.

## Why This Improves “Smartness”
- Better decomposition before action.
- Better retrieval quality (less noisy single-query failures).
- Explicit verification before final delivery.
- Full observability for users through live events.

## Current Limits (Next Work)
- Verification is currently rule-based; add model-based claim checking in next phase.
- Add contradiction detection over retrieved evidence (source-to-source checks).
- Add uncertainty score per major claim in final answer.
- Add adaptive retry policies for failed delivery actions (OAuth refresh, permission checks, replay-safe retry).
