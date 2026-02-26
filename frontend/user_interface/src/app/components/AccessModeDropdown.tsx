import { ChevronDown } from "lucide-react";
import { useMemo, useState } from "react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "./ui/dropdown-menu";

type AccessMode = "restricted" | "full_access";

type AccessModeDropdownProps = {
  value: AccessMode;
  onChange: (value: AccessMode) => void;
};

const ACCESS_LABELS: Record<AccessMode, string> = {
  restricted: "Restricted",
  full_access: "Full Access",
};

export function AccessModeDropdown({ value, onChange }: AccessModeDropdownProps) {
  const [open, setOpen] = useState(false);
  const label = useMemo(() => ACCESS_LABELS[value] ?? "Restricted", [value]);

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className="inline-flex h-9 items-center gap-1 rounded-full border border-black/[0.08] bg-white px-3.5 text-[12px] font-medium text-[#1d1d1f] shadow-[0_1px_2px_rgba(0,0,0,0.04)] transition-colors duration-150 hover:bg-[#f7f7f8] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-black/20"
          aria-haspopup="menu"
          aria-expanded={open}
          aria-label={`Access: ${label}`}
        >
          <span>{label}</span>
          <ChevronDown className="h-3.5 w-3.5 text-[#6e6e73]" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        sideOffset={6}
        className="w-[156px] rounded-2xl border-black/[0.08] bg-white p-1.5 shadow-[0_14px_28px_-20px_rgba(0,0,0,0.55)]"
      >
        <DropdownMenuRadioGroup
          value={value}
          onValueChange={(next) => onChange(next as AccessMode)}
        >
          <DropdownMenuRadioItem
            value="restricted"
            className="rounded-lg py-2 text-[12px] text-[#1d1d1f]"
          >
            Restricted
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem
            value="full_access"
            className="rounded-lg py-2 text-[12px] text-[#1d1d1f]"
          >
            Full Access
          </DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
