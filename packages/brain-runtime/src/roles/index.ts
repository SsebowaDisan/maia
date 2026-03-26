/**
 * Role catalog â€” 27 agent roles, each in its own file.
 */

export type { RoleDefinition, PersonalityProfile, AgentRole } from "./types";

import { analyst } from "./analyst";
import { browser } from "./browser";
import { business_analyst } from "./business_analyst";
import { coder } from "./coder";
import { customer_support } from "./customer_support";
import { data_scientist } from "./data_scientist";
import { delivery } from "./delivery";
import { designer } from "./designer";
import { devops } from "./devops";
import { document_reader } from "./document_reader";
import { email_specialist } from "./email_specialist";
import { finance } from "./finance";
import { it_infrastructure } from "./it_infrastructure";
import { legal } from "./legal";
import { marketing } from "./marketing";
import { product_manager } from "./product_manager";
import { project_manager } from "./project_manager";
import { project_sponsor } from "./project_sponsor";
import { qa_tester } from "./qa_tester";
import { researcher } from "./researcher";
import { reviewer } from "./reviewer";
import { sales } from "./sales";
import { security_auditor } from "./security_auditor";
import { supervisor } from "./supervisor";
import { tech_lead } from "./tech_lead";
import { translator } from "./translator";
import { writer } from "./writer";

/** All 27 roles indexed by ID. */
export const ROLE_CATALOG: Record<string, import("./types").AgentRole> = {
  analyst,
  browser,
  business_analyst,
  coder,
  customer_support,
  data_scientist,
  delivery,
  designer,
  devops,
  document_reader,
  email_specialist,
  finance,
  it_infrastructure,
  legal,
  marketing,
  product_manager,
  project_manager,
  project_sponsor,
  qa_tester,
  researcher,
  reviewer,
  sales,
  security_auditor,
  supervisor,
  tech_lead,
  translator,
  writer,
};

/** Get a role by ID, with fallback to researcher. */
export function getRole(roleId: string): import("./types").AgentRole {
  return ROLE_CATALOG[roleId] ?? ROLE_CATALOG.researcher;
}

/** Get all role definitions. */
export function getAllRoles(): import("./types").AgentRole[] {
  return Object.values(ROLE_CATALOG);
}

/** Infer the best role from a step description. */
export function inferRole(description: string): string {
  const lower = description.toLowerCase();
  if (/(sponsor|vision|go.no.go|strategic align|budget approv)/.test(lower)) return "project_sponsor";
  if (/(business analys|acceptance criteria|process map|stakeholder need)/.test(lower)) return "business_analyst";
  if (/(project manag|scrum|sprint|milestone|timeline|blocker|standup)/.test(lower)) return "project_manager";
  if (/(tech lead|architect|system design|tech stack|technical decision)/.test(lower)) return "tech_lead";
  if (/(devops|deploy|pipeline|ci.cd|docker|kubernetes)/.test(lower)) return "devops";
  if (/(server|dns|ssl|firewall|sysadmin|infrastructure|network)/.test(lower)) return "it_infrastructure";
  if (/(marketing|campaign|brand|seo|content marketing|growth|funnel)/.test(lower)) return "marketing";
  if (/(code|implement|debug|fix bug|program|function|class)/.test(lower)) return "coder";
  if (/(model|ml|machine learning|statistic|regression|predict)/.test(lower)) return "data_scientist";
  if (/(design|ui|ux|wireframe|layout|mockup)/.test(lower)) return "designer";
  if (/(prioriti|user stor|requirement|product|feature|mvp)/.test(lower)) return "product_manager";
  if (/(test|qa|edge case|bug|regression|reproduce)/.test(lower)) return "qa_tester";
  if (/(secur|vulnerab|audit|compliance|encrypt|penetr)/.test(lower)) return "security_auditor";
  if (/(translat|locali|language|multilingual)/.test(lower)) return "translator";
  if (/(support|ticket|customer|helpdesk|escalat)/.test(lower)) return "customer_support";
  if (/(sales|lead|prospect|outreach|pipeline|deal)/.test(lower)) return "sales";
  if (/(budget|invoice|forecast|financ|expense|p&l|margin)/.test(lower)) return "finance";
  if (/(legal|contract|clause|compliance|liabil|regulat)/.test(lower)) return "legal";
  if (/(search|find|look up|research|gather)/.test(lower)) return "researcher";
  if (/(browse|navigate|website|click|scrape)/.test(lower)) return "browser";
  if (/(read|extract|document|pdf|file|parse)/.test(lower)) return "document_reader";
  if (/(analy|compar|metric|data|calculat|number)/.test(lower)) return "analyst";
  if (/(review|check|verify|validate|quality)/.test(lower)) return "reviewer";
  if (/(write|draft|report|summar|compose)/.test(lower)) return "writer";
  if (/(email|send email|mail|inbox)/.test(lower)) return "email_specialist";
  if (/(deliver|publish|send|dispatch|deploy)/.test(lower)) return "delivery";
  if (/(supervise|coordinate|manage|gate|approve)/.test(lower)) return "supervisor";
  return "researcher";
}

/** Format the role catalog for LLM prompts. */
export function formatRoleCatalogForPrompt(): string {
  return getAllRoles()
    .map((r) => `- ${r.role.id}: ${r.role.name} - ${r.role.description}`)
    .join("\n");
}

/** Build a personality instruction for an agent's system prompt. */
export function personalityPrompt(roleId: string): string {
  const r = ROLE_CATALOG[roleId];
  if (!r) return "";
  const p = r.personality;
  return (
    "\n\nYour communication style:\n"
    + `- Keep messages under ${p.maxWords} words. Shorter is better.\n`
    + `- Be ${p.directness > 0.7 ? "direct and blunt" : "measured and diplomatic"}.\n`
    + `- When you disagree: ${p.disagreementStyle}\n`
    + `- When you agree: ${p.agreementStyle}\n`
    + `- For quick exchanges, respond with just: "${p.quickResponse}"`
  );
}
