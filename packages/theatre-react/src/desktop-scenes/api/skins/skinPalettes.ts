import type { SkinDescriptor, SkinPalette } from "./skinTypes";

// ── Brand variant type — every connector that gets a custom skin ─────────────
type SkinVariant =
  // Email
  | "gmail" | "outlook"
  // Chat
  | "slack" | "discord" | "microsoft_teams" | "twilio"
  // Sheet
  | "sheets" | "excel" | "airtable"
  // CRM
  | "salesforce" | "hubspot"
  // Support
  | "zendesk" | "intercom"
  // Commerce
  | "stripe" | "shopify" | "sap" | "quickbooks" | "xero"
  // Database
  | "postgresql" | "supabase" | "bigquery" | "pinecone"
  // Document
  | "notion" | "confluence" | "dropbox" | "box" | "docusign"
  // Social
  | "twitter" | "linkedin" | "youtube" | "spotify"
  // Marketing
  | "mailchimp" | "webflow"
  // Cloud
  | "aws" | "cloudflare" | "vercel"
  // Scheduling
  | "calendly"
  // Design
  | "figma"
  // Developer
  | "github" | "linear" | "jira"
  // Project Management
  | "asana" | "monday" | "trello"
  // Automation
  | "zapier_webhooks" | "make"
  // AI
  | "openai"
  // Search
  | "brave_search" | "bing_search"
  // Google extras
  | "google_analytics" | "google_ads" | "google_maps" | "google_calendar"
  // Misc
  | "invoice" | "reddit" | "newsapi" | "sec_edgar" | "page_monitor"
  | "email_validation" | "http_request";

// ── Palettes ─────────────────────────────────────────────────────────────────
const PALETTES: Record<SkinVariant, SkinPalette> = {
  // Email
  gmail:        { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(239,68,68,0.24),rgba(17,24,39,0.95)_56%)]", cardBg: "bg-white/90", cardBorder: "border-[#fecaca]", textPrimary: "text-[#111827]", textSecondary: "text-[#6b7280]", accentBg: "bg-[#ef4444]/15", accentText: "text-[#991b1b]" },
  outlook:      { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(37,99,235,0.24),rgba(17,24,39,0.95)_56%)]", cardBg: "bg-white/90", cardBorder: "border-[#bfdbfe]", textPrimary: "text-[#0f172a]", textSecondary: "text-[#64748b]", accentBg: "bg-[#2563eb]/15", accentText: "text-[#1e3a8a]" },
  // Chat
  slack:        { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(192,38,211,0.24),rgba(17,24,39,0.96)_60%)]", cardBg: "bg-white/90", cardBorder: "border-[#f5d0fe]", textPrimary: "text-[#111827]", textSecondary: "text-[#6b7280]", accentBg: "bg-[#c026d3]/15", accentText: "text-[#86198f]" },
  discord:      { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(88,101,242,0.28),rgba(17,24,39,0.96)_58%)]", cardBg: "bg-[#2b2d31]/95", cardBorder: "border-[#3f4248]", textPrimary: "text-[#f2f3f5]", textSecondary: "text-[#b5bac1]", accentBg: "bg-[#5865f2]/20", accentText: "text-[#949cf7]" },
  microsoft_teams: { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(98,75,174,0.24),rgba(17,24,39,0.95)_56%)]", cardBg: "bg-white/90", cardBorder: "border-[#ddd6fe]", textPrimary: "text-[#1e1b4b]", textSecondary: "text-[#6d28d9]", accentBg: "bg-[#624bae]/15", accentText: "text-[#4c1d95]" },
  twilio:       { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(244,23,43,0.22),rgba(17,24,39,0.95)_56%)]", cardBg: "bg-white/90", cardBorder: "border-[#fecdd3]", textPrimary: "text-[#111827]", textSecondary: "text-[#6b7280]", accentBg: "bg-[#f4172b]/15", accentText: "text-[#9f1239]" },
  // Sheet
  sheets:       { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(22,163,74,0.24),rgba(10,15,26,0.95)_58%)]", cardBg: "bg-[#f8fffb]/95", cardBorder: "border-[#bbf7d0]", textPrimary: "text-[#052e16]", textSecondary: "text-[#166534]", accentBg: "bg-[#16a34a]/15", accentText: "text-[#14532d]" },
  excel:        { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(5,150,105,0.24),rgba(9,14,23,0.95)_58%)]", cardBg: "bg-[#f4fffb]/95", cardBorder: "border-[#99f6e4]", textPrimary: "text-[#022c22]", textSecondary: "text-[#0f766e]", accentBg: "bg-[#059669]/15", accentText: "text-[#064e3b]" },
  airtable:     { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(252,196,25,0.22),rgba(17,24,39,0.95)_56%)]", cardBg: "bg-white/90", cardBorder: "border-[#fde68a]", textPrimary: "text-[#111827]", textSecondary: "text-[#92400e]", accentBg: "bg-[#fcc419]/15", accentText: "text-[#78350f]" },
  // CRM
  salesforce:   { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(0,176,240,0.24),rgba(17,24,39,0.95)_56%)]", cardBg: "bg-white/90", cardBorder: "border-[#bae6fd]", textPrimary: "text-[#032e5e]", textSecondary: "text-[#0369a1]", accentBg: "bg-[#00b0f0]/15", accentText: "text-[#075985]" },
  hubspot:      { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(255,122,0,0.24),rgba(17,24,39,0.95)_56%)]", cardBg: "bg-white/90", cardBorder: "border-[#fed7aa]", textPrimary: "text-[#111827]", textSecondary: "text-[#9a3412]", accentBg: "bg-[#ff7a00]/15", accentText: "text-[#7c2d12]" },
  // Support
  zendesk:      { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(3,54,73,0.30),rgba(17,24,39,0.95)_56%)]", cardBg: "bg-white/90", cardBorder: "border-[#d1fae5]", textPrimary: "text-[#03363d]", textSecondary: "text-[#065f46]", accentBg: "bg-[#03363d]/15", accentText: "text-[#03363d]" },
  intercom:     { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(0,128,255,0.24),rgba(17,24,39,0.95)_56%)]", cardBg: "bg-white/90", cardBorder: "border-[#bfdbfe]", textPrimary: "text-[#111827]", textSecondary: "text-[#1d4ed8]", accentBg: "bg-[#0080ff]/15", accentText: "text-[#1e40af]" },
  // Commerce
  stripe:       { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(99,91,255,0.24),rgba(17,24,39,0.95)_56%)]", cardBg: "bg-white/90", cardBorder: "border-[#c7d2fe]", textPrimary: "text-[#0f0d29]", textSecondary: "text-[#4338ca]", accentBg: "bg-[#635bff]/15", accentText: "text-[#3730a3]" },
  shopify:      { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(150,191,72,0.24),rgba(17,24,39,0.95)_56%)]", cardBg: "bg-white/90", cardBorder: "border-[#d9f99d]", textPrimary: "text-[#111827]", textSecondary: "text-[#3f6212]", accentBg: "bg-[#96bf48]/15", accentText: "text-[#365314]" },
  sap:          { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(2,132,199,0.24),rgba(11,19,32,0.96)_58%)]", cardBg: "bg-white/90", cardBorder: "border-[#bae6fd]", textPrimary: "text-[#0c4a6e]", textSecondary: "text-[#0369a1]", accentBg: "bg-[#0284c7]/15", accentText: "text-[#075985]" },
  quickbooks:   { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(44,160,28,0.24),rgba(17,24,39,0.95)_56%)]", cardBg: "bg-white/90", cardBorder: "border-[#bbf7d0]", textPrimary: "text-[#111827]", textSecondary: "text-[#15803d]", accentBg: "bg-[#2ca01c]/15", accentText: "text-[#166534]" },
  xero:         { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(19,181,234,0.24),rgba(17,24,39,0.95)_56%)]", cardBg: "bg-white/90", cardBorder: "border-[#a5f3fc]", textPrimary: "text-[#111827]", textSecondary: "text-[#0891b2]", accentBg: "bg-[#13b5ea]/15", accentText: "text-[#155e75]" },
  // Database
  postgresql:   { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(51,103,145,0.28),rgba(10,15,26,0.96)_58%)]", cardBg: "bg-[#0f172a]/90", cardBorder: "border-[#336791]/40", textPrimary: "text-[#e2e8f0]", textSecondary: "text-[#94a3b8]", accentBg: "bg-[#336791]/20", accentText: "text-[#7dd3fc]" },
  supabase:     { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(62,207,142,0.24),rgba(10,15,26,0.96)_58%)]", cardBg: "bg-[#1c1c1c]/90", cardBorder: "border-[#3ecf8e]/30", textPrimary: "text-[#ededed]", textSecondary: "text-[#8f8f8f]", accentBg: "bg-[#3ecf8e]/15", accentText: "text-[#3ecf8e]" },
  bigquery:     { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(66,133,244,0.24),rgba(10,15,26,0.96)_58%)]", cardBg: "bg-[#0f172a]/90", cardBorder: "border-[#4285f4]/30", textPrimary: "text-[#e2e8f0]", textSecondary: "text-[#93c5fd]", accentBg: "bg-[#4285f4]/20", accentText: "text-[#93c5fd]" },
  pinecone:     { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(0,196,154,0.24),rgba(10,15,26,0.96)_58%)]", cardBg: "bg-[#0f172a]/90", cardBorder: "border-[#00c49a]/30", textPrimary: "text-[#e2e8f0]", textSecondary: "text-[#6ee7b7]", accentBg: "bg-[#00c49a]/15", accentText: "text-[#6ee7b7]" },
  // Document
  notion:       { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(255,255,255,0.12),rgba(17,24,39,0.95)_56%)]", cardBg: "bg-white/95", cardBorder: "border-[#e5e5e5]", textPrimary: "text-[#191919]", textSecondary: "text-[#787774]", accentBg: "bg-[#e3e2df]", accentText: "text-[#37352f]" },
  confluence:   { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(0,82,204,0.24),rgba(17,24,39,0.95)_56%)]", cardBg: "bg-white/90", cardBorder: "border-[#bfdbfe]", textPrimary: "text-[#172b4d]", textSecondary: "text-[#5e6c84]", accentBg: "bg-[#0052cc]/15", accentText: "text-[#0747a6]" },
  dropbox:      { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(0,97,255,0.24),rgba(17,24,39,0.95)_56%)]", cardBg: "bg-white/90", cardBorder: "border-[#bfdbfe]", textPrimary: "text-[#1b1f23]", textSecondary: "text-[#637394]", accentBg: "bg-[#0061ff]/15", accentText: "text-[#003fac]" },
  box:          { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(0,114,198,0.24),rgba(17,24,39,0.95)_56%)]", cardBg: "bg-white/90", cardBorder: "border-[#bae6fd]", textPrimary: "text-[#111827]", textSecondary: "text-[#0369a1]", accentBg: "bg-[#0072c6]/15", accentText: "text-[#075985]" },
  docusign:     { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(255,195,0,0.22),rgba(17,24,39,0.95)_56%)]", cardBg: "bg-white/90", cardBorder: "border-[#fde68a]", textPrimary: "text-[#111827]", textSecondary: "text-[#92400e]", accentBg: "bg-[#ffc300]/15", accentText: "text-[#78350f]" },
  // Social
  twitter:      { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(29,155,240,0.24),rgba(17,24,39,0.96)_58%)]", cardBg: "bg-[#15202b]/95", cardBorder: "border-[#38444d]", textPrimary: "text-[#e7e9ea]", textSecondary: "text-[#71767b]", accentBg: "bg-[#1d9bf0]/20", accentText: "text-[#1d9bf0]" },
  linkedin:     { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(10,102,194,0.24),rgba(17,24,39,0.95)_56%)]", cardBg: "bg-white/90", cardBorder: "border-[#bfdbfe]", textPrimary: "text-[#111827]", textSecondary: "text-[#0a66c2]", accentBg: "bg-[#0a66c2]/15", accentText: "text-[#004182]" },
  youtube:      { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(255,0,0,0.22),rgba(17,24,39,0.96)_58%)]", cardBg: "bg-[#0f0f0f]/95", cardBorder: "border-[#3f3f3f]", textPrimary: "text-[#f1f1f1]", textSecondary: "text-[#aaaaaa]", accentBg: "bg-[#ff0000]/15", accentText: "text-[#ff4e45]" },
  spotify:      { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(30,215,96,0.24),rgba(10,10,10,0.96)_58%)]", cardBg: "bg-[#121212]/95", cardBorder: "border-[#282828]", textPrimary: "text-[#ffffff]", textSecondary: "text-[#b3b3b3]", accentBg: "bg-[#1ed760]/15", accentText: "text-[#1ed760]" },
  // Marketing
  mailchimp:    { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(255,225,77,0.22),rgba(17,24,39,0.95)_56%)]", cardBg: "bg-white/90", cardBorder: "border-[#fef08a]", textPrimary: "text-[#241c15]", textSecondary: "text-[#6b7280]", accentBg: "bg-[#ffe14d]/15", accentText: "text-[#78350f]" },
  webflow:      { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(67,83,255,0.24),rgba(17,24,39,0.95)_56%)]", cardBg: "bg-white/90", cardBorder: "border-[#c7d2fe]", textPrimary: "text-[#111827]", textSecondary: "text-[#4338ca]", accentBg: "bg-[#4353ff]/15", accentText: "text-[#312e81]" },
  // Cloud
  aws:          { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(255,153,0,0.22),rgba(17,24,39,0.96)_58%)]", cardBg: "bg-[#232f3e]/95", cardBorder: "border-[#ff9900]/30", textPrimary: "text-[#f2f3f3]", textSecondary: "text-[#d5dbdb]", accentBg: "bg-[#ff9900]/15", accentText: "text-[#ff9900]" },
  cloudflare:   { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(245,132,31,0.22),rgba(17,24,39,0.95)_56%)]", cardBg: "bg-white/90", cardBorder: "border-[#fed7aa]", textPrimary: "text-[#111827]", textSecondary: "text-[#ea580c]", accentBg: "bg-[#f5841f]/15", accentText: "text-[#c2410c]" },
  vercel:       { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(255,255,255,0.10),rgba(0,0,0,0.96)_58%)]", cardBg: "bg-[#0a0a0a]/95", cardBorder: "border-[#333333]", textPrimary: "text-[#ededed]", textSecondary: "text-[#888888]", accentBg: "bg-white/10", accentText: "text-white" },
  // Scheduling
  calendly:     { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(0,107,255,0.24),rgba(17,24,39,0.95)_56%)]", cardBg: "bg-white/90", cardBorder: "border-[#bfdbfe]", textPrimary: "text-[#1a1a2e]", textSecondary: "text-[#6366f1]", accentBg: "bg-[#006bff]/15", accentText: "text-[#1e3a8a]" },
  // Design
  figma:        { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(162,89,255,0.24),rgba(17,24,39,0.95)_56%)]", cardBg: "bg-white/90", cardBorder: "border-[#ddd6fe]", textPrimary: "text-[#111827]", textSecondary: "text-[#7c3aed]", accentBg: "bg-[#a259ff]/15", accentText: "text-[#5b21b6]" },
  // Developer
  github:       { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(255,255,255,0.08),rgba(13,17,23,0.96)_58%)]", cardBg: "bg-[#0d1117]/95", cardBorder: "border-[#30363d]", textPrimary: "text-[#e6edf3]", textSecondary: "text-[#8b949e]", accentBg: "bg-[#238636]/20", accentText: "text-[#3fb950]" },
  linear:       { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(98,92,255,0.24),rgba(17,24,39,0.96)_58%)]", cardBg: "bg-[#191a23]/95", cardBorder: "border-[#2e2f3e]", textPrimary: "text-[#e2e2e8]", textSecondary: "text-[#8a8f98]", accentBg: "bg-[#625cff]/20", accentText: "text-[#8b87ff]" },
  jira:         { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(0,82,204,0.24),rgba(17,24,39,0.95)_56%)]", cardBg: "bg-white/90", cardBorder: "border-[#bfdbfe]", textPrimary: "text-[#172b4d]", textSecondary: "text-[#5e6c84]", accentBg: "bg-[#0052cc]/15", accentText: "text-[#0747a6]" },
  // Project Management
  asana:        { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(246,79,89,0.22),rgba(17,24,39,0.95)_56%)]", cardBg: "bg-white/90", cardBorder: "border-[#fecaca]", textPrimary: "text-[#111827]", textSecondary: "text-[#e11d48]", accentBg: "bg-[#f64f59]/15", accentText: "text-[#9f1239]" },
  monday:       { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(108,62,208,0.24),rgba(17,24,39,0.95)_56%)]", cardBg: "bg-white/90", cardBorder: "border-[#ddd6fe]", textPrimary: "text-[#111827]", textSecondary: "text-[#7c3aed]", accentBg: "bg-[#6c3ed0]/15", accentText: "text-[#5b21b6]" },
  trello:       { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(0,121,191,0.24),rgba(17,24,39,0.95)_56%)]", cardBg: "bg-white/90", cardBorder: "border-[#bae6fd]", textPrimary: "text-[#172b4d]", textSecondary: "text-[#5e6c84]", accentBg: "bg-[#0079bf]/15", accentText: "text-[#0c4a6e]" },
  // Automation
  zapier_webhooks: { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(255,74,35,0.22),rgba(17,24,39,0.95)_56%)]", cardBg: "bg-white/90", cardBorder: "border-[#fed7aa]", textPrimary: "text-[#111827]", textSecondary: "text-[#ea580c]", accentBg: "bg-[#ff4a23]/15", accentText: "text-[#9a3412]" },
  make:         { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(108,43,217,0.24),rgba(17,24,39,0.95)_56%)]", cardBg: "bg-white/90", cardBorder: "border-[#ddd6fe]", textPrimary: "text-[#111827]", textSecondary: "text-[#7c3aed]", accentBg: "bg-[#6c2bd9]/15", accentText: "text-[#5b21b6]" },
  // AI
  openai:       { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(116,204,183,0.20),rgba(17,24,39,0.96)_58%)]", cardBg: "bg-[#343541]/95", cardBorder: "border-[#565869]", textPrimary: "text-[#ececf1]", textSecondary: "text-[#acacbe]", accentBg: "bg-[#10a37f]/15", accentText: "text-[#10a37f]" },
  // Search
  brave_search: { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(251,84,43,0.22),rgba(17,24,39,0.95)_56%)]", cardBg: "bg-white/90", cardBorder: "border-[#fed7aa]", textPrimary: "text-[#111827]", textSecondary: "text-[#ea580c]", accentBg: "bg-[#fb542b]/15", accentText: "text-[#9a3412]" },
  bing_search:  { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(0,120,212,0.24),rgba(17,24,39,0.95)_56%)]", cardBg: "bg-white/90", cardBorder: "border-[#bae6fd]", textPrimary: "text-[#111827]", textSecondary: "text-[#0284c7]", accentBg: "bg-[#0078d4]/15", accentText: "text-[#075985]" },
  // Google extras
  google_analytics: { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(245,171,53,0.22),rgba(17,24,39,0.95)_56%)]", cardBg: "bg-white/90", cardBorder: "border-[#fde68a]", textPrimary: "text-[#111827]", textSecondary: "text-[#b45309]", accentBg: "bg-[#f5ab35]/15", accentText: "text-[#92400e]" },
  google_ads:   { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(66,133,244,0.24),rgba(17,24,39,0.95)_56%)]", cardBg: "bg-white/90", cardBorder: "border-[#bfdbfe]", textPrimary: "text-[#111827]", textSecondary: "text-[#1d4ed8]", accentBg: "bg-[#4285f4]/15", accentText: "text-[#1e3a8a]" },
  google_maps:  { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(52,168,83,0.24),rgba(17,24,39,0.95)_56%)]", cardBg: "bg-white/90", cardBorder: "border-[#bbf7d0]", textPrimary: "text-[#111827]", textSecondary: "text-[#15803d]", accentBg: "bg-[#34a853]/15", accentText: "text-[#166534]" },
  google_calendar: { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(66,133,244,0.24),rgba(17,24,39,0.95)_56%)]", cardBg: "bg-white/90", cardBorder: "border-[#bfdbfe]", textPrimary: "text-[#111827]", textSecondary: "text-[#1d4ed8]", accentBg: "bg-[#4285f4]/15", accentText: "text-[#1e3a8a]" },
  // Misc
  invoice:      { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(107,114,128,0.22),rgba(17,24,39,0.95)_56%)]", cardBg: "bg-white/90", cardBorder: "border-[#d1d5db]", textPrimary: "text-[#111827]", textSecondary: "text-[#6b7280]", accentBg: "bg-[#6b7280]/15", accentText: "text-[#374151]" },
  reddit:       { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(255,69,0,0.22),rgba(17,24,39,0.95)_56%)]", cardBg: "bg-white/90", cardBorder: "border-[#fed7aa]", textPrimary: "text-[#111827]", textSecondary: "text-[#ea580c]", accentBg: "bg-[#ff4500]/15", accentText: "text-[#9a3412]" },
  newsapi:      { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(29,78,216,0.24),rgba(17,24,39,0.95)_56%)]", cardBg: "bg-white/90", cardBorder: "border-[#bfdbfe]", textPrimary: "text-[#111827]", textSecondary: "text-[#1d4ed8]", accentBg: "bg-[#1d4ed8]/15", accentText: "text-[#1e3a8a]" },
  sec_edgar:    { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(0,51,102,0.28),rgba(17,24,39,0.95)_56%)]", cardBg: "bg-white/90", cardBorder: "border-[#bfdbfe]", textPrimary: "text-[#003366]", textSecondary: "text-[#0369a1]", accentBg: "bg-[#003366]/15", accentText: "text-[#003366]" },
  page_monitor: { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(107,114,128,0.22),rgba(17,24,39,0.95)_56%)]", cardBg: "bg-white/90", cardBorder: "border-[#d1d5db]", textPrimary: "text-[#111827]", textSecondary: "text-[#6b7280]", accentBg: "bg-[#6b7280]/15", accentText: "text-[#374151]" },
  email_validation: { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(16,185,129,0.24),rgba(17,24,39,0.95)_56%)]", cardBg: "bg-white/90", cardBorder: "border-[#a7f3d0]", textPrimary: "text-[#111827]", textSecondary: "text-[#059669]", accentBg: "bg-[#10b981]/15", accentText: "text-[#065f46]" },
  http_request: { shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(107,114,128,0.22),rgba(17,24,39,0.95)_56%)]", cardBg: "bg-white/90", cardBorder: "border-[#d1d5db]", textPrimary: "text-[#111827]", textSecondary: "text-[#6b7280]", accentBg: "bg-[#6b7280]/15", accentText: "text-[#374151]" },
};

// ── Descriptors ──────────────────────────────────────────────────────────────
const DESCRIPTORS: Record<SkinVariant, SkinDescriptor> = {
  // Email
  gmail:        { brand: "Gmail",          theatreLabel: "Mail",        objectLabel: "Thread",      actionVerb: "Composing email" },
  outlook:      { brand: "Outlook",        theatreLabel: "Mailbox",     objectLabel: "Message",     actionVerb: "Processing mailbox" },
  // Chat
  slack:        { brand: "Slack",          theatreLabel: "Channel",     objectLabel: "Message",     actionVerb: "Publishing message" },
  discord:      { brand: "Discord",        theatreLabel: "Server",      objectLabel: "Message",     actionVerb: "Posting to channel" },
  microsoft_teams: { brand: "Teams",       theatreLabel: "Channel",     objectLabel: "Message",     actionVerb: "Sending to Teams" },
  twilio:       { brand: "Twilio",         theatreLabel: "Messaging",   objectLabel: "SMS",         actionVerb: "Sending message" },
  // Sheet
  sheets:       { brand: "Google Sheets",  theatreLabel: "Spreadsheet", objectLabel: "Row",         actionVerb: "Updating cells" },
  excel:        { brand: "Excel",          theatreLabel: "Workbook",    objectLabel: "Row",         actionVerb: "Updating workbook" },
  airtable:     { brand: "Airtable",       theatreLabel: "Base",        objectLabel: "Record",      actionVerb: "Updating record" },
  // CRM
  salesforce:   { brand: "Salesforce",     theatreLabel: "CRM",         objectLabel: "Record",      actionVerb: "Updating CRM" },
  hubspot:      { brand: "HubSpot",        theatreLabel: "CRM",         objectLabel: "Contact",     actionVerb: "Managing contacts" },
  // Support
  zendesk:      { brand: "Zendesk",        theatreLabel: "Support",     objectLabel: "Ticket",      actionVerb: "Processing ticket" },
  intercom:     { brand: "Intercom",       theatreLabel: "Messenger",   objectLabel: "Conversation",actionVerb: "Handling conversation" },
  // Commerce
  stripe:       { brand: "Stripe",         theatreLabel: "Payments",    objectLabel: "Transaction", actionVerb: "Processing payment" },
  shopify:      { brand: "Shopify",        theatreLabel: "Store",       objectLabel: "Order",       actionVerb: "Managing order" },
  sap:          { brand: "SAP",            theatreLabel: "ERP",         objectLabel: "Document",    actionVerb: "Processing transaction" },
  quickbooks:   { brand: "QuickBooks",     theatreLabel: "Accounting",  objectLabel: "Invoice",     actionVerb: "Managing finances" },
  xero:         { brand: "Xero",           theatreLabel: "Accounting",  objectLabel: "Invoice",     actionVerb: "Processing accounts" },
  // Database
  postgresql:   { brand: "PostgreSQL",     theatreLabel: "Database",    objectLabel: "Query",       actionVerb: "Executing query" },
  supabase:     { brand: "Supabase",       theatreLabel: "Database",    objectLabel: "Row",         actionVerb: "Querying database" },
  bigquery:     { brand: "BigQuery",       theatreLabel: "Warehouse",   objectLabel: "Query",       actionVerb: "Running analysis" },
  pinecone:     { brand: "Pinecone",       theatreLabel: "Vector DB",   objectLabel: "Vector",      actionVerb: "Searching vectors" },
  // Document
  notion:       { brand: "Notion",         theatreLabel: "Workspace",   objectLabel: "Page",        actionVerb: "Editing page" },
  confluence:   { brand: "Confluence",     theatreLabel: "Wiki",        objectLabel: "Page",        actionVerb: "Updating wiki" },
  dropbox:      { brand: "Dropbox",        theatreLabel: "Storage",     objectLabel: "File",        actionVerb: "Managing files" },
  box:          { brand: "Box",            theatreLabel: "Storage",     objectLabel: "File",        actionVerb: "Managing files" },
  docusign:     { brand: "DocuSign",       theatreLabel: "Signing",     objectLabel: "Envelope",    actionVerb: "Processing signature" },
  // Social
  twitter:      { brand: "X",             theatreLabel: "Feed",        objectLabel: "Tweet",       actionVerb: "Posting content" },
  linkedin:     { brand: "LinkedIn",       theatreLabel: "Network",     objectLabel: "Post",        actionVerb: "Publishing update" },
  youtube:      { brand: "YouTube",        theatreLabel: "Channel",     objectLabel: "Video",       actionVerb: "Analysing content" },
  spotify:      { brand: "Spotify",        theatreLabel: "Player",      objectLabel: "Track",       actionVerb: "Curating music" },
  // Marketing
  mailchimp:    { brand: "Mailchimp",      theatreLabel: "Campaigns",   objectLabel: "Campaign",    actionVerb: "Managing campaign" },
  webflow:      { brand: "Webflow",        theatreLabel: "CMS",         objectLabel: "Item",        actionVerb: "Publishing content" },
  // Cloud
  aws:          { brand: "AWS",            theatreLabel: "Console",     objectLabel: "Resource",    actionVerb: "Managing infrastructure" },
  cloudflare:   { brand: "Cloudflare",     theatreLabel: "Dashboard",   objectLabel: "Zone",        actionVerb: "Configuring network" },
  vercel:       { brand: "Vercel",         theatreLabel: "Platform",    objectLabel: "Deployment",  actionVerb: "Managing deployment" },
  // Scheduling
  calendly:     { brand: "Calendly",       theatreLabel: "Scheduling",  objectLabel: "Event",       actionVerb: "Managing schedule" },
  // Design
  figma:        { brand: "Figma",          theatreLabel: "Canvas",      objectLabel: "Frame",       actionVerb: "Reviewing design" },
  // Developer
  github:       { brand: "GitHub",         theatreLabel: "Repository",  objectLabel: "Issue",       actionVerb: "Managing repo" },
  linear:       { brand: "Linear",         theatreLabel: "Tracker",     objectLabel: "Issue",       actionVerb: "Updating issue" },
  jira:         { brand: "Jira",           theatreLabel: "Board",       objectLabel: "Issue",       actionVerb: "Processing issue" },
  // Project Management
  asana:        { brand: "Asana",          theatreLabel: "Project",     objectLabel: "Task",        actionVerb: "Managing task" },
  monday:       { brand: "Monday.com",     theatreLabel: "Board",       objectLabel: "Item",        actionVerb: "Updating board" },
  trello:       { brand: "Trello",         theatreLabel: "Board",       objectLabel: "Card",        actionVerb: "Moving card" },
  // Automation
  zapier_webhooks: { brand: "Zapier",      theatreLabel: "Automation",  objectLabel: "Zap",         actionVerb: "Triggering workflow" },
  make:         { brand: "Make",           theatreLabel: "Automation",  objectLabel: "Scenario",    actionVerb: "Running scenario" },
  // AI
  openai:       { brand: "OpenAI",         theatreLabel: "AI Studio",   objectLabel: "Completion",  actionVerb: "Generating response" },
  // Search
  brave_search: { brand: "Brave Search",   theatreLabel: "Search",      objectLabel: "Results",     actionVerb: "Searching web" },
  bing_search:  { brand: "Bing",           theatreLabel: "Search",      objectLabel: "Results",     actionVerb: "Searching web" },
  // Google extras
  google_analytics: { brand: "Analytics",  theatreLabel: "Analytics",   objectLabel: "Report",      actionVerb: "Pulling metrics" },
  google_ads:   { brand: "Google Ads",     theatreLabel: "Ads",         objectLabel: "Campaign",    actionVerb: "Managing campaign" },
  google_maps:  { brand: "Google Maps",    theatreLabel: "Maps",        objectLabel: "Place",       actionVerb: "Looking up location" },
  google_calendar: { brand: "Calendar",    theatreLabel: "Calendar",    objectLabel: "Event",       actionVerb: "Managing event" },
  // Misc
  invoice:      { brand: "Invoice",        theatreLabel: "Billing",     objectLabel: "Invoice",     actionVerb: "Processing invoice" },
  reddit:       { brand: "Reddit",         theatreLabel: "Forum",       objectLabel: "Post",        actionVerb: "Searching posts" },
  newsapi:      { brand: "NewsAPI",        theatreLabel: "News",        objectLabel: "Article",     actionVerb: "Fetching news" },
  sec_edgar:    { brand: "SEC EDGAR",      theatreLabel: "Filings",     objectLabel: "Filing",      actionVerb: "Retrieving filings" },
  page_monitor: { brand: "Page Monitor",   theatreLabel: "Monitor",     objectLabel: "URL",         actionVerb: "Checking changes" },
  email_validation: { brand: "Email Check",theatreLabel: "Validation",  objectLabel: "Email",       actionVerb: "Validating email" },
  http_request: { brand: "HTTP",           theatreLabel: "API",         objectLabel: "Request",     actionVerb: "Making request" },
};

// ── Scene family to default variant ──────────────────────────────────────────
const SCENE_FAMILY_TO_VARIANT: Record<string, SkinVariant> = {
  email: "gmail",
  browser: "brave_search",
  chat: "slack",
  sheet: "sheets",
  crm: "salesforce",
  support: "zendesk",
  commerce: "stripe",
  database: "postgresql",
  document: "notion",
  social: "twitter",
  marketing: "mailchimp",
  cloud: "aws",
  scheduling: "calendly",
  design: "figma",
  api: "github",
};

// ── Brand slug to variant (direct lookup) ────────────────────────────────────
const BRAND_SLUG_TO_VARIANT: Record<string, SkinVariant> = Object.fromEntries(
  (Object.keys(PALETTES) as SkinVariant[]).map((key) => [key, key]),
) as Record<string, SkinVariant>;

// Additional aliases
Object.assign(BRAND_SLUG_TO_VARIANT, {
  bing: "bing_search",
  brave: "brave_search",
  google_sheets: "sheets",
  google_drive: "notion",
  google_docs: "notion",
  google_cloud: "aws",
  google_workspace: "sheets",
  http: "http_request",
  microsoft_365: "outlook",
  microsoft_calendar: "outlook",
  onedrive: "outlook",
  word: "outlook",
  teams: "microsoft_teams",
  zapier: "zapier_webhooks",
  integromat: "make",
  browser: "brave_search",
  x: "twitter",
});

function resolveSkinVariant(brandSlug: string, sceneFamily: string): SkinVariant | null {
  const slug = (brandSlug || "").trim().toLowerCase();
  if (slug && BRAND_SLUG_TO_VARIANT[slug]) {
    return BRAND_SLUG_TO_VARIANT[slug];
  }
  const family = (sceneFamily || "").trim().toLowerCase();
  if (family && SCENE_FAMILY_TO_VARIANT[family]) {
    return SCENE_FAMILY_TO_VARIANT[family];
  }
  return null;
}

function getPalette(variant: SkinVariant): SkinPalette {
  return PALETTES[variant];
}

function getDescriptor(variant: SkinVariant): SkinDescriptor {
  return DESCRIPTORS[variant];
}

export type { SkinVariant };
export { BRAND_SLUG_TO_VARIANT, DESCRIPTORS, PALETTES, SCENE_FAMILY_TO_VARIANT, getDescriptor, getPalette, resolveSkinVariant };
