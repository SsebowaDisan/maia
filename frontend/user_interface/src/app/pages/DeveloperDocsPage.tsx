import { useState } from "react";
import { toast } from "sonner";

import { renderRichText } from "../utils/richText";

const DOCS_MD = `
# Connector SDK Quickstart

Use \`ConnectorBase\` to define your integration and expose tools with typed parameters.

## Install
\`\`\`bash
pip install maia-connector-sdk
\`\`\`

## Minimal Example
\`\`\`python
from maia_connector_sdk import ConnectorBase, tool

class ExampleConnector(ConnectorBase):
    def definition(self):
        return {
            "connector_id": "example_api",
            "name": "Example API",
            "auth_type": "api_key",
        }

    @tool("example.read")
    def read(self, resource_id: str):
        return {"resource_id": resource_id, "status": "ok"}
\`\`\`
`;

export function DeveloperDocsPage() {
  const [copied, setCopied] = useState(false);
  const html = renderRichText(DOCS_MD);

  const copyDocs = async () => {
    await navigator.clipboard.writeText(DOCS_MD);
    setCopied(true);
    toast.success("SDK example copied.");
    window.setTimeout(() => setCopied(false), 1200);
  };

  return (
    <div className="h-full overflow-y-auto bg-[#f6f6f7] p-5">
      <div className="mx-auto max-w-[1100px] space-y-4">
        <section className="rounded-[28px] border border-black/[0.08] bg-white px-6 py-5">
          <p className="text-[12px] font-semibold uppercase tracking-[0.16em] text-[#667085]">Developer docs</p>
          <h1 className="mt-1 text-[32px] font-semibold tracking-[-0.02em] text-[#101828]">Connector SDK documentation</h1>
          <div className="mt-4 flex items-center gap-2">
            <button
              type="button"
              onClick={() => void copyDocs()}
              className="rounded-full border border-black/[0.12] bg-white px-4 py-2 text-[12px] font-semibold text-[#344054]"
            >
              {copied ? "Copied" : "Copy example"}
            </button>
            <a
              href="https://replit.com/"
              target="_blank"
              rel="noreferrer"
              className="rounded-full bg-[#7c3aed] px-4 py-2 text-[12px] font-semibold text-white"
            >
              Open in sandbox
            </a>
          </div>
        </section>

        <section className="rounded-2xl border border-black/[0.08] bg-white p-5">
          <div
            className="chat-answer-html assistantAnswerBody"
            dangerouslySetInnerHTML={{ __html: html }}
          />
        </section>
      </div>
    </div>
  );
}

