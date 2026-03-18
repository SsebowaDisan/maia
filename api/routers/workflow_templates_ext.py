"""Extended workflow templates — content, data viz, analysis, and analytics.

Responsibility: pure data continuation of workflow_templates.py.
"""
from __future__ import annotations

from typing import Any

WORKFLOW_TEMPLATES_EXT: list[dict[str, Any]] = [
    # ═══════════════════════════════════════════════════════════════════════════
    # CONTENT & WRITING
    # ═══════════════════════════════════════════════════════════════════════════

    # ── Blog Writer ───────────────────────────────────────────────────────────
    {
        "template_id": "content-blog-writer",
        "name": "Blog Post Writer",
        "description": "Research a topic, outline the structure, write a full SEO-optimized blog post, and add a meta description.",
        "step_count": 4,
        "tags": ["content", "writing", "blog", "seo"],
        "definition": {
            "workflow_id": "content-blog-writer",
            "name": "Blog Post Writer",
            "version": "1.0.0",
            "steps": [
                {"step_id": "research", "agent_id": "researcher", "input_mapping": {"query": "literal:Enter your blog topic"}, "output_key": "research", "description": "Search the web for key facts, statistics, expert quotes, and trending angles on this topic."},
                {"step_id": "outline", "agent_id": "analyst", "input_mapping": {"content": "research"}, "output_key": "outline", "description": "Create a structured blog outline with H2/H3 headings, key points per section, and a suggested hook."},
                {"step_id": "write", "agent_id": "writer", "input_mapping": {"outline": "outline", "research": "research"}, "output_key": "draft", "description": "Write the full blog post (1200-1800 words) in a conversational, authoritative tone with inline citations."},
                {"step_id": "seo", "agent_id": "analyst", "input_mapping": {"draft": "draft"}, "output_key": "final_post", "description": "Add SEO meta title (under 60 chars), meta description (under 155 chars), suggest 5 internal link opportunities, and ensure keyword density is natural."},
            ],
            "edges": [
                {"from_step": "research", "to_step": "outline"},
                {"from_step": "outline", "to_step": "write"},
                {"from_step": "write", "to_step": "seo"},
            ],
        },
    },
    # ── Social Media Campaign ─────────────────────────────────────────────────
    {
        "template_id": "content-social-campaign",
        "name": "Social Media Campaign",
        "description": "Generate platform-specific posts for LinkedIn, Twitter/X, and Instagram from a single brief.",
        "step_count": 4,
        "tags": ["content", "social-media", "marketing"],
        "definition": {
            "workflow_id": "content-social-campaign",
            "name": "Social Media Campaign",
            "version": "1.0.0",
            "steps": [
                {"step_id": "brief", "agent_id": "analyst", "input_mapping": {"topic": "literal:Enter your campaign topic or product"}, "output_key": "strategy", "description": "Analyse the topic and define the campaign angle, target audience, tone, and 3 key messages."},
                {"step_id": "linkedin", "agent_id": "writer", "input_mapping": {"strategy": "strategy"}, "output_key": "linkedin_posts", "description": "Write 3 LinkedIn posts: professional tone, 150-300 words each, with a hook opening and CTA. Include relevant hashtags."},
                {"step_id": "twitter", "agent_id": "writer", "input_mapping": {"strategy": "strategy"}, "output_key": "twitter_posts", "description": "Write 5 Twitter/X posts: punchy, under 280 chars each, with hooks and hashtags. Include a thread option (5 connected tweets)."},
                {"step_id": "compile", "agent_id": "writer", "input_mapping": {"linkedin": "linkedin_posts", "twitter": "twitter_posts"}, "output_key": "campaign_pack", "description": "Compile all posts into a ready-to-publish campaign pack with platform labels, posting schedule suggestion, and a brief for the design team."},
            ],
            "edges": [
                {"from_step": "brief", "to_step": "linkedin"},
                {"from_step": "brief", "to_step": "twitter"},
                {"from_step": "linkedin", "to_step": "compile"},
                {"from_step": "twitter", "to_step": "compile"},
            ],
        },
    },
    # ── Email Sequence Writer ─────────────────────────────────────────────────
    {
        "template_id": "content-email-sequence",
        "name": "Email Sequence Writer",
        "description": "Write a 3-email nurture sequence: welcome, value, and conversion — tailored to your product.",
        "step_count": 3,
        "tags": ["content", "email", "marketing", "copywriting"],
        "definition": {
            "workflow_id": "content-email-sequence",
            "name": "Email Sequence Writer",
            "version": "1.0.0",
            "steps": [
                {"step_id": "strategy", "agent_id": "analyst", "input_mapping": {"brief": "literal:Describe your product and target audience"}, "output_key": "email_strategy", "description": "Define the sequence strategy: audience persona, pain points, value proposition, tone, and CTA for each email."},
                {"step_id": "write_emails", "agent_id": "writer", "input_mapping": {"strategy": "email_strategy"}, "output_key": "emails", "description": "Write 3 emails: (1) Welcome — introduce the brand warmly, (2) Value — share a tip or case study, (3) Convert — make the offer with urgency. Each under 300 words with subject lines."},
                {"step_id": "review", "agent_id": "analyst", "input_mapping": {"emails": "emails"}, "output_key": "final_sequence", "description": "Review for tone consistency, subject line A/B variants, spam trigger words, and mobile readability. Output the final polished sequence."},
            ],
            "edges": [
                {"from_step": "strategy", "to_step": "write_emails"},
                {"from_step": "write_emails", "to_step": "review"},
            ],
        },
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # DATA VISUALISATION
    # ═══════════════════════════════════════════════════════════════════════════

    # ── CSV to Charts ─────────────────────────────────────────────────────────
    {
        "template_id": "dataviz-csv-charts",
        "name": "CSV → Charts & Insights",
        "description": "Upload a CSV file, analyse the data, generate chart descriptions, and produce a visual report.",
        "step_count": 3,
        "tags": ["data", "visualisation", "csv", "charts"],
        "definition": {
            "workflow_id": "dataviz-csv-charts",
            "name": "CSV → Charts & Insights",
            "version": "1.0.0",
            "steps": [
                {"step_id": "parse", "agent_id": "analyst", "input_mapping": {"data": "literal:Paste your CSV data or describe the dataset"}, "output_key": "parsed_data", "description": "Parse the CSV data. Identify column types (numeric, categorical, date). Report row count, missing values, and basic statistics (mean, median, min, max) for each numeric column."},
                {"step_id": "analyse", "agent_id": "analyst", "input_mapping": {"data": "parsed_data"}, "output_key": "analysis", "description": "Find the top 5 insights: trends, outliers, correlations, and distributions. For each insight, recommend the best chart type (bar, line, scatter, pie, heatmap) and specify the exact axes and data series."},
                {"step_id": "report", "agent_id": "writer", "input_mapping": {"analysis": "analysis"}, "output_key": "visual_report", "description": "Produce a markdown report with: executive summary, one section per insight (chart specification + narrative explanation), and a data quality appendix. Use markdown tables for the underlying numbers."},
            ],
            "edges": [
                {"from_step": "parse", "to_step": "analyse"},
                {"from_step": "analyse", "to_step": "report"},
            ],
        },
    },
    # ── Dashboard Builder ─────────────────────────────────────────────────────
    {
        "template_id": "dataviz-dashboard-spec",
        "name": "Dashboard Spec Builder",
        "description": "Describe your KPIs and get a complete dashboard specification with chart types, layout, and data sources.",
        "step_count": 3,
        "tags": ["data", "visualisation", "dashboard", "kpi"],
        "definition": {
            "workflow_id": "dataviz-dashboard-spec",
            "name": "Dashboard Spec Builder",
            "version": "1.0.0",
            "steps": [
                {"step_id": "gather", "agent_id": "analyst", "input_mapping": {"brief": "literal:Describe your business KPIs and data sources"}, "output_key": "kpi_inventory", "description": "List each KPI with: definition, data source, update frequency, target value, and comparison period. Group into categories (revenue, engagement, operations, etc.)."},
                {"step_id": "design", "agent_id": "analyst", "input_mapping": {"kpis": "kpi_inventory"}, "output_key": "dashboard_spec", "description": "Design the dashboard layout: which KPIs go in the hero section (big numbers), which get trend charts (line/area), which get comparison charts (bar), and which get tables. Specify filters (date range, segment, region)."},
                {"step_id": "document", "agent_id": "writer", "input_mapping": {"spec": "dashboard_spec"}, "output_key": "dashboard_document", "description": "Produce a complete dashboard specification document with: wireframe description, chart-by-chart specs (type, axes, colours, thresholds), filter behaviour, and implementation notes for the dev team."},
            ],
            "edges": [
                {"from_step": "gather", "to_step": "design"},
                {"from_step": "design", "to_step": "document"},
            ],
        },
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # DATA ANALYSIS
    # ═══════════════════════════════════════════════════════════════════════════

    # ── Survey Analysis ───────────────────────────────────────────────────────
    {
        "template_id": "analysis-survey",
        "name": "Survey Results Analyser",
        "description": "Process survey responses, segment by demographics, identify themes, and produce an insight report.",
        "step_count": 3,
        "tags": ["data", "analysis", "survey", "research"],
        "definition": {
            "workflow_id": "analysis-survey",
            "name": "Survey Results Analyser",
            "version": "1.0.0",
            "steps": [
                {"step_id": "process", "agent_id": "analyst", "input_mapping": {"data": "literal:Paste survey data or describe the survey"}, "output_key": "processed", "description": "Process the raw survey data. For quantitative questions: calculate distributions, averages, and NPS/CSAT scores. For open-ended questions: extract the top 10 themes with frequency counts and representative quotes."},
                {"step_id": "segment", "agent_id": "analyst", "input_mapping": {"data": "processed"}, "output_key": "segments", "description": "Segment responses by available demographics (age, role, region, tenure). For each segment, highlight where their answers differ significantly from the overall average. Flag any statistically notable patterns."},
                {"step_id": "report", "agent_id": "writer", "input_mapping": {"analysis": "segments"}, "output_key": "survey_report", "description": "Write an executive report: overall sentiment summary, top 5 takeaways, segment-level findings, recommended actions, and an appendix with all charts and tables."},
            ],
            "edges": [
                {"from_step": "process", "to_step": "segment"},
                {"from_step": "segment", "to_step": "report"},
            ],
        },
    },
    # ── Financial Document Analysis ───────────────────────────────────────────
    {
        "template_id": "analysis-financial-docs",
        "name": "Financial Document Analyser",
        "description": "Upload financial documents (10-K, balance sheet, P&L) and get KPI extraction, trend analysis, and a summary.",
        "step_count": 4,
        "tags": ["data", "analysis", "finance", "rag"],
        "definition": {
            "workflow_id": "analysis-financial-docs",
            "name": "Financial Document Analyser",
            "version": "1.0.0",
            "steps": [
                {"step_id": "search", "agent_id": "researcher", "step_type": "knowledge_search", "step_config": {"query_key": "query", "top_k": 15, "retrieval_mode": "hybrid"}, "input_mapping": {"query": "literal:Extract revenue, net income, margins, and key financial metrics"}, "output_key": "doc_passages", "description": "Search uploaded financial documents for revenue, expenses, net income, margins, cash flow, and any forward guidance."},
                {"step_id": "extract", "agent_id": "analyst", "input_mapping": {"passages": "doc_passages"}, "output_key": "kpis", "description": "Extract structured KPIs: revenue, gross margin, operating margin, net income, EPS, debt-to-equity, free cash flow. Compare YoY if multiple periods are available."},
                {"step_id": "analyse", "agent_id": "analyst", "input_mapping": {"kpis": "kpis"}, "output_key": "analysis", "description": "Analyse trends, flag risks (declining margins, rising debt, revenue concentration), identify strengths, and compare against industry benchmarks if context is available."},
                {"step_id": "report", "agent_id": "writer", "input_mapping": {"analysis": "analysis", "kpis": "kpis"}, "output_key": "financial_report", "description": "Produce a structured financial analysis report: executive summary, KPI dashboard table, trend analysis, risk flags, and investment considerations."},
            ],
            "edges": [
                {"from_step": "search", "to_step": "extract"},
                {"from_step": "extract", "to_step": "analyse"},
                {"from_step": "analyse", "to_step": "report"},
            ],
        },
    },
    # ── Competitor Pricing Analysis ────────────────────────────────────────────
    {
        "template_id": "analysis-competitor-pricing",
        "name": "Competitor Pricing Analysis",
        "description": "Scrape competitor pricing pages, extract plan tiers, and produce a comparison matrix.",
        "step_count": 4,
        "tags": ["data", "analysis", "competitive", "pricing"],
        "definition": {
            "workflow_id": "analysis-competitor-pricing",
            "name": "Competitor Pricing Analysis",
            "version": "1.0.0",
            "steps": [
                {"step_id": "scrape_a", "agent_id": "researcher", "input_mapping": {"query": "literal:Competitor A pricing page URL"}, "output_key": "pricing_a", "description": "Visit the competitor's pricing page. Extract all plan names, prices, billing periods, feature lists, and any usage limits."},
                {"step_id": "scrape_b", "agent_id": "researcher", "input_mapping": {"query": "literal:Competitor B pricing page URL"}, "output_key": "pricing_b", "description": "Visit the second competitor's pricing page. Extract the same structured pricing data."},
                {"step_id": "compare", "agent_id": "analyst", "input_mapping": {"a": "pricing_a", "b": "pricing_b"}, "output_key": "comparison", "description": "Build a feature-by-feature comparison matrix. Highlight where each competitor is cheaper/more expensive, which features are unique, and calculate price-per-feature value scores."},
                {"step_id": "report", "agent_id": "writer", "input_mapping": {"comparison": "comparison"}, "output_key": "pricing_report", "description": "Produce a pricing intelligence report with: comparison table, positioning map, recommended pricing strategy, and talking points for the sales team."},
            ],
            "edges": [
                {"from_step": "scrape_a", "to_step": "compare"},
                {"from_step": "scrape_b", "to_step": "compare"},
                {"from_step": "compare", "to_step": "report"},
            ],
        },
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # GOOGLE ANALYTICS
    # ═══════════════════════════════════════════════════════════════════════════

    # ── GA4 Weekly Report ─────────────────────────────────────────────────────
    {
        "template_id": "ga4-weekly-report",
        "name": "GA4 Weekly Performance Report",
        "description": "Pull last 7 days of GA4 data, analyse traffic and conversions, and produce a stakeholder-ready report.",
        "step_count": 3,
        "tags": ["google-analytics", "ga4", "report", "weekly"],
        "definition": {
            "workflow_id": "ga4-weekly-report",
            "name": "GA4 Weekly Performance Report",
            "version": "1.0.0",
            "steps": [
                {"step_id": "fetch", "agent_id": "analyst", "input_mapping": {"property_id": "literal:Enter your GA4 property ID"}, "output_key": "ga4_data", "description": "Fetch the last 7 days of GA4 data: sessions, users, pageviews, bounce rate, avg session duration, conversion rate, top 10 pages, top 5 traffic sources, and device breakdown."},
                {"step_id": "analyse", "agent_id": "analyst", "input_mapping": {"data": "ga4_data"}, "output_key": "analysis", "description": "Compare this week vs previous week. Calculate percentage changes for all KPIs. Identify the biggest movers (pages gaining/losing traffic), any anomalies (sudden spikes/drops), and traffic source shifts."},
                {"step_id": "report", "agent_id": "writer", "input_mapping": {"analysis": "analysis"}, "output_key": "weekly_report", "description": "Write a weekly performance report: executive summary (3 bullet points), KPI scoreboard table with WoW changes, top pages table, traffic source breakdown, notable observations, and 3 recommended actions."},
            ],
            "edges": [
                {"from_step": "fetch", "to_step": "analyse"},
                {"from_step": "analyse", "to_step": "report"},
            ],
        },
    },
    # ── GA4 Landing Page Audit ────────────────────────────────────────────────
    {
        "template_id": "ga4-landing-page-audit",
        "name": "GA4 Landing Page Audit",
        "description": "Analyse your top landing pages by bounce rate, conversion, and engagement — with recommendations.",
        "step_count": 3,
        "tags": ["google-analytics", "ga4", "landing-pages", "cro"],
        "definition": {
            "workflow_id": "ga4-landing-page-audit",
            "name": "GA4 Landing Page Audit",
            "version": "1.0.0",
            "steps": [
                {"step_id": "fetch", "agent_id": "analyst", "input_mapping": {"property_id": "literal:Enter your GA4 property ID"}, "output_key": "page_data", "description": "Fetch landing page performance for the last 30 days: page path, sessions, bounce rate, avg engagement time, conversions, and conversion rate. Get the top 20 pages by traffic volume."},
                {"step_id": "audit", "agent_id": "analyst", "input_mapping": {"pages": "page_data"}, "output_key": "audit_results", "description": "Score each landing page: high-traffic + high-bounce = urgent fix, high-traffic + low-conversion = optimisation opportunity, low-traffic + high-conversion = scale candidate. Rank pages by improvement potential."},
                {"step_id": "recommendations", "agent_id": "writer", "input_mapping": {"audit": "audit_results"}, "output_key": "audit_report", "description": "Produce a landing page audit report: priority matrix (fix/optimise/scale), per-page recommendations (headline changes, CTA placement, content gaps), and a 30-day action plan."},
            ],
            "edges": [
                {"from_step": "fetch", "to_step": "audit"},
                {"from_step": "audit", "to_step": "recommendations"},
            ],
        },
    },
    # ── GA4 Traffic Source Deep Dive ───────────────────────────────────────────
    {
        "template_id": "ga4-traffic-source-analysis",
        "name": "GA4 Traffic Source Deep Dive",
        "description": "Break down your traffic by source, medium, and campaign — with ROI analysis and channel recommendations.",
        "step_count": 3,
        "tags": ["google-analytics", "ga4", "traffic", "channels"],
        "definition": {
            "workflow_id": "ga4-traffic-source-analysis",
            "name": "GA4 Traffic Source Deep Dive",
            "version": "1.0.0",
            "steps": [
                {"step_id": "fetch", "agent_id": "analyst", "input_mapping": {"property_id": "literal:Enter your GA4 property ID"}, "output_key": "traffic_data", "description": "Fetch 30-day traffic data grouped by source/medium: sessions, users, new users, bounce rate, pages per session, avg engagement time, conversions, and revenue (if available). Also fetch campaign-level data."},
                {"step_id": "analyse", "agent_id": "analyst", "input_mapping": {"data": "traffic_data"}, "output_key": "channel_analysis", "description": "For each channel: calculate cost-efficiency (if spend data available), conversion rate, user quality score (engagement × conversion). Identify over-invested channels (high spend, low conversion) and under-invested ones (low spend, high conversion). Compare organic vs paid split."},
                {"step_id": "report", "agent_id": "writer", "input_mapping": {"analysis": "channel_analysis"}, "output_key": "traffic_report", "description": "Produce a traffic source report: channel performance scoreboard, top 5 campaigns by ROI, channel mix recommendation (where to increase/decrease spend), and a quarterly channel strategy outline."},
            ],
            "edges": [
                {"from_step": "fetch", "to_step": "analyse"},
                {"from_step": "analyse", "to_step": "report"},
            ],
        },
    },
]
