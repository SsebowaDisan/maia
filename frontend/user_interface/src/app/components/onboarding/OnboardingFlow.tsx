/**
 * OnboardingFlow — guides first-time users through Maia setup.
 *
 * Shows on first visit (checks localStorage). Steps:
 * 1. Welcome — what Maia does
 * 2. Connect — set up first connector (Google, Slack, etc.)
 * 3. Explore — browse marketplace agents
 * 4. Try it — send first message
 */
import { useState, useEffect } from "react";

const ONBOARDING_KEY = "maia.onboarding.completed";

type OnboardingStep = {
  title: string;
  subtitle: string;
  description: string;
  icon: string;
  action: string;
};

const STEPS: OnboardingStep[] = [
  {
    title: "Welcome to Maia",
    subtitle: "Your AI agent platform",
    description:
      "Maia is where AI agents work as a team. Chat with them, build workflows, " +
      "connect your tools, and watch agents collaborate in real-time.",
    icon: "\u{1F44B}",
    action: "Get started",
  },
  {
    title: "Connect your tools",
    subtitle: "Gmail, Slack, Jira, and 50+ more",
    description:
      "Agents need access to your tools to work. Connect at least one service " +
      "to unlock the full experience. You can always add more later.",
    icon: "\u{1F50C}",
    action: "Connect a tool",
  },
  {
    title: "Browse the marketplace",
    subtitle: "10,000+ ready-to-use agents",
    description:
      "Find agents built for your industry and use case. Install them in one click " +
      "and they're ready to work with your connected tools.",
    icon: "\u{1F6CD}",
    action: "Browse agents",
  },
  {
    title: "You're all set",
    subtitle: "Start chatting with your agents",
    description:
      "Type a message to get started. Try 'Ask' mode for quick answers, " +
      "'Company Agent' for multi-step tasks, or 'Brain' to build a full workflow.",
    icon: "\u{1F680}",
    action: "Start chatting",
  },
];

type OnboardingFlowProps = {
  onComplete: () => void;
  onNavigate?: (path: string) => void;
};

function OnboardingFlow({ onComplete, onNavigate }: OnboardingFlowProps) {
  const [step, setStep] = useState(0);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setVisible(true), 100);
    return () => clearTimeout(timer);
  }, []);

  function handleNext() {
    if (step === 1 && onNavigate) {
      onNavigate("/connectors");
    }
    if (step === 2 && onNavigate) {
      onNavigate("/marketplace");
    }
    if (step >= STEPS.length - 1) {
      localStorage.setItem(ONBOARDING_KEY, "true");
      setVisible(false);
      setTimeout(onComplete, 300);
      return;
    }
    setStep((s) => s + 1);
  }

  function handleSkip() {
    localStorage.setItem(ONBOARDING_KEY, "true");
    setVisible(false);
    setTimeout(onComplete, 300);
  }

  const current = STEPS[step];
  const progress = ((step + 1) / STEPS.length) * 100;

  return (
    <div
      className={`fixed inset-0 z-[9999] flex items-center justify-center bg-black/60 backdrop-blur-sm transition-opacity duration-300 ${
        visible ? "opacity-100" : "opacity-0"
      }`}
    >
      <div className="relative w-full max-w-[480px] overflow-hidden rounded-2xl bg-white shadow-2xl">
        {/* Progress bar */}
        <div className="h-1 bg-gray-100">
          <div
            className="h-full bg-purple-500 transition-all duration-500 ease-out"
            style={{ width: `${progress}%` }}
          />
        </div>

        {/* Content */}
        <div className="px-8 pb-8 pt-10 text-center">
          <div className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-2xl bg-purple-50 text-[32px]">
            {current.icon}
          </div>
          <h2 className="text-[22px] font-bold text-gray-900">{current.title}</h2>
          <p className="mt-1 text-[14px] font-medium text-purple-600">{current.subtitle}</p>
          <p className="mt-4 text-[14px] leading-relaxed text-gray-600">{current.description}</p>

          {/* Actions */}
          <div className="mt-8 flex items-center justify-between">
            <button
              onClick={handleSkip}
              className="text-[13px] text-gray-400 transition-colors hover:text-gray-600"
            >
              Skip setup
            </button>
            <button
              onClick={handleNext}
              className="rounded-xl bg-purple-600 px-6 py-2.5 text-[14px] font-semibold text-white transition-all hover:bg-purple-700 active:scale-95"
            >
              {current.action}
            </button>
          </div>

          {/* Step dots */}
          <div className="mt-6 flex justify-center gap-2">
            {STEPS.map((_, i) => (
              <div
                key={i}
                className={`h-1.5 rounded-full transition-all duration-300 ${
                  i === step ? "w-6 bg-purple-500" : i < step ? "w-1.5 bg-purple-300" : "w-1.5 bg-gray-200"
                }`}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function shouldShowOnboarding(): boolean {
  try {
    return localStorage.getItem(ONBOARDING_KEY) !== "true";
  } catch {
    return false;
  }
}

export { OnboardingFlow, shouldShowOnboarding, ONBOARDING_KEY };
