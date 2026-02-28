import type { MouseEvent as ReactMouseEvent } from "react";

type ResizeHandleProps = {
  side: "left" | "right";
  active: boolean;
  onMouseDown: (event: ReactMouseEvent<HTMLDivElement>) => void;
};

export function ResizeHandle({ side, active, onMouseDown }: ResizeHandleProps) {
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={side === "left" ? "Resize left panel" : "Resize right panel"}
      onMouseDown={onMouseDown}
      className={`group relative w-2 shrink-0 cursor-col-resize transition-colors ${
        active ? "bg-[#2f2f34]/15" : "hover:bg-[#2f2f34]/10"
      }`}
    >
      <div className="absolute left-1/2 top-1/2 h-12 w-[2px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-black/10 group-hover:bg-[#2f2f34]/60" />
    </div>
  );
}
