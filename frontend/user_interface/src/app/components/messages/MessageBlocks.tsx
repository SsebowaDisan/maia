import type { CanvasDocumentRecord, MessageBlock } from "../../messageBlocks";
import { BlockRenderer } from "./BlockRenderer";

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
  return `${block.type}:${index}`;
}

function MessageBlocks({ blocks, documents = [] }: MessageBlocksProps) {
  if (!blocks.length) {
    return null;
  }

  return (
    <div className="space-y-3">
      {blocks.map((block, index) => (
        <BlockRenderer
          key={messageBlockKey(block, index)}
          block={block}
          documents={documents}
        />
      ))}
    </div>
  );
}

export { MessageBlocks };
