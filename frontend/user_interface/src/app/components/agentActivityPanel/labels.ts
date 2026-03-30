function desktopStatusForEventType(eventType: string, streaming: boolean): string {
  if (eventType === "desktop_starting") {
    return "Starting secure agent desktop";
  }
  if (eventType === "desktop_ready") {
    return "Desktop live. Beginning execution.";
  }
  if (eventType === "response_writing") {
    return "Writing response while tools and evidence remain visible";
  }
  if (streaming) {
    return "Desktop session is running live";
  }
  return "Desktop replay";
}

function cursorLabelForEventType(type: string): string {
  if (type === "planning_started") return "Planning search strategy";
  if (type === "plan_candidate" || type === "plan_refined") return "Preparing roadmap";
  if (type === "document_opened") return "Open file";
  if (type === "document_scanned") return "Scanning page";
  if (type === "highlights_detected") return "Highlighting";
  if (type === "response_writing") return "Writing";
  if (type === "browser_open") return "Opening browser";
  if (type === "browser_contact_form_detected") return "Detecting contact form";
  if (type === "browser_contact_required_scan") return "Checking required fields";
  if (type === "browser_contact_fill_name") return "Typing name";
  if (type === "browser_contact_fill_email") return "Typing email";
  if (type === "browser_contact_fill_company") return "Typing company";
  if (type === "browser_contact_fill_phone") return "Typing phone";
  if (type === "browser_contact_fill_subject") return "Typing subject";
  if (type === "browser_contact_fill_message") return "Typing message";
  if (type === "browser_contact_llm_fill") return "Typing mapped field";
  if (type === "llm.form_field_mapping") return "Resolving fields with LLM";
  if (type === "browser_contact_submit") return "Submitting form";
  if (type === "browser_contact_confirmation") return "Checking confirmation";
  if (type === "browser_human_verification_required") return "Waiting for human verification";
  if (type === "browser_cookie_accept") return "Accepting cookies";
  if (type === "browser_cookie_check") return "Checking cookie banner";
  if (type === "browser_hover") return "Hovering element";
  if (type === "browser_click") return "Clicking element";
  if (type === "browser_trusted_site_mode") return "Applying trusted-site policy";
  if (type === "browser_keyword_highlight") return "Highlighting keywords";
  if (type === "browser_find_in_page") return "Searching within page";
  if (type === "browser_copy_selection") return "Copying excerpt";
  if (type === "doc_copy_clipboard") return "Copying note";
  if (type === "doc_open") return "Opening docs notebook";
  if (type === "doc_type_text") return "Writing docs note";
  if (type === "doc_paste_clipboard") return "Pasting content";
  if (type === "doc_save") return "Saving docs note";
  if (type === "docs.create_started") return "Creating Google Doc";
  if (type === "docs.create_completed") return "Doc created";
  if (type === "docs.insert_started") return "Writing to doc";
  if (type === "docs.insert_completed") return "Doc updated";
  if (type === "sheets.create_started") return "Creating tracker sheet";
  if (type === "sheets.create_completed") return "Sheet created";
  if (type === "sheets.append_started") return "Appending sheet rows";
  if (type === "sheets.append_completed") return "Rows saved";
  if (type === "drive.go_to_doc") return "Opening doc link";
  if (type === "drive.go_to_sheet") return "Opening sheet link";
  if (type === "llm.context_summary") return "Summarizing context";
  if (type === "llm.task_rewrite_started") return "Writing todo";
  if (type === "llm.task_rewrite_completed") return "Todo ready";
  if (type === "llm.task_contract_started") return "Preparing checklist";
  if (type === "llm.task_contract_completed") return "Checklist ready";
  if (type === "llm.clarification_requested") return "Requesting clarification";
  if (type === "llm.clarification_resolved") return "Clarification resolved";
  if (type === "llm.plan_decompose_started") return "Breaking into steps";
  if (type === "llm.plan_decompose_completed") return "Step decomposition ready";
  if (type === "llm.plan_step") return "Publishing plan step";
  if (type === "llm.location_brief") return "Synthesizing location answer";
  if (type === "llm.intent_tags") return "Classifying intent";
  if (type === "llm.step_summary") return "Summarizing step";
  if (type === "browser_navigate" || type === "web_search_started") return "Navigating";
  if (type === "sheet_open") return "Opening tracker";
  if (type === "pdf_open") return "Opening PDF";
  if (type === "pdf_page_change") return "Turning PDF page";
  if (type === "pdf_scan_region") return "Scanning PDF region";
  if (type === "pdf_evidence_linked") return "Linking PDF evidence";
  if (type === "sheet_cell_update") return "Updating cells";
  if (type === "sheet_append_row") return "Appending row";
  if (type === "sheet_save") return "Saving tracker";
  if (type === "email_set_body" || type === "email_type_body") return "Typing email";
  if (type === "email_auth_required") return "Awaiting sign in";
  if (type === "email_click_send") return "Clicking send";
  if (type === "email_sent") return "Send complete";
  if (type === "web_result_opened") return "Opening source";
  return "Empowered by Axon Group";
}

export { cursorLabelForEventType, desktopStatusForEventType };
