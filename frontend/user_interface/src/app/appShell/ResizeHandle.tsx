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
      className="group relative -mx-1 w-2 shrink-0 cursor-col-resize bg-transparent z-10"
    >
      <div
        className={`absolute left-1/2 top-1/2 h-12 w-[1px] -translate-x-1/2 -translate-y-1/2 rounded-full transition-opacity ${
          active
            ? "opacity-55 bg-[#34353a]"
            : "opacity-0 bg-[#34353a] group-hover:opacity-30"
        }`}
      />
    </div>
  );
}
