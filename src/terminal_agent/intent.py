"""Intent recognition and enumeration for the terminal agent.

Classifies natural-language user inputs into concrete MCP tool operations or
local session/CLI commands using deterministic keyword and pattern matching.
"""

from enum import Enum
import re
from typing import Optional


class IntentType(str, Enum):
    """Supported user intents covering all seven MCP tools and CLI controls."""

    # 1. Point-to-Point Propagation Tools
    CHECK_ENVIRONMENT = "check_environment"
    LIST_SCENES = "list_scenes"
    RUN_SIMULATION = "run_simulation"

    # 2. Radio Map & Experiment Management Tools
    GENERATE_RADIO_MAP = "generate_radio_map"
    LIST_EXPERIMENTS = "list_experiments"
    GET_EXPERIMENT_DETAILS = "get_experiment_details"
    COMPARE_EXPERIMENTS = "compare_experiments"

    # 3. Conversational / Local CLI Commands
    CONFIRMATION = "confirmation"
    REJECTION = "rejection"
    CLARIFICATION = "clarification"
    HELP = "help"
    TOOLS = "tools"
    CONTEXT = "context"
    RESET = "reset"
    EXIT = "exit"
    UNKNOWN = "unknown"


# Explicit regex rules for deterministic intent classification
_CLI_COMMAND_PATTERNS = {
    IntentType.EXIT: re.compile(r"^\s*(/exit|/quit|exit|quit|bye|:q|q)\s*$", re.IGNORECASE),
    IntentType.HELP: re.compile(r"^\s*(/help|\?|help|commands|what can you do\??)\s*$", re.IGNORECASE),
    IntentType.TOOLS: re.compile(r"^\s*(/tools|tools|list tools|show tools)\s*$", re.IGNORECASE),
    IntentType.CONTEXT: re.compile(r"^\s*(/context|context|show context|view context)\s*$", re.IGNORECASE),
    IntentType.RESET: re.compile(r"^\s*(/reset|reset|clear context|restart)\s*$", re.IGNORECASE),
}

_CONFIRMATION_PATTERN = re.compile(
    r"^\s*(yes|y|yeah|yep|proceed|confirm|ok|okay|sure|go ahead|run it|do it)\s*$",
    re.IGNORECASE,
)
_REJECTION_PATTERN = re.compile(
    r"^\s*(no|n|nope|cancel|stop|abort|don't|dont)\s*$",
    re.IGNORECASE,
)

_CHECK_ENV_PATTERNS = [
    re.compile(r"\b(check\s+environment|environment\s+check)\b", re.IGNORECASE),
    re.compile(r"\b(check\s+(?:whether\s+)?sionna(?:\s*rt)?|is\s+sionna(?:\s*rt)?\s+(?:ready|working)|sionna\s+status|sionna\s+ready)\b", re.IGNORECASE),
    re.compile(r"\b(verify\s+simulator|simulator\s+ready|backend\s+status)\b", re.IGNORECASE),
    re.compile(r"\b(system\s+health|system\s+status|runtime\s+check)\b", re.IGNORECASE),
]

_LIST_SCENES_PATTERNS = [
    re.compile(r"\b(list\s+scenes?|show\s+scenes?|available\s+scenes?|get\s+scenes?)\b", re.IGNORECASE),
    re.compile(r"\b(which\s+scenes?|what\s+scenes?|default\s+scene)\b", re.IGNORECASE),
    re.compile(r"\b(what\s+3d\s+models|3d\s+scenes?)\b", re.IGNORECASE),
]

_COMPARE_EXPERIMENTS_PATTERNS = [
    re.compile(r"\bcompare\s+(?:the\s+)?last\s+two\s+(?:radio\s*maps?|maps?|experiments?)\b", re.IGNORECASE),
    re.compile(r"\bcompare\s+this\s+map\s+with\s+(?:my\s+)?previous\s+map\b", re.IGNORECASE),
    re.compile(r"\bcompare\s+(?:experiments?|runs?|results?|maps?)\b", re.IGNORECASE),
    re.compile(r"\bcompare\s+experiment_\w+\s+(?:with|and|to)\s+experiment_\w+\b", re.IGNORECASE),
    re.compile(r"\b(?:diff|difference)\s+(?:between\s+)?experiment_\w+", re.IGNORECASE),
    re.compile(r"\bdifference\s+heatmaps?\b", re.IGNORECASE),
]

_GET_EXPERIMENT_PATTERNS = [
    re.compile(r"\b(?:show|view|get|inspect|display)\s+(?:the\s+)?(?:details\s+(?:of|for)\s+)?(?:the\s+)?(?:previous|last)\s+experiment\b", re.IGNORECASE),
    re.compile(r"\b(?:give\s+me\s+)?details\s+(?:of|for)\s+(?:the\s+)?(?:previous|last)\s+experiment\b", re.IGNORECASE),
    re.compile(r"\b(?:give\s+me\s+)?details\s+(?:of|for)\s+experiment\b", re.IGNORECASE),
    re.compile(r"\b(?:view|get|inspect|show)\s+experiment\s+id\b", re.IGNORECASE),
    re.compile(r"\b(?:details|info|metadata)\s+(?:of|for)\s+experiment_\w+\b", re.IGNORECASE),
    re.compile(r"^\s*experiment_\d{8}_\d{6}_[a-zA-Z0-9]+\s*$", re.IGNORECASE),
]

_LIST_EXPERIMENTS_PATTERNS = [
    re.compile(r"\b(?:list|show)\s+(?:all\s+)?(?:saved\s+)?experiments?\b", re.IGNORECASE),
    re.compile(r"\b(list\s+experiments?|show\s+(?:my\s+)?experiments?|previous\s+experiments?)\b", re.IGNORECASE),
    re.compile(r"\b(past\s+experiments?|saved\s+experiments?|experiment\s+history)\b", re.IGNORECASE),
    re.compile(r"\b(recent\s+simulations?|all\s+experiments?|all\s+saved\s+experiments?)\b", re.IGNORECASE),
]

_GENERATE_RADIO_MAP_PATTERNS = [
    re.compile(r"\b(?:generate|create|build|run|compute)\s+(?:a\s+)?radio\s*map\b", re.IGNORECASE),
    re.compile(r"\b(?:generate|create|show|compute)\s+(?:a\s+)?coverage(?:\s+map)?\b", re.IGNORECASE),
    re.compile(r"\b(?:heat\s*map|heatmap|rss\s*map|path\s*gain\s*map|signal[- ]strength\s*map)\b", re.IGNORECASE),
    re.compile(r"\bcoverage\s+simulation\b", re.IGNORECASE),
    re.compile(r"\b(?:regenerate|rerun)\s+(?:the\s+)?(?:radio\s*)?map\b", re.IGNORECASE),
    re.compile(r"\bgenerate\s+(?:the\s+)?radio\s*map\s+for\b", re.IGNORECASE),
    re.compile(r"\b(?:now\s+)?generate\s+(?:the\s+same\s+map|again\s+)?at\s+\d+(?:\.\d+)?\s*(?:g|m)?hz\b", re.IGNORECASE),
    re.compile(r"\b(?:now\s+)?generate\s+at\s+\d+", re.IGNORECASE),
]

_RUN_SIMULATION_PATTERNS = [
    re.compile(r"\b(?:point[- ]to[- ]point|p2p)\s*(?:simulation)?\b", re.IGNORECASE),
    re.compile(r"\b(?:simulate\s+(?:a\s+)?link|link\s+simulation)\b", re.IGNORECASE),
    re.compile(r"\bcalculate\s+received\s+power\s+between\b", re.IGNORECASE),
    re.compile(r"\b(?:simulate|ray[- ]trace)\s+between\b", re.IGNORECASE),
    re.compile(r"\bpropagation\s+between\b", re.IGNORECASE),
    re.compile(r"\bsimulation\s+using\s+transmitter\b", re.IGNORECASE),
    re.compile(r"\bsimulation\s+between\s+(?:tx|transmitter)\b", re.IGNORECASE),
    re.compile(r"\b(?:run|execute)\s+(?:a\s+)?(?:point[- ]to[- ]point\s+)?simulation\s+between\b", re.IGNORECASE),
    re.compile(r"\b(?:run|execute)\s+(?:a\s+)?simulation\s+using\b", re.IGNORECASE),
    re.compile(r"\b(?:run|execute)\s+the\s+same\s+simulation\b", re.IGNORECASE),
    re.compile(r"\brun\s+(?:the\s+)?previous\s+simulation\s+again\b", re.IGNORECASE),
]


def classify_intent(
    text: str,
    pending_intent: Optional[IntentType] = None,
    awaiting_confirmation: bool = False,
    has_active_context: bool = False,
    last_intent: Optional[IntentType] = None,
) -> IntentType:
    """Classifies user natural-language input into a deterministic IntentType.

    Args:
        text: Raw natural language input from the user.
        pending_intent: Active intent waiting for parameter clarification.
        awaiting_confirmation: Whether agent is awaiting user yes/no.
        has_active_context: Whether session has prior simulation context.
        last_intent: The most recently executed simulation/map intent.

    Returns:
        IntentType: The identified intent.
    """
    cleaned = text.strip()
    if not cleaned:
        return IntentType.UNKNOWN

    # 1. Local CLI Commands
    for intent, pattern in _CLI_COMMAND_PATTERNS.items():
        if pattern.match(cleaned):
            return intent

    # 2. Confirmation / Rejection checks
    if awaiting_confirmation:
        if _CONFIRMATION_PATTERN.match(cleaned):
            return IntentType.CONFIRMATION
        if _REJECTION_PATTERN.match(cleaned):
            return IntentType.REJECTION

    # 3. Pending clarification context check
    if pending_intent is not None:
        if re.search(r"\b(default|keep\s+default|use\s+defaults?|standard)\b", cleaned, re.IGNORECASE):
            return IntentType.CLARIFICATION
        if re.search(r"\b(\d+|simple_reflector|isotropic|dipole|directional)\b", cleaned, re.IGNORECASE):
            return IntentType.CLARIFICATION

    # 4. Compare Experiments
    for pattern in _COMPARE_EXPERIMENTS_PATTERNS:
        if pattern.search(cleaned):
            return IntentType.COMPARE_EXPERIMENTS

    # 5. Get Experiment Details (check before List Experiments)
    for pattern in _GET_EXPERIMENT_PATTERNS:
        if pattern.search(cleaned):
            return IntentType.GET_EXPERIMENT_DETAILS

    # 6. List Experiments
    for pattern in _LIST_EXPERIMENTS_PATTERNS:
        if pattern.search(cleaned):
            return IntentType.LIST_EXPERIMENTS

    # 7. Check Environment
    for pattern in _CHECK_ENV_PATTERNS:
        if pattern.search(cleaned):
            return IntentType.CHECK_ENVIRONMENT

    # 8. List Scenes
    for pattern in _LIST_SCENES_PATTERNS:
        if pattern.search(cleaned):
            return IntentType.LIST_SCENES

    # 9. Point-to-Point Simulation explicit patterns
    for pattern in _RUN_SIMULATION_PATTERNS:
        if pattern.search(cleaned):
            return IntentType.RUN_SIMULATION

    # Additional Point-to-point check: If both TX and RX are explicitly specified
    # e.g. "Run a simulation using transmitter at [0, 0, 10] and receiver at [20, 10, 1.5]..."
    has_tx_term = bool(re.search(r"\b(tx|transmitter)\b", cleaned, re.IGNORECASE))
    has_rx_term = bool(re.search(r"\b(rx|receiver)\b", cleaned, re.IGNORECASE))
    if "simulation" in cleaned.lower() and has_tx_term and has_rx_term:
        return IntentType.RUN_SIMULATION

    # 10. Radio Map Generation explicit patterns
    for pattern in _GENERATE_RADIO_MAP_PATTERNS:
        if pattern.search(cleaned):
            return IntentType.GENERATE_RADIO_MAP

    # Additional Radio Map check: If user says "generate ... cell size" or "coverage"
    if re.search(r"\b(radio\s*map|cell\s*size|resolution|heat\s*map|heatmap)\b", cleaned, re.IGNORECASE):
        if re.search(r"\b(generate|create|build|run|make|show)\b", cleaned, re.IGNORECASE):
            return IntentType.GENERATE_RADIO_MAP

    # 11. Conversational Context Reuse / Follow-up modifications
    # e.g., "Now change frequency to 5 GHz", "Use a dipole antenna instead",
    # "Move the transmitter to [5, 5, 10]", "Run the same simulation again"
    if has_active_context or last_intent is not None:
        effective_intent = last_intent or IntentType.GENERATE_RADIO_MAP

        # Explicit cues for radio map follow-ups
        if re.search(r"\b(cell\s*size|resolution|receiver\s*height|rx\s*height|regenerate\s*(?:the\s+)?map|same\s*map)\b", cleaned, re.IGNORECASE):
            return IntentType.GENERATE_RADIO_MAP

        # Explicit cues for simulation follow-ups
        if re.search(r"\b(same\s*simulation|previous\s*simulation|receiver\s*at|rx\s*at|rx\s*position)\b", cleaned, re.IGNORECASE):
            return IntentType.RUN_SIMULATION

        # General parameter modifications: "Now change frequency to 5 GHz", "Use dipole antenna instead"
        if re.search(
            r"\b(change|move|put|set|use|now|switch|update|frequency|antenna|dipole|isotropic|directional|power|transmitter|tx)\b",
            cleaned,
            re.IGNORECASE,
        ) or re.search(r"\d+(?:\.\d+)?\s*(?:ghz|mhz|hz)", cleaned, re.IGNORECASE):
            return effective_intent

    return IntentType.UNKNOWN
