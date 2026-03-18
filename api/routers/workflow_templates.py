"""Curated workflow starter templates.

Responsibility: pure data — no logic. Each template is a complete workflow
definition ready to be loaded into the canvas.
"""
from __future__ import annotations

from typing import Any

WORKFLOW_TEMPLATES: list[dict[str, Any]] = [
    # ── RAG: Ask Your Documents ───────────────────────────────────────────────
    {
        "template_id": "rag-document-qa",
        "name": "Ask Your Documents",
        "description": "Search your uploaded PDFs, docs, and URLs for answers, then write a cited response.",
        "step_count": 3,
        "tags": ["rag", "knowledge", "documents"],
        "definition": {
            "workflow_id": "rag-document-qa",
            "name": "Ask Your Documents",
            "description": "Search uploaded documents and produce a cited answer.",
            "version": "1.0.0",
            "steps": [
                {
                    "step_id": "step_search",
                    "agent_id": "researcher",
                    "step_type": "knowledge_search",
                    "step_config": {"query_key": "query", "top_k": 8, "retrieval_mode": "hybrid"},
                    "input_mapping": {"query": "literal:Enter your question here"},
                    "output_key": "search_results",
                    "description": "Search all uploaded documents for relevant passages.",
                },
                {
                    "step_id": "step_answer",
                    "agent_id": "analyst",
                    "input_mapping": {"context": "search_results", "question": "literal:Enter your question here"},
                    "output_key": "answer",
                    "description": "Read the retrieved passages and write a comprehensive answer with source citations.",
                },
                {
                    "step_id": "step_format",
                    "agent_id": "writer",
                    "input_mapping": {"content": "answer"},
                    "output_key": "final_response",
                    "description": "Format the answer as a clean, readable response with inline citations and source list.",
                },
            ],
            "edges": [
                {"from_step": "step_search", "to_step": "step_answer"},
                {"from_step": "step_answer", "to_step": "step_format"},
            ],
        },
    },
    # ── RAG: Multi-Document Comparison ────────────────────────────────────────
    {
        "template_id": "rag-multi-doc-compare",
        "name": "Compare Documents",
        "description": "Search across multiple documents to find differences, contradictions, or common themes.",
        "step_count": 3,
        "tags": ["rag", "comparison", "analysis"],
        "definition": {
            "workflow_id": "rag-multi-doc-compare",
            "name": "Compare Documents",
            "description": "Search documents and produce a comparison analysis.",
            "version": "1.0.0",
            "steps": [
                {
                    "step_id": "step_search",
                    "agent_id": "researcher",
                    "step_type": "knowledge_search",
                    "step_config": {"query_key": "query", "top_k": 15, "retrieval_mode": "hybrid", "include_metadata": True},
                    "input_mapping": {"query": "literal:Enter the topic to compare across documents"},
                    "output_key": "search_results",
                    "description": "Search all documents for passages related to the comparison topic.",
                },
                {
                    "step_id": "step_analyse",
                    "agent_id": "analyst",
                    "input_mapping": {"passages": "search_results"},
                    "output_key": "comparison",
                    "description": "Group findings by source document. Identify agreements, contradictions, and unique points.",
                },
                {
                    "step_id": "step_report",
                    "agent_id": "writer",
                    "input_mapping": {"content": "comparison"},
                    "output_key": "report",
                    "description": "Produce a side-by-side comparison table with a summary of key differences.",
                },
            ],
            "edges": [
                {"from_step": "step_search", "to_step": "step_analyse"},
                {"from_step": "step_analyse", "to_step": "step_report"},
            ],
        },
    },
    # ── Web Search: Deep Research ─────────────────────────────────────────────
    {
        "template_id": "web-deep-research",
        "name": "Deep Web Research",
        "description": "Search the web from multiple angles, cross-reference findings, and produce a research brief.",
        "step_count": 4,
        "tags": ["web-search", "research", "report"],
        "definition": {
            "workflow_id": "web-deep-research",
            "name": "Deep Web Research",
            "description": "Multi-angle web research with cross-referencing.",
            "version": "1.0.0",
            "steps": [
                {
                    "step_id": "step_search_broad",
                    "agent_id": "researcher",
                    "input_mapping": {"query": "literal:Enter your research topic"},
                    "output_key": "broad_results",
                    "description": "Search the web broadly for the topic. Gather key facts, statistics, and expert opinions.",
                },
                {
                    "step_id": "step_search_news",
                    "agent_id": "researcher",
                    "input_mapping": {"query": "literal:Enter your research topic — recent news"},
                    "output_key": "news_results",
                    "description": "Search for recent news and developments on the topic from the past 30 days.",
                },
                {
                    "step_id": "step_cross_ref",
                    "agent_id": "analyst",
                    "input_mapping": {"broad": "broad_results", "news": "news_results"},
                    "output_key": "verified_findings",
                    "description": "Cross-reference broad research with recent news. Flag contradictions and verify key claims.",
                },
                {
                    "step_id": "step_brief",
                    "agent_id": "writer",
                    "input_mapping": {"content": "verified_findings"},
                    "output_key": "research_brief",
                    "description": "Write a structured research brief with executive summary, key findings, and source links.",
                },
            ],
            "edges": [
                {"from_step": "step_search_broad", "to_step": "step_cross_ref"},
                {"from_step": "step_search_news", "to_step": "step_cross_ref"},
                {"from_step": "step_cross_ref", "to_step": "step_brief"},
            ],
        },
    },
    # ── Web + RAG: Enrich Documents with Web Data ─────────────────────────────
    {
        "template_id": "rag-web-enrich",
        "name": "Enrich Docs with Web Data",
        "description": "Search your documents for a topic, then enrich the findings with live web data.",
        "step_count": 4,
        "tags": ["rag", "web-search", "enrichment"],
        "definition": {
            "workflow_id": "rag-web-enrich",
            "name": "Enrich Docs with Web Data",
            "description": "Combine document knowledge with live web data.",
            "version": "1.0.0",
            "steps": [
                {
                    "step_id": "step_doc_search",
                    "agent_id": "researcher",
                    "step_type": "knowledge_search",
                    "step_config": {"query_key": "query", "top_k": 10, "retrieval_mode": "hybrid"},
                    "input_mapping": {"query": "literal:Enter your topic"},
                    "output_key": "doc_findings",
                    "description": "Search your uploaded documents for existing knowledge on the topic.",
                },
                {
                    "step_id": "step_web_search",
                    "agent_id": "researcher",
                    "input_mapping": {"query": "literal:Enter your topic — latest data"},
                    "output_key": "web_findings",
                    "description": "Search the web for the latest data, stats, and developments on the topic.",
                },
                {
                    "step_id": "step_merge",
                    "agent_id": "analyst",
                    "input_mapping": {"internal": "doc_findings", "external": "web_findings"},
                    "output_key": "enriched",
                    "description": "Merge internal document knowledge with web findings. Highlight what's new or updated.",
                },
                {
                    "step_id": "step_report",
                    "agent_id": "writer",
                    "input_mapping": {"content": "enriched"},
                    "output_key": "report",
                    "description": "Produce a report showing internal knowledge, web updates, and recommended actions.",
                },
            ],
            "edges": [
                {"from_step": "step_doc_search", "to_step": "step_merge"},
                {"from_step": "step_web_search", "to_step": "step_merge"},
                {"from_step": "step_merge", "to_step": "step_report"},
            ],
        },
    },
    # ── Research → Summarise → Email (original) ───────────────────────────────
    {
        "template_id": "research-summarise-email",
        "name": "Research → Summarise → Email",
        "description": "Search the web for a topic, summarise the findings, then draft and send an email report.",
        "step_count": 3,
        "tags": ["research", "email", "report"],
        "definition": {
            "workflow_id": "research-summarise-email",
            "name": "Research → Summarise → Email",
            "description": "Search the web for a topic, summarise the findings, then send an email.",
            "version": "1.0.0",
            "steps": [
                {"step_id": "step_research", "agent_id": "researcher", "input_mapping": {"query": "literal:Enter your research topic here"}, "output_key": "research_result", "description": "Search the web and gather key findings on the topic."},
                {"step_id": "step_summarise", "agent_id": "analyst", "input_mapping": {"content": "research_result"}, "output_key": "summary", "description": "Synthesise the research into a concise executive summary."},
                {"step_id": "step_email", "agent_id": "deliverer", "input_mapping": {"body": "summary", "subject": "literal:Research Summary"}, "output_key": "email_sent", "description": "Draft and send the summary as an email."},
            ],
            "edges": [{"from_step": "step_research", "to_step": "step_summarise"}, {"from_step": "step_summarise", "to_step": "step_email"}],
        },
    },
    # ── Scrape → Analyse → Report (original) ──────────────────────────────────
    {
        "template_id": "scrape-analyse-report",
        "name": "Scrape → Analyse → Report",
        "description": "Browse a URL, extract structured data, analyse it, and produce a markdown report.",
        "step_count": 3,
        "tags": ["scraping", "analysis", "report"],
        "definition": {
            "workflow_id": "scrape-analyse-report",
            "name": "Scrape → Analyse → Report",
            "description": "Browse a URL, extract data, and produce a markdown report.",
            "version": "1.0.0",
            "steps": [
                {"step_id": "step_scrape", "agent_id": "browser", "input_mapping": {"url": "literal:https://example.com"}, "output_key": "raw_content", "description": "Browse the target URL and extract the page content."},
                {"step_id": "step_analyse", "agent_id": "analyst", "input_mapping": {"data": "raw_content"}, "output_key": "analysis", "description": "Identify key patterns, numbers, and insights in the extracted content."},
                {"step_id": "step_report", "agent_id": "writer", "input_mapping": {"content": "analysis"}, "output_key": "report", "description": "Format the analysis as a structured markdown report with sections and tables."},
            ],
            "edges": [{"from_step": "step_scrape", "to_step": "step_analyse"}, {"from_step": "step_analyse", "to_step": "step_report"}],
        },
    },
    # ── Monitor → Alert → Escalate (original) ─────────────────────────────────
    {
        "template_id": "monitor-alert-escalate",
        "name": "Monitor → Alert → Escalate",
        "description": "Check a data source for anomalies, send an alert if found, escalate if critical.",
        "step_count": 3,
        "tags": ["monitoring", "alerting", "conditional"],
        "definition": {
            "workflow_id": "monitor-alert-escalate",
            "name": "Monitor → Alert → Escalate",
            "description": "Check a source, alert on anomaly, escalate if critical.",
            "version": "1.0.0",
            "steps": [
                {"step_id": "step_monitor", "agent_id": "analyst", "input_mapping": {"source": "literal:Describe the data source to monitor"}, "output_key": "monitor_result", "description": "Fetch and evaluate the data source for anomalies or threshold breaches."},
                {"step_id": "step_alert", "agent_id": "deliverer", "input_mapping": {"message": "monitor_result"}, "output_key": "alert_sent", "description": "Send a Slack or email alert with the anomaly details."},
                {"step_id": "step_escalate", "agent_id": "deliverer", "input_mapping": {"message": "monitor_result", "channel": "literal:escalation-team"}, "output_key": "escalation_sent", "description": "Escalate to the on-call team if the severity is critical."},
            ],
            "edges": [{"from_step": "step_monitor", "to_step": "step_alert"}, {"from_step": "step_alert", "to_step": "step_escalate", "condition": "output.alert_sent == 'critical'"}],
        },
    },
    # ── Ingest → Index → Notify (original) ────────────────────────────────────
    {
        "template_id": "ingest-index-notify",
        "name": "Ingest → Index → Notify",
        "description": "Pull a document from a URL, index it into the knowledge base, then notify the team.",
        "step_count": 3,
        "tags": ["ingestion", "knowledge-base", "notification"],
        "definition": {
            "workflow_id": "ingest-index-notify",
            "name": "Ingest → Index → Notify",
            "description": "Fetch a document, index it, notify the team.",
            "version": "1.0.0",
            "steps": [
                {"step_id": "step_fetch", "agent_id": "browser", "input_mapping": {"url": "literal:https://example.com/document.pdf"}, "output_key": "document_content", "description": "Download and extract the raw text content of the document."},
                {"step_id": "step_index", "agent_id": "indexer", "input_mapping": {"content": "document_content"}, "output_key": "index_result", "description": "Chunk, embed, and store the document in the vector knowledge base."},
                {"step_id": "step_notify", "agent_id": "deliverer", "input_mapping": {"message": "index_result"}, "output_key": "notification_sent", "description": "Send a notification confirming the document was indexed successfully."},
            ],
            "edges": [{"from_step": "step_fetch", "to_step": "step_index"}, {"from_step": "step_index", "to_step": "step_notify"}],
        },
    },
    # ── Competitive Intelligence (original) ───────────────────────────────────
    {
        "template_id": "competitive-intel",
        "name": "Competitive Intelligence",
        "description": "Research competitors, extract positioning data, and produce a comparison table.",
        "step_count": 4,
        "tags": ["research", "competitive", "analysis"],
        "definition": {
            "workflow_id": "competitive-intel",
            "name": "Competitive Intelligence",
            "description": "Research competitors and produce a comparison report.",
            "version": "1.0.0",
            "steps": [
                {"step_id": "step_research_a", "agent_id": "researcher", "input_mapping": {"query": "literal:Competitor A pricing and features"}, "output_key": "competitor_a", "description": "Research Competitor A — gather pricing, key features, and market positioning."},
                {"step_id": "step_research_b", "agent_id": "researcher", "input_mapping": {"query": "literal:Competitor B pricing and features"}, "output_key": "competitor_b", "description": "Research Competitor B — gather pricing, key features, and market positioning."},
                {"step_id": "step_compare", "agent_id": "analyst", "input_mapping": {"data_a": "competitor_a", "data_b": "competitor_b"}, "output_key": "comparison", "description": "Compare both competitors across price, features, strengths, and weaknesses."},
                {"step_id": "step_report", "agent_id": "writer", "input_mapping": {"content": "comparison"}, "output_key": "report", "description": "Produce a markdown report with an executive summary and comparison table."},
            ],
            "edges": [{"from_step": "step_research_a", "to_step": "step_compare"}, {"from_step": "step_research_b", "to_step": "step_compare"}, {"from_step": "step_compare", "to_step": "step_report"}],
        },
    },
]
