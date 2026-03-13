"""Brain package — reactive coordinator for one agent turn.

Public surface
--------------
Brain          — coordinator class; call observe_step() after each tool step
build_brain    — factory that wires BrainState + Brain together
BrainState     — working memory (coverage, evidence, revision budget)
BrainSignal    — signal sent from executor to Brain after a step
BrainDirective — directive returned by Brain.assess()
StepOutcome    — captured result of one tool execution

HandoffWatcher — idle watchdog that triggers graceful handoff on timeout
save_brain_memory / load_brain_memory / apply_memory_to_state
               — cross-turn persistence helpers via SessionPool
"""
from .brain import Brain, build_brain
from .handoff_watcher import HandoffWatcher
from .memory import apply_memory_to_state, load_brain_memory, save_brain_memory
from .signals import BrainDirective, BrainSignal, StepOutcome
from .state import BrainState

__all__ = [
    "Brain",
    "BrainDirective",
    "BrainSignal",
    "BrainState",
    "HandoffWatcher",
    "StepOutcome",
    "apply_memory_to_state",
    "build_brain",
    "load_brain_memory",
    "save_brain_memory",
]
