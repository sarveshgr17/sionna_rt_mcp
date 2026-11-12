"""Command and intent execution orchestrator for Sionna RT terminal agent.

Coordinates NLP parsing, conversational session context, parameter validation,
MCP client tool invocation, and formatted terminal output generation.
"""

import json
import logging
import re
from typing import Any, Dict, Optional, Tuple

from src.terminal_agent.context import SessionContext
from src.terminal_agent.intent import IntentType, classify_intent
from src.terminal_agent.mcp_client import MCPDirectClient, MCPClientError
from src.terminal_agent.parser import (
    extract_all_parameters,
    extract_cell_size,
    extract_coordinates,
    extract_experiment_ids,
    extract_frequency,
    extract_samples_per_tx,
    extract_scene_name,
    extract_tx_power,
)
from src.terminal_agent.presenter import (
    format_comparison_result,
    format_environment_status,
    format_experiment_details,
    format_experiments_list,
    format_help,
    format_radio_map_result,
    format_scenes_list,
    format_simulation_result,
    format_understanding_acknowledgment,
)
from src.terminal_agent.validator import (
    DEFAULT_RADIO_MAP_CONFIG,
    DEFAULT_SIMULATION_CONFIG,
    validate_compare_experiments_args,
    validate_get_experiment_args,
    validate_radio_map_args,
    validate_simulation_args,
)

logger = logging.getLogger("sionna_rt_mcp.terminal_agent.executor")


class ExecutionResult:
    """Represents the response from the agent to the user."""

    def __init__(self, output: str, is_exit: bool = False) -> None:
        self.output = output
        self.is_exit = is_exit


class AgentExecutor:
    """Coordinates the conversational AI terminal workflow."""

    def __init__(self, mcp_client: MCPDirectClient, context: Optional[SessionContext] = None) -> None:
        self.client = mcp_client
        self.context = context or SessionContext()

    async def execute_instruction(self, user_text: str) -> ExecutionResult:
        """Processes a single user natural language or CLI input."""
        cleaned = user_text.strip()
        if not cleaned:
            return ExecutionResult("")

        # 1. Local CLI Controls
        if re.match(r"^(/exit|/quit|exit|quit|bye|:q|q)$", cleaned, re.IGNORECASE):
            return ExecutionResult("Exiting Sionna Radio Planner CLI. Goodbye!", is_exit=True)

        if re.match(r"^(/help|\?|help)$", cleaned, re.IGNORECASE):
            return ExecutionResult(format_help())

        if re.match(r"^(/tools|tools)$", cleaned, re.IGNORECASE):
            return ExecutionResult(self._format_tools_summary())

        if re.match(r"^(/context|context)$", cleaned, re.IGNORECASE):
            return ExecutionResult(self._format_context_summary())

        if re.match(r"^(/reset|reset)$", cleaned, re.IGNORECASE):
            self.context.reset()
            return ExecutionResult("Session context has been reset to clean initial state.")

        # 2. Awaiting Confirmation Check
        if self.context.awaiting_confirmation:
            intent = classify_intent(cleaned, awaiting_confirmation=True)
            if intent == IntentType.CONFIRMATION:
                tool_name, args = self.context.pending_tool_call  # type: ignore
                self.context.clear_pending()
                return await self._execute_tool_and_format(tool_name, args)
            elif intent == IntentType.REJECTION:
                self.context.clear_pending()
                return ExecutionResult("Operation cancelled by user.")

        # 3. Pending Parameter Clarification
        if self.context.has_pending_clarification():
            return await self._handle_clarification_response(cleaned)

        # 4. Standard Intent Classification
        intent = classify_intent(
            cleaned,
            has_active_context=self.context.has_active_context(),
            last_intent=self.context.last_intent,
        )

        extracted = extract_all_parameters(cleaned)

        # Handle specific operations
        if intent == IntentType.CHECK_ENVIRONMENT:
            try:
                res = await self.client.call_tool("check_environment", {})
                return ExecutionResult(format_environment_status(res))
            except MCPClientError as exc:
                return ExecutionResult(f"Error checking environment: {exc}")

        elif intent == IntentType.LIST_SCENES:
            try:
                res = await self.client.call_tool("list_scenes", {})
                return ExecutionResult(format_scenes_list(res))
            except MCPClientError as exc:
                return ExecutionResult(f"Error listing scenes: {exc}")

        elif intent == IntentType.LIST_EXPERIMENTS:
            try:
                res = await self.client.call_tool("list_experiments", {})
                return ExecutionResult(format_experiments_list(res))
            except MCPClientError as exc:
                return ExecutionResult(f"Error listing experiments: {exc}")

        elif intent == IntentType.GET_EXPERIMENT_DETAILS:
            val = validate_get_experiment_args(extracted, last_exp_id=self.context.last_experiment_id)
            if val.needs_clarification:
                self.context.set_pending_clarification(
                    intent=IntentType.GET_EXPERIMENT_DETAILS,
                    current_params={},
                    param_name=val.missing_param,  # type: ignore
                    question=val.clarification_prompt,  # type: ignore
                )
                return ExecutionResult(f"Assistant: {val.clarification_prompt}")
            try:
                res = await self.client.call_tool("get_experiment_details", val.arguments)
                self.context.last_experiment_id = val.arguments.get("experiment_id")
                return ExecutionResult(format_experiment_details(res))
            except MCPClientError as exc:
                return ExecutionResult(f"Error retrieving experiment details: {exc}")

        elif intent == IntentType.COMPARE_EXPERIMENTS:
            val = validate_compare_experiments_args(
                extracted,
                last_exp_id=self.context.last_experiment_id,
                previous_exp_id=self.context.previous_experiment_id,
            )
            if val.needs_clarification:
                self.context.set_pending_clarification(
                    intent=IntentType.COMPARE_EXPERIMENTS,
                    current_params=val.arguments,
                    param_name=val.missing_param,  # type: ignore
                    question=val.clarification_prompt,  # type: ignore
                )
                return ExecutionResult(f"Assistant: {val.clarification_prompt}")
            try:
                ack = format_understanding_acknowledgment(
                    "Experiment comparison",
                    {"Baseline (A)": val.arguments["experiment_id_a"], "Modified (B)": val.arguments["experiment_id_b"]},
                )
                res = await self.client.call_tool("compare_experiments", val.arguments)
                return ExecutionResult(f"{ack}\n\n{format_comparison_result(res)}")
            except MCPClientError as exc:
                return ExecutionResult(f"Error comparing experiments: {exc}")

        elif intent == IntentType.RUN_SIMULATION:
            is_explicit_followup = bool(
                self.context.last_simulation_config
                and re.search(r"\b(same\s*simulation|previous\s*simulation|again|now\s+change|use\s+.*instead)\b", cleaned, re.IGNORECASE)
            )

            has_both_coords = ("tx_position" in extracted and "rx_position" in extracted)
            has_only_one_coord = (
                ("tx_position" in extracted and "rx_position" not in extracted)
                or ("rx_position" in extracted and "tx_position" not in extracted)
            )

            if is_explicit_followup and not has_only_one_coord:
                merged = self.context.get_merged_simulation_config(extracted)
                require_both = False
            elif has_only_one_coord:
                merged = extracted
                require_both = True
            else:
                merged = self.context.get_merged_simulation_config(extracted) if self.context.last_simulation_config else extracted
                require_both = not bool(self.context.last_simulation_config)

            val = validate_simulation_args(merged, require_both_coordinates=require_both)
            if val.needs_clarification:
                self.context.set_pending_clarification(
                    intent=IntentType.RUN_SIMULATION,
                    current_params=val.arguments,
                    param_name=val.missing_param,  # type: ignore
                    question=val.clarification_prompt,  # type: ignore
                )
                return ExecutionResult(f"Assistant: {val.clarification_prompt}")

            if not val.is_valid:
                return ExecutionResult(f"Validation error: {val.error_message}")

            ack = format_understanding_acknowledgment("Point-to-point simulation", val.arguments)
            try:
                res = await self.client.call_tool("run_simulation", val.arguments)
                self.context.update_last_simulation(val.arguments, res)
                return ExecutionResult(f"{ack}\n\n{format_simulation_result(res)}")
            except MCPClientError as exc:
                return ExecutionResult(f"Simulation failed: {exc}")

        elif intent == IntentType.GENERATE_RADIO_MAP:
            return await self._process_radio_map_request(cleaned, extracted)

        # Unknown intent
        return ExecutionResult(
            "Assistant: I did not understand your instruction. You can type:\n"
            "  • 'Generate a radio map at 3.5 GHz using a directional antenna and 2 metre cell size.'\n"
            "  • 'Run a simulation between TX [0, 0, 10] and RX [20, 10, 1.5] at 3.5 GHz.'\n"
            "  • 'Check whether Sionna RT is ready.'\n"
            "  • 'List available scenes.'\n"
            "  • '/help' for more examples."
        )

    async def _process_radio_map_request(self, user_text: str, extracted: Dict[str, Any]) -> ExecutionResult:
        """Processes radio map generation, handling context reuse and multi-turn questions."""
        is_context_followup = bool(
            self.context.last_radio_map_config
            and (
                re.search(r"\b(same\s*map|rerun|now\s+generate|change|put|move|update|regenerate)\b", user_text, re.IGNORECASE)
                or not ("cell_size" in extracted or "samples_per_tx" in extracted)
            )
        )

        if is_context_followup and self.context.last_radio_map_config:
            merged = self.context.get_merged_radio_map_config(extracted)
            val = validate_radio_map_args(merged)
            if val.is_valid:
                return await self._execute_radio_map(val.arguments)

        # Check if user gave an incomplete initial instruction without scene and without cell size
        has_scene = "scene_name" in extracted
        has_cell_size = "cell_size" in extracted

        if not has_scene and not has_cell_size and not ("scene_name" in self.context.last_radio_map_config):
            self.context.set_pending_clarification(
                intent=IntentType.GENERATE_RADIO_MAP,
                current_params=extracted,
                param_name="scene_name",
                question="Which scene should I use? (Press Enter or say 'default' for 'simple_reflector')",
            )
            return ExecutionResult("Assistant: Which scene should I use? (Press Enter or say 'default' for 'simple_reflector')")

        if not has_cell_size and not ("cell_size" in self.context.last_radio_map_config):
            self.context.set_pending_clarification(
                intent=IntentType.GENERATE_RADIO_MAP,
                current_params=extracted,
                param_name="cell_size",
                question="What cell size should I use? (e.g. 5 metres, or 'default' for 1.0m)",
            )
            return ExecutionResult("Assistant: What cell size should I use? (e.g. 5 metres, or 'default' for 1.0m)")

        # Validate arguments with defaults applied
        val = validate_radio_map_args(extracted)
        if not val.is_valid:
            return ExecutionResult(f"Configuration error: {val.error_message}")

        return await self._execute_radio_map(val.arguments)

    async def _handle_clarification_response(self, text: str) -> ExecutionResult:
        """Applies a clarification answer to pending parameters."""
        param_name = self.context.pending_param_name
        intent = self.context.pending_intent
        params = self.context.pending_params

        is_default = bool(re.search(r"\b(default|keep\s+default|use\s+defaults?|standard|skip)\b", text, re.IGNORECASE) or text == "")

        if intent == IntentType.GENERATE_RADIO_MAP:
            if param_name == "scene_name":
                params["scene_name"] = "simple_reflector" if is_default else (extract_scene_name(text) or text.strip())

                # Check if cell_size is also needed
                if "cell_size" not in params:
                    self.context.set_pending_clarification(
                        intent=IntentType.GENERATE_RADIO_MAP,
                        current_params=params,
                        param_name="cell_size",
                        question="What cell size should I use? (e.g. 5 metres, or 'default' for 1.0m)",
                    )
                    return ExecutionResult("Assistant: What cell size should I use? (e.g. 5 metres, or 'default' for 1.0m)")
            elif param_name == "cell_size":
                if is_default:
                    params["cell_size"] = 1.0
                else:
                    cs = extract_cell_size(text)
                    if cs is None:
                        try:
                            cs = float(re.findall(r"[-+]?\d*\.?\d+", text)[0])
                        except Exception:
                            cs = 1.0
                    params["cell_size"] = cs
            elif param_name == "manual_bounds":
                extra_bounds = extract_all_parameters(text)
                params.update(extra_bounds)

            extra_extracted = extract_all_parameters(text)
            params.update({k: v for k, v in extra_extracted.items() if v is not None and not k.startswith("_")})

            self.context.clear_pending()
            val = validate_radio_map_args(params)
            if not val.is_valid:
                return ExecutionResult(f"Configuration error: {val.error_message}")
            return await self._execute_radio_map(val.arguments)

        elif intent == IntentType.RUN_SIMULATION:
            if param_name in ("tx_position", "rx_position"):
                tx_c, rx_c, all_c = extract_coordinates(text)
                if param_name == "tx_position":
                    params["tx_position"] = tx_c or (all_c[0] if all_c else [0.0, -10.0, 5.0])
                elif param_name == "rx_position":
                    params["rx_position"] = rx_c or (all_c[0] if all_c else [0.0, 10.0, 5.0])

            extra_extracted = extract_all_parameters(text)
            params.update({k: v for k, v in extra_extracted.items() if v is not None and not k.startswith("_")})

            self.context.clear_pending()
            val = validate_simulation_args(params)
            if not val.is_valid:
                return ExecutionResult(f"Configuration error: {val.error_message}")

            ack = format_understanding_acknowledgment("Point-to-point simulation", val.arguments)
            try:
                res = await self.client.call_tool("run_simulation", val.arguments)
                self.context.update_last_simulation(val.arguments, res)
                return ExecutionResult(f"{ack}\n\n{format_simulation_result(res)}")
            except MCPClientError as exc:
                return ExecutionResult(f"Simulation failed: {exc}")

        elif intent == IntentType.COMPARE_EXPERIMENTS:
            if param_name == "experiment_id_a":
                exp_ids = extract_experiment_ids(text)
                if exp_ids:
                    params["experiment_id_a"] = exp_ids[0]
                    if len(exp_ids) >= 2:
                        params["experiment_id_b"] = exp_ids[1]
                else:
                    params["experiment_id_a"] = text.strip()

                if "experiment_id_b" not in params:
                    self.context.set_pending_clarification(
                        intent=IntentType.COMPARE_EXPERIMENTS,
                        current_params=params,
                        param_name="experiment_id_b",
                        question=f"Baseline is set to '{params['experiment_id_a']}'. What is Experiment B?",
                    )
                    return ExecutionResult(f"Assistant: Baseline set to '{params['experiment_id_a']}'. What is Experiment B?")

            elif param_name == "experiment_id_b":
                exp_ids = extract_experiment_ids(text)
                params["experiment_id_b"] = exp_ids[0] if exp_ids else text.strip()

            self.context.clear_pending()
            val = validate_compare_experiments_args(params)
            if not val.is_valid:
                return ExecutionResult(f"Validation error: {val.error_message}")

            try:
                res = await self.client.call_tool("compare_experiments", val.arguments)
                return ExecutionResult(format_comparison_result(res))
            except MCPClientError as exc:
                return ExecutionResult(f"Error comparing experiments: {exc}")

        elif intent == IntentType.GET_EXPERIMENT_DETAILS:
            exp_ids = extract_experiment_ids(text)
            target_id = exp_ids[0] if exp_ids else text.strip()
            self.context.clear_pending()
            try:
                res = await self.client.call_tool("get_experiment_details", {"experiment_id": target_id})
                self.context.last_experiment_id = target_id
                return ExecutionResult(format_experiment_details(res))
            except MCPClientError as exc:
                return ExecutionResult(f"Error retrieving experiment: {exc}")

        self.context.clear_pending()
        return ExecutionResult("Pending question cleared.")

    async def _execute_radio_map(self, args: Dict[str, Any]) -> ExecutionResult:
        """Executes `generate_radio_map` with acknowledgment and updates context."""
        ack = format_understanding_acknowledgment("Radio map generation", args)
        try:
            res = await self.client.call_tool("generate_radio_map", args)
            self.context.update_last_radio_map(args, res)
            result_str = format_radio_map_result(res)
            return ExecutionResult(f"{ack}\n\n{result_str}")
        except MCPClientError as exc:
            return ExecutionResult(f"{ack}\n\nMCP Error: Simulation failed: {exc}")

    async def _execute_tool_and_format(self, tool_name: str, args: Dict[str, Any]) -> ExecutionResult:
        """Executes a confirmed tool."""
        try:
            res = await self.client.call_tool(tool_name, args)
            if tool_name == "generate_radio_map":
                self.context.update_last_radio_map(args, res)
                return ExecutionResult(format_radio_map_result(res))
            elif tool_name == "run_simulation":
                self.context.update_last_simulation(args, res)
                return ExecutionResult(format_simulation_result(res))
            elif tool_name == "compare_experiments":
                return ExecutionResult(format_comparison_result(res))
            return ExecutionResult(json.dumps(res, indent=2))
        except MCPClientError as exc:
            return ExecutionResult(f"Tool execution failed: {exc}")

    def _format_tools_summary(self) -> str:
        """Summarizes all discovered tools and descriptions."""
        lines = [
            f"Registered MCP Tools ({len(self.client.discovered_tools)} total):",
            "-" * 72,
        ]
        for name, tool in self.client.discovered_tools.items():
            desc = getattr(tool, "description", "").strip().split("\n")[0]
            lines.append(f"  • {name:<24} {desc}")
        return "\n".join(lines)

    def _format_context_summary(self) -> str:
        """Displays active session state."""
        lines = [
            "Active Session Context:",
            "-" * 72,
            f"  Last Intent:         {self.context.last_intent or 'None'}",
            f"  Last Experiment ID:  {self.context.last_experiment_id or 'None'}",
            f"  Previous Exp ID:     {self.context.previous_experiment_id or 'None'}",
            f"  Selected Scene:      {self.context.last_selected_scene or 'None'}",
        ]
        if self.context.last_radio_map_config:
            lines.append("  Last Radio Map Configuration:")
            for k in ("scene_name", "frequency_hz", "tx_position", "cell_size", "samples_per_tx", "tx_power_dbm", "antenna_type"):
                if k in self.context.last_radio_map_config:
                    lines.append(f"    - {k}: {self.context.last_radio_map_config[k]}")
        if self.context.last_simulation_config:
            lines.append("  Last Simulation Configuration:")
            for k in ("scene", "frequency_hz", "tx_position", "rx_position", "tx_power_dbm", "antenna_type"):
                if k in self.context.last_simulation_config:
                    lines.append(f"    - {k}: {self.context.last_simulation_config[k]}")
        if self.context.has_pending_clarification():
            lines.append(f"  Pending Question:    {self.context.pending_question}")
        return "\n".join(lines)
