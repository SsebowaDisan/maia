import type { CanvasDocumentRecord, MessageBlock } from "../../messageBlocks";
import { BlockRenderer } from "./BlockRenderer";
import { WidgetRenderBoundary } from "./WidgetRenderBoundary";

type MessageBlocksProps = {
  blocks: MessageBlock[];
  documents?: CanvasDocumentRecord[];
};

function messageBlockKey(block: MessageBlock, index: number): string {
  if (block.type === "document_action") {
    return `${block.type}:${block.action.documentId}:${index}`;
  }
  if (block.type === "widget") {
    return `${block.type}:${block.widget.kind}:${index}`;
  }
  if (block.type === "chart") {
    return `${block.type}:${String(block.plot?.title || "")}:${index}`;
  }
  return `${block.type}:${index}`;
}

function MessageBlocks({ blocks, documents = [] }: MessageBlocksProps) {
  if (!blocks.length) {
    return null;
  }

  return (
    <div className="space-y-3">
      {blocks.map((block, index) => (
        <WidgetRenderBoundary
          key={messageBlockKey(block, index)}
          fallback={
            <div className="rounded-2xl border border-[#fecaca] bg-[#fff1f2] px-4 py-3 text-[12px] text-[#9f1239]">
              This message block failed to render.
            </div>
          }
        >
          <BlockRenderer block={block} documents={documents} />
        </WidgetRenderBoundary>
      ))}
    </div>
  );
}

export { MessageBlocks };
