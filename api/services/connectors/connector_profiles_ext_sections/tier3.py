from __future__ import annotations

from api.schemas.connector_definition import (
    ApiKeyAuthConfig,
    BearerAuthConfig,
    ConnectorCategory,
    NoAuthConfig,
    OAuth2AuthConfig,
    ToolActionClass,
    ToolParameter,
    ToolParameterType,
    ToolSchema,
)

PROFILES_EXT_TIER3: dict[str, dict] = {
    # ══════════════════════════════════════════════════════════════════════════
    # TIER 3 — Industry-specific, high value
    # ══════════════════════════════════════════════════════════════════════════
    "quickbooks": {
        "name": "QuickBooks",
        "description": "Accounting — invoices, expenses, customers, and reports via QuickBooks Online API.",
        "category": ConnectorCategory.accounting,
        "auth": OAuth2AuthConfig(
            authorization_url="https://appcenter.intuit.com/connect/oauth2",
            token_url="https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer",
            scopes=["com.intuit.quickbooks.accounting"],
        ),
        "tags": ["quickbooks", "accounting", "invoices", "finance"],
        "tools": [
            ToolSchema(id="quickbooks.list_invoices", name="List invoices", description="List recent invoices with amount and status.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="status", type=ToolParameterType.string, description="Filter: paid, unpaid, overdue", required=False),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=20),
            ]),
            ToolSchema(id="quickbooks.create_invoice", name="Create invoice", description="Create a new invoice for a customer.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="customer_id", type=ToolParameterType.string, description="Customer ID"),
                ToolParameter(name="line_items", type=ToolParameterType.array, description="Line items with description, quantity, rate"),
                ToolParameter(name="due_date", type=ToolParameterType.string, description="Due date YYYY-MM-DD", required=False),
            ]),
            ToolSchema(id="quickbooks.get_profit_loss", name="Profit & Loss", description="Get a profit and loss report for a date range.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="start_date", type=ToolParameterType.string, description="Start date YYYY-MM-DD"),
                ToolParameter(name="end_date", type=ToolParameterType.string, description="End date YYYY-MM-DD"),
            ]),
            ToolSchema(id="quickbooks.list_customers", name="List customers", description="List customers with balance info.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=50)]),
        ],
    },
    "xero": {
        "name": "Xero",
        "description": "Cloud accounting — invoices, bank transactions, contacts, and reports via Xero API.",
        "category": ConnectorCategory.accounting,
        "auth": OAuth2AuthConfig(
            authorization_url="https://login.xero.com/identity/connect/authorize",
            token_url="https://identity.xero.com/connect/token",
            scopes=["openid", "accounting.transactions", "accounting.contacts"],
        ),
        "tags": ["xero", "accounting", "invoices", "finance"],
        "tools": [
            ToolSchema(id="xero.list_invoices", name="List invoices", description="List invoices with status and amounts.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="status", type=ToolParameterType.string, description="Filter: DRAFT, SUBMITTED, AUTHORISED, PAID", required=False),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=20),
            ]),
            ToolSchema(id="xero.create_invoice", name="Create invoice", description="Create a new sales invoice.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="contact_id", type=ToolParameterType.string, description="Contact ID"),
                ToolParameter(name="line_items", type=ToolParameterType.array, description="Line items with description, quantity, unit_amount"),
                ToolParameter(name="due_date", type=ToolParameterType.string, description="Due date YYYY-MM-DD", required=False),
            ]),
            ToolSchema(id="xero.get_profit_loss", name="Profit & Loss", description="Get a profit and loss report.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="from_date", type=ToolParameterType.string, description="Start date YYYY-MM-DD"),
                ToolParameter(name="to_date", type=ToolParameterType.string, description="End date YYYY-MM-DD"),
            ]),
            ToolSchema(id="xero.list_contacts", name="List contacts", description="List contacts (customers and suppliers).", action_class=ToolActionClass.read, parameters=[ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=50)]),
        ],
    },
    "zapier_webhooks": {
        "name": "Zapier Webhooks",
        "description": "Trigger Zapier workflows via webhooks — bridge Maia agents to 6,000+ apps.",
        "category": ConnectorCategory.other,
        "auth": NoAuthConfig(),
        "tags": ["zapier", "webhooks", "automation", "integration"],
        "tools": [
            ToolSchema(id="zapier.trigger_webhook", name="Trigger webhook", description="Send a POST request to a Zapier webhook URL to trigger a Zap.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="webhook_url", type=ToolParameterType.string, description="Zapier webhook URL"),
                ToolParameter(name="data", type=ToolParameterType.object, description="JSON payload to send"),
            ]),
        ],
    },
    "make": {
        "name": "Make (Integromat)",
        "description": "Trigger Make scenarios via webhooks and retrieve scenario run status.",
        "category": ConnectorCategory.other,
        "auth": ApiKeyAuthConfig(param_name="Authorization", credential_label="Make API Token"),
        "tags": ["make", "integromat", "automation", "integration"],
        "tools": [
            ToolSchema(id="make.trigger_scenario", name="Trigger scenario", description="Trigger a Make scenario via its webhook URL.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="webhook_url", type=ToolParameterType.string, description="Make webhook URL"),
                ToolParameter(name="data", type=ToolParameterType.object, description="JSON payload"),
            ]),
            ToolSchema(id="make.list_scenarios", name="List scenarios", description="List available Make scenarios.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=20)]),
        ],
    },
    "aws": {
        "name": "AWS",
        "description": "Amazon Web Services — S3 file management, Lambda invocations, and CloudWatch metrics.",
        "category": ConnectorCategory.cloud,
        "auth": ApiKeyAuthConfig(param_name="Authorization", credential_label="AWS Access Key + Secret Key"),
        "tags": ["aws", "cloud", "s3", "lambda", "infrastructure"],
        "tools": [
            ToolSchema(id="aws.s3_list", name="List S3 objects", description="List objects in an S3 bucket with optional prefix.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="bucket", type=ToolParameterType.string, description="S3 bucket name"),
                ToolParameter(name="prefix", type=ToolParameterType.string, description="Object prefix filter", required=False),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max objects", required=False, default=50),
            ]),
            ToolSchema(id="aws.s3_get", name="Get S3 object", description="Download/read an object from S3.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="bucket", type=ToolParameterType.string, description="Bucket name"),
                ToolParameter(name="key", type=ToolParameterType.string, description="Object key"),
            ]),
            ToolSchema(id="aws.s3_put", name="Put S3 object", description="Upload content to S3.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="bucket", type=ToolParameterType.string, description="Bucket name"),
                ToolParameter(name="key", type=ToolParameterType.string, description="Object key"),
                ToolParameter(name="content", type=ToolParameterType.string, description="Content to upload"),
            ]),
            ToolSchema(id="aws.lambda_invoke", name="Invoke Lambda", description="Invoke an AWS Lambda function.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="function_name", type=ToolParameterType.string, description="Lambda function name or ARN"),
                ToolParameter(name="payload", type=ToolParameterType.object, description="JSON payload", required=False),
            ]),
            ToolSchema(id="aws.cloudwatch_query", name="CloudWatch query", description="Query CloudWatch metrics for a service.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="namespace", type=ToolParameterType.string, description="CloudWatch namespace (e.g. AWS/EC2)"),
                ToolParameter(name="metric_name", type=ToolParameterType.string, description="Metric name"),
                ToolParameter(name="period_hours", type=ToolParameterType.integer, description="Lookback period in hours", required=False, default=24),
            ]),
        ],
    },
    "cloudflare": {
        "name": "Cloudflare",
        "description": "DNS, security, and performance — manage zones, DNS records, and view analytics.",
        "category": ConnectorCategory.cloud,
        "auth": BearerAuthConfig(credential_label="Cloudflare API Token"),
        "tags": ["cloudflare", "dns", "security", "cdn", "cloud"],
        "tools": [
            ToolSchema(id="cloudflare.list_zones", name="List zones", description="List all DNS zones in the Cloudflare account.", action_class=ToolActionClass.read, parameters=[]),
            ToolSchema(id="cloudflare.list_dns_records", name="List DNS records", description="List DNS records for a zone.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="zone_id", type=ToolParameterType.string, description="Zone ID")]),
            ToolSchema(id="cloudflare.create_dns_record", name="Create DNS record", description="Create a new DNS record.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="zone_id", type=ToolParameterType.string, description="Zone ID"),
                ToolParameter(name="type", type=ToolParameterType.string, description="Record type: A, AAAA, CNAME, TXT, MX"),
                ToolParameter(name="name", type=ToolParameterType.string, description="Record name"),
                ToolParameter(name="content", type=ToolParameterType.string, description="Record value"),
                ToolParameter(name="proxied", type=ToolParameterType.boolean, description="Enable Cloudflare proxy", required=False, default=True),
            ]),
            ToolSchema(id="cloudflare.get_analytics", name="Get analytics", description="Get traffic analytics for a zone.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="zone_id", type=ToolParameterType.string, description="Zone ID"),
                ToolParameter(name="hours", type=ToolParameterType.integer, description="Lookback hours", required=False, default=24),
            ]),
        ],
    },
    "vercel": {
        "name": "Vercel",
        "description": "Deployment platform — list projects, deployments, domains, and environment variables.",
        "category": ConnectorCategory.cloud,
        "auth": BearerAuthConfig(credential_label="Vercel Access Token"),
        "tags": ["vercel", "deployment", "hosting", "cloud"],
        "tools": [
            ToolSchema(id="vercel.list_projects", name="List projects", description="List all Vercel projects.", action_class=ToolActionClass.read, parameters=[]),
            ToolSchema(id="vercel.list_deployments", name="List deployments", description="List recent deployments for a project.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="project_id", type=ToolParameterType.string, description="Project ID or name"),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=10),
            ]),
            ToolSchema(id="vercel.get_deployment", name="Get deployment", description="Get details of a specific deployment.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="deployment_id", type=ToolParameterType.string, description="Deployment ID or URL")]),
            ToolSchema(id="vercel.list_domains", name="List domains", description="List custom domains for a project.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="project_id", type=ToolParameterType.string, description="Project ID")]),
        ],
    },
    "twitter": {
        "name": "X (Twitter)",
        "description": "Post tweets, search conversations, and monitor mentions via the X/Twitter API.",
        "category": ConnectorCategory.social,
        "auth": BearerAuthConfig(credential_label="X/Twitter Bearer Token"),
        "tags": ["twitter", "x", "social-media", "posts"],
        "tools": [
            ToolSchema(id="twitter.post_tweet", name="Post tweet", description="Post a new tweet.", action_class=ToolActionClass.execute, parameters=[ToolParameter(name="text", type=ToolParameterType.string, description="Tweet text (max 280 chars)")]),
            ToolSchema(id="twitter.search_tweets", name="Search tweets", description="Search recent tweets matching a query.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="query", type=ToolParameterType.string, description="Search query"),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=20),
            ]),
            ToolSchema(id="twitter.get_mentions", name="Get mentions", description="Get recent mentions of the authenticated user.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=20)]),
            ToolSchema(id="twitter.get_user_tweets", name="Get user tweets", description="Get recent tweets from a specific user.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="username", type=ToolParameterType.string, description="Twitter username (without @)"),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=20),
            ]),
        ],
    },
    "linkedin": {
        "name": "LinkedIn",
        "description": "Professional networking — post content, search profiles, and manage company pages.",
        "category": ConnectorCategory.social,
        "auth": OAuth2AuthConfig(
            authorization_url="https://www.linkedin.com/oauth/v2/authorization",
            token_url="https://www.linkedin.com/oauth/v2/accessToken",
            scopes=["r_liteprofile", "w_member_social"],
        ),
        "tags": ["linkedin", "social-media", "professional", "networking"],
        "tools": [
            ToolSchema(id="linkedin.create_post", name="Create post", description="Publish a post on LinkedIn.", action_class=ToolActionClass.execute, parameters=[ToolParameter(name="text", type=ToolParameterType.string, description="Post content")]),
            ToolSchema(id="linkedin.get_profile", name="Get profile", description="Get the authenticated user's LinkedIn profile.", action_class=ToolActionClass.read, parameters=[]),
            ToolSchema(id="linkedin.search_people", name="Search people", description="Search LinkedIn profiles by keywords.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="keywords", type=ToolParameterType.string, description="Search keywords"),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=10),
            ]),
            ToolSchema(id="linkedin.get_company", name="Get company", description="Get a company page's details.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="company_id", type=ToolParameterType.string, description="LinkedIn company ID")]),
        ],
    },
    "youtube": {
        "name": "YouTube",
        "description": "YouTube Data API — channel analytics, video search, playlists, and comment management.",
        "category": ConnectorCategory.social,
        "auth": OAuth2AuthConfig(
            authorization_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",
            scopes=["https://www.googleapis.com/auth/youtube.readonly"],
        ),
        "tags": ["youtube", "google", "video", "analytics"],
        "suite_id": "google", "suite_label": "Google", "service_order": 60,
        "tools": [
            ToolSchema(id="youtube.search_videos", name="Search videos", description="Search YouTube videos by query.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="query", type=ToolParameterType.string, description="Search query"),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=10),
            ]),
            ToolSchema(id="youtube.get_channel_stats", name="Channel stats", description="Get subscriber count, video count, and view stats for a channel.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="channel_id", type=ToolParameterType.string, description="YouTube channel ID")]),
            ToolSchema(id="youtube.get_video_details", name="Video details", description="Get details, stats, and comments for a video.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="video_id", type=ToolParameterType.string, description="YouTube video ID")]),
            ToolSchema(id="youtube.list_playlists", name="List playlists", description="List playlists for a channel.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="channel_id", type=ToolParameterType.string, description="Channel ID")]),
        ],
    },
    "spotify": {
        "name": "Spotify",
        "description": "Spotify Web API — search tracks, get playlists, artist data, and playback control.",
        "category": ConnectorCategory.other,
        "auth": OAuth2AuthConfig(
            authorization_url="https://accounts.spotify.com/authorize",
            token_url="https://accounts.spotify.com/api/token",
            scopes=["user-read-playback-state", "playlist-read-private"],
        ),
        "tags": ["spotify", "music", "media", "entertainment"],
        "tools": [
            ToolSchema(id="spotify.search", name="Search", description="Search Spotify for tracks, artists, albums, or playlists.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="query", type=ToolParameterType.string, description="Search query"),
                ToolParameter(name="type", type=ToolParameterType.string, description="Type: track, artist, album, playlist", required=False, default="track"),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=10),
            ]),
            ToolSchema(id="spotify.get_playlist", name="Get playlist", description="Get tracks in a Spotify playlist.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="playlist_id", type=ToolParameterType.string, description="Playlist ID")]),
            ToolSchema(id="spotify.get_artist", name="Get artist", description="Get artist details including top tracks and related artists.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="artist_id", type=ToolParameterType.string, description="Artist ID")]),
        ],
    },
    "openai": {
        "name": "OpenAI",
        "description": "Call OpenAI models (GPT, DALL-E, Whisper) as tools within Maia agent workflows.",
        "category": ConnectorCategory.developer_tools,
        "auth": ApiKeyAuthConfig(param_name="Authorization", credential_label="OpenAI API Key"),
        "tags": ["openai", "ai", "llm", "gpt"],
        "tools": [
            ToolSchema(id="openai.chat", name="Chat completion", description="Generate a response from an OpenAI chat model.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="model", type=ToolParameterType.string, description="Model ID (gpt-4o, gpt-4o-mini)", required=False, default="gpt-4o-mini"),
                ToolParameter(name="messages", type=ToolParameterType.array, description="Chat messages array"),
                ToolParameter(name="max_tokens", type=ToolParameterType.integer, description="Max tokens", required=False, default=1000),
            ]),
            ToolSchema(id="openai.image", name="Generate image", description="Generate an image using DALL-E.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="prompt", type=ToolParameterType.string, description="Image description"),
                ToolParameter(name="size", type=ToolParameterType.string, description="Size: 1024x1024, 512x512", required=False, default="1024x1024"),
            ]),
            ToolSchema(id="openai.embeddings", name="Create embeddings", description="Generate text embeddings for semantic search.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="input", type=ToolParameterType.string, description="Text to embed"),
                ToolParameter(name="model", type=ToolParameterType.string, description="Embedding model", required=False, default="text-embedding-3-small"),
            ]),
        ],
    },
    "pinecone": {
        "name": "Pinecone",
        "description": "Vector database — upsert, query, and manage embeddings for semantic search and RAG.",
        "category": ConnectorCategory.database,
        "auth": ApiKeyAuthConfig(param_name="Api-Key", credential_label="Pinecone API Key"),
        "tags": ["pinecone", "vector-db", "embeddings", "rag", "ai"],
        "tools": [
            ToolSchema(id="pinecone.query", name="Query vectors", description="Query a Pinecone index for similar vectors.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="index_name", type=ToolParameterType.string, description="Index name"),
                ToolParameter(name="vector", type=ToolParameterType.array, description="Query vector (float array)"),
                ToolParameter(name="top_k", type=ToolParameterType.integer, description="Number of results", required=False, default=10),
                ToolParameter(name="namespace", type=ToolParameterType.string, description="Namespace filter", required=False),
            ]),
            ToolSchema(id="pinecone.upsert", name="Upsert vectors", description="Upsert vectors into a Pinecone index.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="index_name", type=ToolParameterType.string, description="Index name"),
                ToolParameter(name="vectors", type=ToolParameterType.array, description="Array of {id, values, metadata} objects"),
                ToolParameter(name="namespace", type=ToolParameterType.string, description="Namespace", required=False),
            ]),
            ToolSchema(id="pinecone.list_indexes", name="List indexes", description="List all Pinecone indexes.", action_class=ToolActionClass.read, parameters=[]),
        ],
    },
}
