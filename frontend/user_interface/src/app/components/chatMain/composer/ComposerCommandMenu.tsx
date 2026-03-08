import type { CommandOption, CommandQueryState } from "./commandPalette";

type ComposerCommandMenuProps = {
  query: CommandQueryState;
  options: CommandOption[];
  activeIndex: number;
  onSelect: (option: CommandOption) => void;
};

function ComposerCommandMenu({ query, options, activeIndex, onSelect }: ComposerCommandMenuProps) {
  if (!options.length) {
    return null;
  }
  const label =
    query.trigger === "document" ? "Attach document" : query.trigger === "group" ? "Attach group" : "Attach project";

  return (
    <div className="absolute bottom-full left-3 right-3 z-20 mb-2 overflow-hidden rounded-2xl border border-black/[0.1] bg-white shadow-[0_18px_38px_-24px_rgba(0,0,0,0.5)]">
      <div className="border-b border-black/[0.06] px-3 py-2 text-[11px] text-[#6e6e73]">{label}</div>
      <ul className="max-h-56 overflow-y-auto py-1.5">
        {options.map((option, index) => (
          <li key={`${query.trigger}-${option.id}`}>
            <button
              type="button"
              onMouseDown={(event) => {
                event.preventDefault();
                onSelect(option);
              }}
              className={`flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-[13px] transition-colors ${
                index === activeIndex ? "bg-[#f3f3f6] text-[#1d1d1f]" : "text-[#2a2a2d] hover:bg-[#f8f8fa]"
              }`}
            >
              <span className="truncate">{option.label}</span>
              {option.subtitle ? (
                <span className="shrink-0 text-[11px] text-[#8d8d93]">{option.subtitle}</span>
              ) : null}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

export { ComposerCommandMenu };
