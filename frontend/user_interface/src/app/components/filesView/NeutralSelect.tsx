import { useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import type { SelectOption } from "./types";

interface NeutralSelectProps {
  value: string;
  options: SelectOption[];
  placeholder: string;
  disabled?: boolean;
  buttonClassName: string;
  menuClassName?: string;
  onChange: (value: string) => void;
}

function NeutralSelect({
  value,
  options,
  placeholder,
  disabled = false,
  buttonClassName,
  menuClassName,
  onChange,
}: NeutralSelectProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    window.addEventListener("mousedown", onPointerDown);
    return () => window.removeEventListener("mousedown", onPointerDown);
  }, [open]);

  useEffect(() => {
    if (disabled) {
      setOpen(false);
    }
  }, [disabled]);

  const selectedOption = options.find((option) => option.value === value);
  const displayText = selectedOption?.label || placeholder;

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => {
          if (!disabled) {
            setOpen((previous) => !previous);
          }
        }}
        disabled={disabled}
        className={`${buttonClassName} inline-flex items-center justify-between gap-2 disabled:opacity-45`}
      >
        <span className="truncate">{displayText}</span>
        <ChevronDown
          className={`h-3.5 w-3.5 text-[#6e6e73] transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open ? (
        <div
          className={`absolute z-20 mt-1 max-h-56 overflow-auto rounded-xl border border-black/[0.08] bg-white p-1 shadow-[0_12px_28px_rgba(0,0,0,0.12)] ${menuClassName || "left-0 right-0"}`}
        >
          {options.length ? (
            options.map((option) => {
              const isActive = option.value === value;
              return (
                <button
                  key={option.value || "__empty__"}
                  type="button"
                  onClick={() => {
                    onChange(option.value);
                    setOpen(false);
                  }}
                  className={`w-full rounded-lg px-2.5 py-1.5 text-left text-[12px] ${
                    isActive ? "bg-[#1d1d1f] text-white" : "text-[#1d1d1f] hover:bg-[#f5f5f7]"
                  }`}
                >
                  {option.label}
                </button>
              );
            })
          ) : (
            <p className="px-2.5 py-2 text-[12px] text-[#8d8d93]">No options</p>
          )}
        </div>
      ) : null}
    </div>
  );
}

export { NeutralSelect };
