"""Conversational session context for the Sionna RT terminal agent.

Stores previous simulation configurations, last executed experiment identifiers,
and multi-turn clarification state for natural follow-up instructions without
requiring external database infrastructure.
"""

from copy import deepcopy
import re
from typing import Any, Dict, List, Optional, Tuple
from src.terminal_agent.intent import IntentType


class SessionContext:
    """In-memory session state across the active terminal conversation."""

    def __init__(self) -> None:
        self.last_intent: Optional[IntentType] = None
        self.last_radio_map_config: Dict[str, Any] = {}
        self.last_simulation_config: Dict[str, Any] = {}
        self.last_experiment_id: Optional[str] = None
        self.previous_experiment_id: Optional[str] = None
        self.last_result: Optional[Dict[str, Any]] = None
        self.last_selected_scene: Optional[str] = None
        self.last_antenna_config: Dict[str, Any] = {}

        # Multi-turn clarification and confirmation state
        self.pending_intent: Optional[IntentType] = None
        self.pending_params: Dict[str, Any] = {}
        self.pending_param_name: Optional[str] = None
        self.pending_question: Optional[str] = None
        self.awaiting_confirmation: bool = False
        self.pending_tool_call: Optional[Tuple[str, Dict[str, Any]]] = None

        # Conversation turns history [(user_text, assistant_response)]
        self.history: List[Tuple[str, str]] = []

    def has_active_context(self) -> bool:
        """Returns True if there is prior simulation or radio map configuration."""
        return bool(self.last_radio_map_config or self.last_simulation_config)

    def has_pending_clarification(self) -> bool:
        """Returns True if agent is waiting for clarification on a specific parameter."""
        return self.pending_intent is not None and self.pending_param_name is not None

    def set_pending_clarification(
        self,
        intent: IntentType,
        current_params: Dict[str, Any],
        param_name: str,
        question: str,
    ) -> None:
        """Registers a missing parameter question to resolve on the next turn."""
        self.pending_intent = intent
        self.pending_params = deepcopy(current_params)
        self.pending_param_name = param_name
        self.pending_question = question
        self.awaiting_confirmation = False
        self.pending_tool_call = None

    def set_awaiting_confirmation(self, tool_name: str, validated_args: Dict[str, Any]) -> None:
        """Sets the agent into confirmation state before running an expensive simulation."""
        self.awaiting_confirmation = True
        self.pending_tool_call = (tool_name, validated_args)

    def clear_pending(self) -> None:
        """Clears pending clarification and confirmation state."""
        self.pending_intent = None
        self.pending_params = {}
        self.pending_param_name = None
        self.pending_question = None
        self.awaiting_confirmation = False
        self.pending_tool_call = None

    def reset(self) -> None:
        """Resets the entire session context to clean initial state."""
        self.last_intent = None
        self.last_radio_map_config = {}
        self.last_simulation_config = {}
        self.last_experiment_id = None
        self.previous_experiment_id = None
        self.last_result = None
        self.last_selected_scene = None
        self.last_antenna_config = {}
        self.clear_pending()
        self.history.clear()

    def record_turn(self, user_msg: str, assistant_msg: str) -> None:
        """Records a completed conversational turn."""
        self.history.append((user_msg, assistant_msg))

    def update_last_radio_map(self, config: Dict[str, Any], result: Optional[Dict[str, Any]] = None) -> None:
        """Updates stored radio map configuration and latest experiment result."""
        self.last_intent = IntentType.GENERATE_RADIO_MAP
        self.last_radio_map_config = deepcopy(config)
        scene = config.get("scene_name") or config.get("scene")
        if scene:
            self.last_selected_scene = scene

        # Update last antenna config
        for ant_k in ("antenna_type", "polarization", "num_rows", "num_cols", "horizontal_spacing", "vertical_spacing"):
            if ant_k in config:
                self.last_antenna_config[ant_k] = config[ant_k]

        if result:
            self.last_result = result
            if "experiment_id" in result:
                new_id = result["experiment_id"]
                if self.last_experiment_id and self.last_experiment_id != new_id:
                    self.previous_experiment_id = self.last_experiment_id
                self.last_experiment_id = new_id

    def update_last_simulation(self, config: Dict[str, Any], result: Optional[Dict[str, Any]] = None) -> None:
        """Updates stored point-to-point simulation configuration and result."""
        self.last_intent = IntentType.RUN_SIMULATION
        self.last_simulation_config = deepcopy(config)
        scene = config.get("scene") or config.get("scene_name")
        if scene:
            self.last_selected_scene = scene

        # Update last antenna config
        for ant_k in ("antenna_type", "polarization", "num_rows", "num_cols", "tx_antenna_type", "rx_antenna_type", "horizontal_spacing", "vertical_spacing"):
            if ant_k in config:
                self.last_antenna_config[ant_k] = config[ant_k]

        if result:
            self.last_result = result

    def get_merged_radio_map_config(self, new_params: Dict[str, Any]) -> Dict[str, Any]:
        """Merges new parameters into the previous radio map configuration.

        Enables instructions like 'Now generate the same map at 5 GHz' or
        'Change cell size to 2 metres and rerun'.
        Preserves isolation from point-to-point configuration.
        """
        merged = deepcopy(self.last_radio_map_config)
        merged.update({k: v for k, v in new_params.items() if v is not None and not k.startswith("_")})
        return merged

    def get_merged_simulation_config(self, new_params: Dict[str, Any]) -> Dict[str, Any]:
        """Merges new parameters into previous point-to-point configuration.

        Preserves isolation from radio map configuration.
        """
        merged = deepcopy(self.last_simulation_config)
        merged.update({k: v for k, v in new_params.items() if v is not None and not k.startswith("_")})
        return merged
