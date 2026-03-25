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

PROFILES_EXT_TIER1: dict[str, dict] = {
    # ══════════════════════════════════════════════════════════════════════════
    # TIER 1 — Essential connectors (every competitor has these)
    # ══════════════════════════════════════════════════════════════════════════
    "github": {
        "name": "GitHub",
        "description": "Repositories, issues, pull requests, and Actions via GitHub API.",
        "category": ConnectorCategory.developer_tools,
        "auth": BearerAuthConfig(credential_label="GitHub Personal Access Token"),
        "tags": ["github", "git", "developer", "code"],
        "tools": [
            ToolSchema(id="github.list_repos", name="List repos", description="List repositories for the authenticated user or an organisation.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="org", type=ToolParameterType.string, description="Organisation name (omit for personal repos)", required=False),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=20),
            ]),
            ToolSchema(id="github.search_issues", name="Search issues", description="Search issues and PRs across repositories.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="query", type=ToolParameterType.string, description="GitHub search query"),
                ToolParameter(name="repo", type=ToolParameterType.string, description="Limit to repo (owner/repo)", required=False),
            ]),
            ToolSchema(id="github.create_issue", name="Create issue", description="Create a new issue in a GitHub repository.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="repo", type=ToolParameterType.string, description="Repository (owner/repo)"),
                ToolParameter(name="title", type=ToolParameterType.string, description="Issue title"),
                ToolParameter(name="body", type=ToolParameterType.string, description="Issue body (markdown)"),
                ToolParameter(name="labels", type=ToolParameterType.array, description="Labels to apply", required=False),
                ToolParameter(name="assignees", type=ToolParameterType.array, description="Assignee usernames", required=False),
            ]),
            ToolSchema(id="github.get_pr", name="Get pull request", description="Get details of a pull request including diff stats.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="repo", type=ToolParameterType.string, description="Repository (owner/repo)"),
                ToolParameter(name="pr_number", type=ToolParameterType.integer, description="PR number"),
            ]),
            ToolSchema(id="github.create_pr", name="Create pull request", description="Open a new pull request.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="repo", type=ToolParameterType.string, description="Repository (owner/repo)"),
                ToolParameter(name="title", type=ToolParameterType.string, description="PR title"),
                ToolParameter(name="body", type=ToolParameterType.string, description="PR description"),
                ToolParameter(name="head", type=ToolParameterType.string, description="Source branch"),
                ToolParameter(name="base", type=ToolParameterType.string, description="Target branch", required=False, default="main"),
            ]),
            ToolSchema(id="github.get_file", name="Get file contents", description="Read a file from a GitHub repository.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="repo", type=ToolParameterType.string, description="Repository (owner/repo)"),
                ToolParameter(name="path", type=ToolParameterType.string, description="File path in the repo"),
                ToolParameter(name="ref", type=ToolParameterType.string, description="Branch or commit SHA", required=False, default="main"),
            ]),
            ToolSchema(id="github.list_actions_runs", name="List workflow runs", description="List recent GitHub Actions workflow runs.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="repo", type=ToolParameterType.string, description="Repository (owner/repo)"),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=10),
            ]),
        ],
    },
    "linear": {
        "name": "Linear",
        "description": "Modern issue tracking — create, update, and search issues, projects, and cycles.",
        "category": ConnectorCategory.project_management,
        "auth": BearerAuthConfig(credential_label="Linear API Key"),
        "tags": ["linear", "project-management", "issues", "engineering"],
        "tools": [
            ToolSchema(id="linear.search_issues", name="Search issues", description="Search Linear issues by text, status, or assignee.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="query", type=ToolParameterType.string, description="Search query"),
                ToolParameter(name="team", type=ToolParameterType.string, description="Team key filter", required=False),
                ToolParameter(name="status", type=ToolParameterType.string, description="Status filter", required=False),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=20),
            ]),
            ToolSchema(id="linear.create_issue", name="Create issue", description="Create a new Linear issue.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="team_id", type=ToolParameterType.string, description="Team ID"),
                ToolParameter(name="title", type=ToolParameterType.string, description="Issue title"),
                ToolParameter(name="description", type=ToolParameterType.string, description="Issue description (markdown)", required=False),
                ToolParameter(name="priority", type=ToolParameterType.integer, description="Priority 0-4 (0=none, 1=urgent, 4=low)", required=False),
                ToolParameter(name="assignee_id", type=ToolParameterType.string, description="Assignee user ID", required=False),
            ]),
            ToolSchema(id="linear.update_issue", name="Update issue", description="Update a Linear issue's status, assignee, or priority.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="issue_id", type=ToolParameterType.string, description="Issue ID"),
                ToolParameter(name="status", type=ToolParameterType.string, description="New status", required=False),
                ToolParameter(name="priority", type=ToolParameterType.integer, description="New priority", required=False),
                ToolParameter(name="assignee_id", type=ToolParameterType.string, description="New assignee", required=False),
            ]),
            ToolSchema(id="linear.get_cycles", name="Get cycles", description="List active and upcoming cycles for a team.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="team_id", type=ToolParameterType.string, description="Team ID")]),
        ],
    },
    "asana": {
        "name": "Asana",
        "description": "Project and task management — create tasks, track progress, and manage teams.",
        "category": ConnectorCategory.project_management,
        "auth": BearerAuthConfig(credential_label="Asana Personal Access Token"),
        "tags": ["asana", "project-management", "tasks", "teams"],
        "tools": [
            ToolSchema(id="asana.search_tasks", name="Search tasks", description="Search tasks across Asana projects and workspaces.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="query", type=ToolParameterType.string, description="Search text"),
                ToolParameter(name="project_id", type=ToolParameterType.string, description="Filter to project", required=False),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=20),
            ]),
            ToolSchema(id="asana.create_task", name="Create task", description="Create a new task in an Asana project.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="project_id", type=ToolParameterType.string, description="Project ID"),
                ToolParameter(name="name", type=ToolParameterType.string, description="Task name"),
                ToolParameter(name="notes", type=ToolParameterType.string, description="Task description", required=False),
                ToolParameter(name="due_date", type=ToolParameterType.string, description="Due date YYYY-MM-DD", required=False),
                ToolParameter(name="assignee", type=ToolParameterType.string, description="Assignee email or user ID", required=False),
            ]),
            ToolSchema(id="asana.update_task", name="Update task", description="Update a task's status, assignee, or due date.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="task_id", type=ToolParameterType.string, description="Task ID"),
                ToolParameter(name="completed", type=ToolParameterType.boolean, description="Mark complete/incomplete", required=False),
                ToolParameter(name="due_date", type=ToolParameterType.string, description="New due date", required=False),
                ToolParameter(name="assignee", type=ToolParameterType.string, description="New assignee", required=False),
            ]),
            ToolSchema(id="asana.list_projects", name="List projects", description="List projects in a workspace.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="workspace_id", type=ToolParameterType.string, description="Workspace ID")]),
        ],
    },
    "monday": {
        "name": "Monday.com",
        "description": "Work OS — boards, items, columns, and automations via Monday.com API.",
        "category": ConnectorCategory.project_management,
        "auth": BearerAuthConfig(credential_label="Monday.com API Token"),
        "tags": ["monday", "project-management", "boards", "work-os"],
        "tools": [
            ToolSchema(id="monday.list_boards", name="List boards", description="List all boards accessible to the authenticated user.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=20)]),
            ToolSchema(id="monday.get_items", name="Get items", description="Get items from a Monday.com board with column values.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="board_id", type=ToolParameterType.string, description="Board ID"),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max items", required=False, default=50),
            ]),
            ToolSchema(id="monday.create_item", name="Create item", description="Create a new item on a Monday.com board.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="board_id", type=ToolParameterType.string, description="Board ID"),
                ToolParameter(name="item_name", type=ToolParameterType.string, description="Item name"),
                ToolParameter(name="column_values", type=ToolParameterType.object, description="Column values as JSON", required=False),
                ToolParameter(name="group_id", type=ToolParameterType.string, description="Group ID to add item to", required=False),
            ]),
            ToolSchema(id="monday.update_item", name="Update item", description="Update column values on an existing item.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="board_id", type=ToolParameterType.string, description="Board ID"),
                ToolParameter(name="item_id", type=ToolParameterType.string, description="Item ID"),
                ToolParameter(name="column_values", type=ToolParameterType.object, description="Column values to update"),
            ]),
        ],
    },
    "trello": {
        "name": "Trello",
        "description": "Kanban boards — cards, lists, and checklists via Trello API.",
        "category": ConnectorCategory.project_management,
        "auth": ApiKeyAuthConfig(param_name="key", credential_label="Trello API Key + Token"),
        "tags": ["trello", "kanban", "boards", "project-management"],
        "tools": [
            ToolSchema(id="trello.list_boards", name="List boards", description="List all Trello boards for the authenticated user.", action_class=ToolActionClass.read, parameters=[]),
            ToolSchema(id="trello.get_cards", name="Get cards", description="Get all cards on a Trello board.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="board_id", type=ToolParameterType.string, description="Board ID")]),
            ToolSchema(id="trello.create_card", name="Create card", description="Create a new Trello card on a list.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="list_id", type=ToolParameterType.string, description="List ID"),
                ToolParameter(name="name", type=ToolParameterType.string, description="Card name"),
                ToolParameter(name="description", type=ToolParameterType.string, description="Card description", required=False),
                ToolParameter(name="due_date", type=ToolParameterType.string, description="Due date", required=False),
            ]),
            ToolSchema(id="trello.move_card", name="Move card", description="Move a card to a different list.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="card_id", type=ToolParameterType.string, description="Card ID"),
                ToolParameter(name="list_id", type=ToolParameterType.string, description="Destination list ID"),
            ]),
        ],
    },
    "discord": {
        "name": "Discord",
        "description": "Send messages, manage channels, and interact with Discord communities via bot API.",
        "category": ConnectorCategory.communication,
        "auth": BearerAuthConfig(credential_label="Discord Bot Token"),
        "tags": ["discord", "messaging", "community", "chat"],
        "tools": [
            ToolSchema(id="discord.send_message", name="Send message", description="Send a message to a Discord channel.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="channel_id", type=ToolParameterType.string, description="Channel ID"),
                ToolParameter(name="content", type=ToolParameterType.string, description="Message text"),
            ]),
            ToolSchema(id="discord.read_messages", name="Read messages", description="Read recent messages from a Discord channel.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="channel_id", type=ToolParameterType.string, description="Channel ID"),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Number of messages", required=False, default=20),
            ]),
            ToolSchema(id="discord.list_channels", name="List channels", description="List channels in a Discord server.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="guild_id", type=ToolParameterType.string, description="Server/guild ID")]),
            ToolSchema(id="discord.create_thread", name="Create thread", description="Create a new thread in a channel.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="channel_id", type=ToolParameterType.string, description="Channel ID"),
                ToolParameter(name="name", type=ToolParameterType.string, description="Thread name"),
                ToolParameter(name="message", type=ToolParameterType.string, description="Initial message"),
            ]),
        ],
    },
    "microsoft_teams": {
        "name": "Microsoft Teams",
        "description": "Send messages, manage channels, and schedule meetings in Microsoft Teams.",
        "category": ConnectorCategory.communication,
        "auth": OAuth2AuthConfig(
            authorization_url="https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
            token_url="https://login.microsoftonline.com/common/oauth2/v2.0/token",
            scopes=["ChannelMessage.Send", "Channel.ReadBasic.All", "Chat.ReadWrite"],
        ),
        "tags": ["microsoft", "teams", "messaging", "enterprise"],
        "suite_id": "microsoft", "suite_label": "Microsoft 365", "service_order": 10,
        "tools": [
            ToolSchema(id="teams.send_message", name="Send message", description="Send a message to a Teams channel.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="team_id", type=ToolParameterType.string, description="Team ID"),
                ToolParameter(name="channel_id", type=ToolParameterType.string, description="Channel ID"),
                ToolParameter(name="content", type=ToolParameterType.string, description="Message text (supports HTML)"),
            ]),
            ToolSchema(id="teams.read_messages", name="Read messages", description="Read recent messages from a Teams channel.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="team_id", type=ToolParameterType.string, description="Team ID"),
                ToolParameter(name="channel_id", type=ToolParameterType.string, description="Channel ID"),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max messages", required=False, default=20),
            ]),
            ToolSchema(id="teams.list_channels", name="List channels", description="List channels in a Team.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="team_id", type=ToolParameterType.string, description="Team ID")]),
            ToolSchema(id="teams.list_teams", name="List teams", description="List all teams the user is a member of.", action_class=ToolActionClass.read, parameters=[]),
        ],
    },
    "twilio": {
        "name": "Twilio",
        "description": "Send SMS, WhatsApp messages, and make calls via Twilio API.",
        "category": ConnectorCategory.communication,
        "auth": ApiKeyAuthConfig(param_name="Authorization", credential_label="Twilio Account SID + Auth Token"),
        "tags": ["twilio", "sms", "whatsapp", "voice", "messaging"],
        "tools": [
            ToolSchema(id="twilio.send_sms", name="Send SMS", description="Send an SMS message via Twilio.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="to", type=ToolParameterType.string, description="Recipient phone number (+E.164 format)"),
                ToolParameter(name="body", type=ToolParameterType.string, description="Message text"),
                ToolParameter(name="from_number", type=ToolParameterType.string, description="Twilio phone number to send from", required=False),
            ]),
            ToolSchema(id="twilio.send_whatsapp", name="Send WhatsApp", description="Send a WhatsApp message via Twilio.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="to", type=ToolParameterType.string, description="Recipient WhatsApp number"),
                ToolParameter(name="body", type=ToolParameterType.string, description="Message text"),
            ]),
            ToolSchema(id="twilio.list_messages", name="List messages", description="List recent inbound and outbound messages.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=20),
                ToolParameter(name="to", type=ToolParameterType.string, description="Filter by recipient", required=False),
            ]),
        ],
    },
    "intercom": {
        "name": "Intercom",
        "description": "Customer messaging platform — conversations, contacts, and articles via Intercom API.",
        "category": ConnectorCategory.support,
        "auth": BearerAuthConfig(credential_label="Intercom Access Token"),
        "tags": ["intercom", "support", "messaging", "customer-success"],
        "tools": [
            ToolSchema(id="intercom.search_contacts", name="Search contacts", description="Search Intercom contacts by name or email.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="query", type=ToolParameterType.string, description="Search query")]),
            ToolSchema(id="intercom.list_conversations", name="List conversations", description="List recent conversations with status and assignee.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="status", type=ToolParameterType.string, description="Filter: open, closed, snoozed", required=False, default="open"),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=20),
            ]),
            ToolSchema(id="intercom.reply_conversation", name="Reply to conversation", description="Send a reply in an Intercom conversation.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="conversation_id", type=ToolParameterType.string, description="Conversation ID"),
                ToolParameter(name="body", type=ToolParameterType.string, description="Reply text"),
                ToolParameter(name="message_type", type=ToolParameterType.string, description="Type: comment (public) or note (internal)", required=False, default="comment"),
            ]),
            ToolSchema(id="intercom.create_article", name="Create article", description="Create a help centre article.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="title", type=ToolParameterType.string, description="Article title"),
                ToolParameter(name="body", type=ToolParameterType.string, description="Article content (HTML)"),
                ToolParameter(name="collection_id", type=ToolParameterType.string, description="Collection to add article to", required=False),
            ]),
        ],
    },
    "mailchimp": {
        "name": "Mailchimp",
        "description": "Email marketing — campaigns, audiences, and templates via Mailchimp API.",
        "category": ConnectorCategory.marketing,
        "auth": ApiKeyAuthConfig(param_name="Authorization", credential_label="Mailchimp API Key"),
        "tags": ["mailchimp", "email", "marketing", "campaigns"],
        "tools": [
            ToolSchema(id="mailchimp.list_campaigns", name="List campaigns", description="List email campaigns with send stats.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="status", type=ToolParameterType.string, description="Filter: sent, draft, schedule", required=False),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=20),
            ]),
            ToolSchema(id="mailchimp.get_campaign_report", name="Campaign report", description="Get open rate, click rate, and bounce stats for a campaign.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="campaign_id", type=ToolParameterType.string, description="Campaign ID")]),
            ToolSchema(id="mailchimp.add_subscriber", name="Add subscriber", description="Add a subscriber to a Mailchimp audience.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="list_id", type=ToolParameterType.string, description="Audience/list ID"),
                ToolParameter(name="email", type=ToolParameterType.string, description="Subscriber email"),
                ToolParameter(name="first_name", type=ToolParameterType.string, description="First name", required=False),
                ToolParameter(name="last_name", type=ToolParameterType.string, description="Last name", required=False),
                ToolParameter(name="tags", type=ToolParameterType.array, description="Tags to apply", required=False),
            ]),
            ToolSchema(id="mailchimp.search_members", name="Search members", description="Search audience members by email or name.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="list_id", type=ToolParameterType.string, description="Audience/list ID"),
                ToolParameter(name="query", type=ToolParameterType.string, description="Search query"),
            ]),
        ],
    },
}
