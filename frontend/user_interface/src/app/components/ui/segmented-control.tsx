import { type KeyboardEvent, useMemo, useRef } from "react";
import { cn } from "./utils";

type SegmentOption = {
  value: string;
  label: string;
};

type SegmentedControlProps = {
  options: SegmentOption[];
  value: string;
  onChange: (value: string) => void;
  ariaLabel: string;
  className?: string;
  segmentClassName?: string;
};

export function SegmentedControl({
  options,
  value,
  onChange,
  ariaLabel,
  className,
  segmentClassName,
}: SegmentedControlProps) {
  const refs = useRef<Array<HTMLButtonElement | null>>([]);
  const segmentCount = Math.max(options.length, 1);
  const activeIndex = useMemo(() => {
    const index = options.findIndex((option) => option.value === value);
    return index >= 0 ? index : 0;
  }, [options, value]);
  const indicatorStyle = useMemo(
    () => ({
      width: `calc((100% - 0.5rem) / ${segmentCount})`,
      transform: `translateX(${activeIndex * 100}%)`,
    }),
    [activeIndex, segmentCount],
  );

  const focusAndSelect = (index: number) => {
    const bounded = ((index % options.length) + options.length) % options.length;
    const next = options[bounded];
    if (!next) {
      return;
    }
    onChange(next.value);
    refs.current[bounded]?.focus();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (!options.length) {
      return;
    }
    if (event.key === "ArrowRight" || event.key === "ArrowDown") {
      event.preventDefault();
      focusAndSelect(index + 1);
      return;
    }
    if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      event.preventDefault();
      focusAndSelect(index - 1);
      return;
    }
    if (event.key === "Home") {
      event.preventDefault();
      focusAndSelect(0);
      return;
    }
    if (event.key === "End") {
      event.preventDefault();
      focusAndSelect(options.length - 1);
    }
  };

  return (
    <div
      role="radiogroup"
      aria-label={ariaLabel}
      className={cn(
        "segmented-control-shell relative inline-grid h-10 items-center rounded-[14px] border border-black/[0.08] bg-[#f3f3f5] p-1",
        className,
      )}
      style={{ gridTemplateColumns: `repeat(${segmentCount}, minmax(0, 1fr))` }}
    >
      <span
        aria-hidden="true"
        className="segmented-indicator-spring pointer-events-none absolute inset-y-1 left-1 rounded-[10px] border border-black/[0.04] bg-white shadow-[0_6px_14px_-14px_rgba(0,0,0,0.55)]"
        style={indicatorStyle}
      />
      {options.map((option, index) => {
        const isActive = option.value === value;
        return (
          <button
            key={option.value}
            ref={(node) => {
              refs.current[index] = node;
            }}
            type="button"
            role="radio"
            aria-checked={isActive}
            aria-pressed={isActive}
            tabIndex={activeIndex === index ? 0 : -1}
            onClick={() => onChange(option.value)}
            onKeyDown={(event) => handleKeyDown(event, index)}
            className={cn(
              "relative z-10 inline-flex h-8 min-w-0 items-center justify-center rounded-[10px] px-3 text-[12px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-black/20",
              isActive
                ? "text-[#1d1d1f]"
                : "text-[#6e6e73] hover:text-[#1d1d1f]",
              segmentClassName,
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
