import { useEffect, useState } from "react";

type TypewriterLoaderProps = {
  text: string;
  /** Milliseconds per character when typing forward (default 40) */
  typeSpeed?: number;
  /** Milliseconds per character when deleting (default 25) */
  deleteSpeed?: number;
  /** Milliseconds to pause after fully typed before deleting (default 1200) */
  pauseAfterType?: number;
  /** Milliseconds to pause after fully deleted before re-typing (default 400) */
  pauseAfterDelete?: number;
};

/**
 * Typewriter loop: types the text out character by character,
 * pauses, deletes character by character, pauses, repeats.
 */
function TypewriterLoader({
  text,
  typeSpeed = 40,
  deleteSpeed = 25,
  pauseAfterType = 1200,
  pauseAfterDelete = 400,
}: TypewriterLoaderProps) {
  const [displayed, setDisplayed] = useState("");
  const [phase, setPhase] = useState<"typing" | "paused" | "deleting" | "waiting">("typing");

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;

    if (phase === "typing") {
      if (displayed.length < text.length) {
        timer = setTimeout(() => {
          setDisplayed(text.slice(0, displayed.length + 1));
        }, typeSpeed);
      } else {
        timer = setTimeout(() => setPhase("paused"), pauseAfterType);
      }
    } else if (phase === "paused") {
      timer = setTimeout(() => setPhase("deleting"), 0);
    } else if (phase === "deleting") {
      if (displayed.length > 0) {
        timer = setTimeout(() => {
          setDisplayed(displayed.slice(0, -1));
        }, deleteSpeed);
      } else {
        timer = setTimeout(() => setPhase("waiting"), pauseAfterDelete);
      }
    } else if (phase === "waiting") {
      timer = setTimeout(() => setPhase("typing"), 0);
    }

    return () => clearTimeout(timer);
  }, [displayed, phase, text, typeSpeed, deleteSpeed, pauseAfterType, pauseAfterDelete]);

  return (
    <span className="text-[14px] leading-relaxed text-[#6e6e73]">
      {displayed}
      <span className="ml-[1px] inline-block w-[2px] animate-pulse bg-[#6e6e73]">&nbsp;</span>
    </span>
  );
}

export { TypewriterLoader };
