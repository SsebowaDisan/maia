import type { SkinProps } from "./skinTypes";
import { ApprovalBanner, FieldDiffsList, SkinHeader, SkinShell, ToolParamsPreview, ValidationBadges } from "./shared";

/** GitHub / Jira / Linear / Asana / Monday / Trello — issue/task card. */
function ProjectSkin({ state, palette, descriptor, activeTitle }: SkinProps) {
  const data = state.toolParams ?? {};
  const title = activeTitle || state.operationLabel || descriptor.actionVerb;
  const issueKey = String(data["issue_key"] || data["issue_id"] || data["task_id"] || data["card_id"] || state.objectId || "—");
  const issueSummary = String(data["summary"] || data["title"] || data["name"] || state.objectType || "Issue");
  const issueStatus = String(data["status"] || data["transition"] || data["completed"] || "Open");
  const assignee = String(data["assignee"] || data["assignee_id"] || "Unassigned");
  const priority = String(data["priority"] || "Medium");

  return (
    <SkinShell palette={palette}>
      <SkinHeader palette={palette} descriptor={descriptor} title={title} status={state.statusLabel} />

      {/* Issue card */}
      <div className={`rounded-xl border ${palette.cardBorder} bg-white/60 p-4`}>
        <div className="flex items-start gap-3">
          <span className={`shrink-0 rounded-md ${palette.accentBg} px-2 py-1 font-mono text-[12px] font-bold ${palette.accentText}`}>
            {issueKey}
          </span>
          <div className="min-w-0 flex-1">
            <h4 className={`text-[15px] font-semibold ${palette.textPrimary}`}>{issueSummary}</h4>
            <div className={`mt-2 flex flex-wrap items-center gap-3 text-[12px] ${palette.textSecondary}`}>
              <span className={`rounded-full border ${palette.cardBorder} px-2 py-0.5`}>{issueStatus}</span>
              <span>👤 {assignee}</span>
              <span className={`rounded-full ${palette.accentBg} px-2 py-0.5 ${palette.accentText}`}>{priority}</span>
            </div>
          </div>
        </div>

        {data["description"] || data["body"] || data["notes"] ? (
          <p className={`mt-3 whitespace-pre-wrap border-t border-black/5 pt-3 text-[13px] leading-relaxed ${palette.textPrimary}`}>
            {String(data["description"] || data["body"] || data["notes"]).slice(0, 300)}
          </p>
        ) : null}
      </div>

      <ToolParamsPreview
        data={data}
        palette={palette}
        fields={[
          { key: "issue_type", label: "Type" },
          { key: "labels", label: "Labels" },
          { key: "due_date", label: "Due date" },
          { key: "sprint", label: "Sprint" },
        ]}
      />

      <FieldDiffsList diffs={state.fieldDiffs} palette={palette} />
      <ValidationBadges validations={state.validations} />
      <ApprovalBanner state={state} />
    </SkinShell>
  );
}

export { ProjectSkin };
