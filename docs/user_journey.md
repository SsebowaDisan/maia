# Maia Agent OS — User Journey
**What users experience, what they see, and what they gain.**

---

## Who uses Maia

| Persona | Role | Core need |
|---------|------|-----------|
| **Alex** | Operations Manager | Automate repetitive tasks without writing code |
| **Sarah** | Sales Director | Get instant deal intelligence and follow-up drafts |
| **James** | Developer | Build and publish agents for his team or marketplace |
| **Priya** | CFO | Understand what AI is costing and doing across the company |

---

## Journey 1 — First Day: Ask a question, get an answer

**Alex opens Maia for the first time.**

### What he sees
A clean chat interface — a single composer box, nothing else in the way. No setup wizard. No configuration required.

He types:
> "Summarise last quarter's pipeline and flag any deals at risk."

### What happens
- Maia searches the company's indexed documents (CRM exports, emails, call notes)
- Citations appear inline in the response — each claim links back to its source
- A confidence indicator shows how well-supported each insight is
- A PDF evidence map highlights the exact paragraphs used

### What Alex gains
**5 minutes instead of 2 hours.** He used to pull this from Salesforce, paste into Excel, write the summary himself. Now it's one message.

---

## Journey 2 — Week 1: Build an agent that works while you sleep

**Sarah wants a deal-briefing agent** that watches Salesforce and sends her a summary every Monday morning before her team standup.

### Step 1 — Open Agent Builder

She clicks **Agents → New Agent** in the sidebar.

She sees a two-panel builder:
- **Left**: Form fields — name, description, system prompt, tools, memory settings
- **Right**: Live YAML preview that updates as she types

She fills in:
- Name: `Deal Briefing`
- System prompt: *"You are a sales intelligence assistant. Every Monday morning, pull the top 10 open deals from Salesforce, identify risks and next steps, and write a concise brief for the sales director."*
- Tools: `salesforce` (checked), `gmail` (checked — for delivery)
- Trigger: `Scheduled → every Monday at 08:00`

### Step 2 — Gate setup (optional but she turns it on)

She enables a gate on `gmail.send`:
> "Before sending any email, show me the draft for approval."

This means the agent will **pause and ask her permission** before any email goes out.

### Step 3 — Save and activate

She clicks **Save**. The agent is live. A confirmation card shows:
> "Deal Briefing will run next Monday at 08:00. You'll be notified when it's ready."

### Monday 08:00

Sarah gets a notification. She opens Maia. The agent ran overnight — it pulled 10 deals, wrote the brief, and is now paused at the gate.

She sees a **Gate Approval Card**:
```
⏸ Agent paused — email ready for review
To: sarah@company.com
Subject: Deal Brief — Week 14
[Preview of the email]

[ Approve & Send ]  [ Edit ]  [ Reject ]
```

She reads it, clicks **Approve & Send**. Done.

### What Sarah gains
- No more Monday morning scramble
- Full control — she approves before anything is sent
- Brief is always accurate — pulled from live Salesforce data, not memory

---

## Journey 3 — Week 2: Watch an agent work in real time

**Alex builds a research agent** to investigate a new prospect before a discovery call.

He types in chat:
> "@prospect-researcher Investigate Acme Corp — what do they do, who are the key contacts, what's their tech stack?"

### What he sees — the Activity Theatre

The right panel opens. This is the **Activity Theatre** — a live view of everything the agent is doing, step by step:

```
▶ Phase 1 — Planning
  → Identifying research tasks: company overview, contacts, tech stack

▶ Phase 2 — Executing
  ✓ Searched company website
  ✓ Pulled LinkedIn profiles for 3 key contacts
  ✓ Checked BuiltWith for tech stack

▶ Phase 3 — Computer Use
  [ Browser window opens live ]
  → Agent navigates to LinkedIn
  → Screenshots update every second
  → Typing "Acme Corp" into search
  → Scrolling through results

▶ Phase 4 — Writing
  → Drafting research brief...
```

While this runs, Alex can see the browser window inside Maia — **exactly what the agent sees** — a live screenshot stream updating in real time. The agent clicks, scrolls, reads pages, just like a human would.

### The result

A structured research brief appears in the chat:
- Company overview (2 paragraphs)
- 3 key contacts with LinkedIn URLs and notes
- Tech stack: React, AWS, Salesforce, HubSpot
- "Potential angle: They recently hired 3 SDRs — growth mode"

### What Alex gains
**30 minutes of research done in 4 minutes.** And he watched every step — nothing was hidden, nothing was assumed.

---

## Journey 4 — Week 3: Delegate complex tasks to a chain of agents

**Sarah's team is growing.** She sets up a **workflow** — a chain of agents that handle the full post-demo follow-up sequence automatically.

### The workflow

```
Step 1: Demo Notes Agent
  Input: Raw Zoom transcript
  Output: Structured notes (pain points, budget, timeline, next steps)
           ↓
Step 2: Proposal Agent
  Input: Structured notes
  Output: Tailored proposal PDF draft
           ↓  (only if confidence score > 0.8)
Step 3: Email Agent
  Input: Proposal draft
  Output: Cover email draft — paused at gate for human approval
```

### What she builds

In the **Workflow Builder**, she drags three agent cards onto a canvas, draws arrows between them, and adds a condition on the edge between step 1 and 2:
> "Only proceed if output.confidence > 0.8"

She saves it. Now every time a Zoom transcript lands in a watched folder, the whole sequence fires automatically.

### In the Activity Theatre

When a workflow runs, Sarah sees a **phase timeline** — each step lights up as it completes, with timing and status. She can replay any step to understand what the agent produced.

### What Sarah gains
- Follow-up emails go out the same day as the demo — not 3 days later
- Proposals are personalised to every prospect's specific pain points
- She only reads the final email before it sends — the rest is handled

---

## Journey 5 — Week 4: Install an agent from the Marketplace

**James** (developer) publishes a `Legal Contract Reviewer` agent to the marketplace. Sarah discovers it.

### Discovery

She opens **Marketplace** from the sidebar. She sees a grid of agent cards:

```
[ Legal Contract Reviewer ]   [ CRM Lead Scorer ]   [ Support Ticket Triage ]
Publisher: James @ LegalTech  Installs: 847          Installs: 2,341
Rating: ★★★★★ (94 reviews)   Rating: ★★★★☆         Rating: ★★★★★
Required: google_drive         Required: salesforce   Required: zendesk
[ Install ]                   [ Install ]            [ Install ]
```

She clicks **Install** on Legal Contract Reviewer.

### The install flow (4 steps)

**Step 1 — Review access**
> This agent needs access to: Google Drive, Gmail

**Step 2 — Map connectors**
> Map `google_drive` → [her company's Google Workspace account]

**Step 3 — Gate preferences**
> ☑ Require approval before sending any email

**Step 4 — Confirm**
> Installing version 1.2.0 · 1 connector mapping · 1 gate policy
> [ Install agent ]

Done. The agent appears in her agent list, ready to use.

### Using it

She drops a contract PDF into Maia and types:
> "@contract-reviewer Review this NDA and flag any unusual clauses."

The agent reads the contract, highlights 3 unusual clauses with explanations, and rates overall risk as Medium.

### What Sarah gains
**No legal fees for initial review.** She catches issues before sending to counsel, saving £400–800 per contract in billable time.

---

## Journey 6 — Operations: What the CFO sees

**Priya** needs to understand what agents are doing and what they cost.

### Operations Dashboard

She opens **Operations** from the sidebar.

```
Fleet Overview — last 7 days
────────────────────────────────
Active agents:        12
Total runs:           847
Success rate:         94.2%
Avg run time:         38s

Top agents by usage:
  Deal Briefing        │████████████ 142 runs
  Prospect Researcher  │████████     89 runs
  Contract Reviewer    │██████       67 runs

Cost this week:       $12.40
Budget limit:         $50.00 / day
  ██░░░░░░░░  24.8% used today

Computer Use steps:   1,204
Gate approvals:       23  (18 approved, 5 rejected)
```

She drills into the **Deal Briefing** agent:

```
Run #847 — Monday 08:00 ✓ Completed (41s)
Run #834 — Monday 08:00 ✓ Completed (38s)
Run #821 — Monday 08:00 ✗ Failed — Salesforce timeout
```

She sees the error log, the exact step it failed on, and the automatic retry.

### Budget control

She sets a daily limit: `$20.00`. If spend hits that limit, new runs pause and she gets a notification. No surprise bills.

### What Priya gains
- Full audit trail of every agent action
- Real-time cost per agent, per day
- Ability to set hard limits — finance remains in control

---

## The human-in-the-loop principle

Across every journey, Maia follows one rule:
> **Agents do the work. Humans make the calls.**

Every agent can be configured with gates — checkpoints where the agent **pauses and asks for permission** before taking a consequential action (sending an email, updating a CRM record, making a purchase).

The user sees a clear approval card with:
- What the agent is about to do
- A preview of the output
- Approve / Edit / Reject

Nothing irreversible happens without a human decision.

---

## What users see — UI surface summary

| Screen | What it shows |
|--------|--------------|
| **Chat** | Conversation with Maia — questions, research, citations |
| **Activity Theatre** | Live step-by-step view of agent execution |
| **Browser Scene** | Live screenshot stream — Computer Use in real time |
| **Gate Approval Card** | Pause point — review and approve/reject agent action |
| **Agent Builder** | Create/edit agents — prompt, tools, trigger, gates, memory |
| **Workflow Builder** | Chain agents into multi-step pipelines with conditions |
| **Marketplace** | Browse, install, and rate agents built by others |
| **Connectors** | Connect to Salesforce, Gmail, Slack, Notion, GitHub, etc. |
| **Operations Dashboard** | Fleet metrics, cost tracking, error log, budget control |
| **File Library** | Upload documents, URLs — the knowledge base |

---

## What users gain — summary

| Pain today | With Maia |
|-----------|-----------|
| 2 hours of manual research | 4 minutes, with sources |
| Missed follow-ups after demos | Automated same-day proposal + email (with approval gate) |
| Monday morning report scramble | Agent delivers it at 08:00 before standup |
| £800 per contract for initial legal review | Agent flags risks in 90 seconds |
| No visibility into what AI tools cost | Real-time cost dashboard per agent |
| "I don't trust AI to act on my behalf" | Every consequential action paused for human approval |
| Siloed data across 10 tools | One place — Maia reads and writes across all connected tools |

---

## The experience in one sentence

> You describe what you need. Maia works through it — using your tools, reading your data, taking actions in the real world — while you watch, stay in control, and only approve what matters.
