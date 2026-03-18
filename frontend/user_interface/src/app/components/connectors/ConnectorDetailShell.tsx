import type { ReactNode } from "react";

type ConnectorDetailShellProps = {
  header: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
};

export function ConnectorDetailShell({
  header,
  children,
  footer,
}: ConnectorDetailShellProps) {
  return (
    <div className="fixed inset-0 z-[120] bg-black/30 backdrop-blur-[2px]">
      <div className="absolute inset-y-0 right-0 w-full max-w-[480px] border-l border-black/[0.08] bg-white shadow-[-30px_0_64px_rgba(15,23,42,0.24)]">
        <div className="flex h-full flex-col">
          {header}
          <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">{children}</div>
          {footer ? (
            <div className="border-t border-black/[0.08] bg-white px-5 py-4">{footer}</div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
