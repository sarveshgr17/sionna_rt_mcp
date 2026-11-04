"""Parameter and schema validator for Sionna RT MCP tool invocations.

Validates extracted parameters against tool schemas, checks coordinate dimensions
and value bounds, and identifies missing parameters requiring multi-turn user clarification.
"""

import math
from typing import Any, Dict, List, Optional, Tuple
from src.terminal_agent.intent import IntentType


class ValidationResult:
    """Outcome of validating intent and parameters."""

    def __init__(
        self,
        is_valid: bool,
        tool_name: str,
        arguments: Dict[str, Any],
        needs_clarification: bool = False,
        missing_param: Optional[str] = None,
        clarification_prompt: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        self.is_valid = is_valid
        self.tool_name = tool_name
        self.arguments = arguments
        self.needs_clarification = needs_clarification
        self.missing_param = missing_param
        self.clarification_prompt = clarification_prompt
        self.error_message = error_message


VALID_ANTENNAS = {"isotropic", "iso", "omni", "omnidirectional", "dipole", "hw_dipole", "directional", "tr38901"}
VALID_POLARIZATIONS = {"V", "H", "VH", "CROSS"}

# Canonical default configurations matching MCP server definitions
DEFAULT_RADIO_MAP_CONFIG: Dict[str, Any] = {
    "scene_name": "simple_reflector",
    "frequency_hz": 3.5e9,
    "tx_name": "tx",
    "tx_position": [0.0, -10.0, 5.0],
    "tx_power_dbm": 30.0,
    "tx_orientation_deg": [0.0, 0.0, 0.0],
    "antenna_type": "isotropic",
    "polarization": "V",
    "num_rows": 1,
    "num_cols": 1,
    "horizontal_spacing": 0.5,
    "vertical_spacing": 0.5,
    "region_mode": "auto",
    "auto_margin": 5.0,
    "auto_include_tx": True,
    "receiver_height": 1.5,
    "cell_size": 1.0,
    "samples_per_tx": 1_000_000,
    "max_depth": 3,
    "los": True,
    "specular_reflection": True,
    "diffraction": True,
    "scattering": False,
}

DEFAULT_SIMULATION_CONFIG: Dict[str, Any] = {
    "scene": "simple_reflector",
    "frequency_hz": 3.5e9,
    "tx_position": [0.0, -10.0, 5.0],
    "rx_position": [0.0, 10.0, 5.0],
    "tx_power_dbm": 30.0,
    "antenna_type": "isotropic",
    "polarization": "V",
    "num_rows": 1,
    "num_cols": 1,
    "horizontal_spacing": 0.5,
    "vertical_spacing": 0.5,
}


def validate_coordinates(coords: Any, name: str = "coordinates") -> Tuple[bool, Optional[str]]:
    """Verifies that coordinates are a 3-element list of numbers."""
    if not isinstance(coords, (list, tuple)) or len(coords) != 3:
        return False, f"{name} must contain exactly 3 coordinates [x, y, z]."
    for v in coords:
        if not isinstance(v, (int, float)) or math.isnan(v) or math.isinf(v):
            return False, f"All coordinates in {name} must be numeric values."
    return True, None


def validate_radio_map_args(
    params: Dict[str, Any],
    require_interactive_clarification: bool = False,
    known_scenes: Optional[List[str]] = None,
) -> ValidationResult:
    """Validates parameters for the `generate_radio_map` tool."""
    tool_name = "generate_radio_map"
    args = dict(DEFAULT_RADIO_MAP_CONFIG)
    args.update({k: v for k, v in params.items() if v is not None and not k.startswith("_")})

    # Value checks
    if args["frequency_hz"] <= 0:
        return ValidationResult(
            is_valid=False,
            tool_name=tool_name,
            arguments={},
            error_message="Frequency must be strictly greater than 0 Hz.",
        )

    ok, err = validate_coordinates(args["tx_position"], "tx_position")
    if not ok:
        return ValidationResult(
            is_valid=False,
            tool_name=tool_name,
            arguments={},
            error_message=err,
        )

    # Antenna check
    ant = str(args.get("antenna_type", "isotropic")).lower()
    if ant not in VALID_ANTENNAS:
        return ValidationResult(
            is_valid=False,
            tool_name=tool_name,
            arguments={},
            error_message=f"Unsupported antenna type '{args.get('antenna_type')}'. Supported: 'isotropic', 'dipole', 'directional'.",
        )

    cell_size = args["cell_size"]
    if isinstance(cell_size, (int, float)):
        if cell_size <= 0:
            return ValidationResult(
                is_valid=False,
                tool_name=tool_name,
                arguments={},
                error_message="Cell size must be greater than 0 meters.",
            )
        args["cell_size"] = float(cell_size)
    elif isinstance(cell_size, (list, tuple)):
        if len(cell_size) != 2 or any(x <= 0 for x in cell_size):
            return ValidationResult(
                is_valid=False,
                tool_name=tool_name,
                arguments={},
                error_message="Cell size sequence must be [dx, dy] with positive numbers.",
            )

    if args["samples_per_tx"] < 100:
        return ValidationResult(
            is_valid=False,
            tool_name=tool_name,
            arguments={},
            error_message="Samples per transmitter must be at least 100 rays.",
        )

    # Manual region verification
    if args.get("region_mode") == "manual":
        for b_name in ("x_min", "x_max", "y_min", "y_max"):
            if b_name not in args or args[b_name] is None:
                return ValidationResult(
                    is_valid=False,
                    tool_name=tool_name,
                    arguments=args,
                    needs_clarification=True,
                    missing_param="manual_bounds",
                    clarification_prompt=f"Manual region selected. Please specify {b_name} in meters.",
                )
        if args["x_min"] >= args["x_max"]:
            return ValidationResult(
                is_valid=False,
                tool_name=tool_name,
                arguments={},
                error_message=f"Invalid bounds: x_min ({args['x_min']}) must be strictly less than x_max ({args['x_max']}).",
            )
        if args["y_min"] >= args["y_max"]:
            return ValidationResult(
                is_valid=False,
                tool_name=tool_name,
                arguments={},
                error_message=f"Invalid bounds: y_min ({args['y_min']}) must be strictly less than y_max ({args['y_max']}).",
            )

    # Convert coordinates to list of floats
    args["tx_position"] = [float(x) for x in args["tx_position"]]

    return ValidationResult(
        is_valid=True,
        tool_name=tool_name,
        arguments=args,
    )


def validate_simulation_args(
    params: Dict[str, Any],
    require_both_coordinates: bool = True,
) -> ValidationResult:
    """Validates parameters for the point-to-point `run_simulation` tool."""
    tool_name = "run_simulation"
    args = dict(DEFAULT_SIMULATION_CONFIG)
    args.update({k: v for k, v in params.items() if v is not None and not k.startswith("_")})

    # If scene_name was extracted, map to scene
    if "scene_name" in params and "scene" not in params:
        args["scene"] = params["scene_name"]

    # Check for missing coordinates when requested directly in prompt without context
    if require_both_coordinates:
        if "tx_position" not in params:
            return ValidationResult(
                is_valid=False,
                tool_name=tool_name,
                arguments=args,
                needs_clarification=True,
                missing_param="tx_position",
                clarification_prompt="Please specify the transmitter coordinates [x, y, z] in meters.",
            )
        if "rx_position" not in params:
            return ValidationResult(
                is_valid=False,
                tool_name=tool_name,
                arguments=args,
                needs_clarification=True,
                missing_param="rx_position",
                clarification_prompt="Please specify the receiver coordinates [x, y, z] in meters.",
            )

    if args["frequency_hz"] <= 0:
        return ValidationResult(
            is_valid=False,
            tool_name=tool_name,
            arguments={},
            error_message="Frequency must be strictly greater than 0 Hz.",
        )

    ok, err = validate_coordinates(args["tx_position"], "tx_position")
    if not ok:
        return ValidationResult(
            is_valid=False,
            tool_name=tool_name,
            arguments={},
            error_message=err,
        )

    ok, err = validate_coordinates(args["rx_position"], "rx_position")
    if not ok:
        return ValidationResult(
            is_valid=False,
            tool_name=tool_name,
            arguments={},
            error_message=err,
        )

    # Validate antenna patterns
    ant = str(args.get("antenna_type", "isotropic")).lower()
    if ant not in VALID_ANTENNAS:
        return ValidationResult(
            is_valid=False,
            tool_name=tool_name,
            arguments={},
            error_message=f"Unsupported antenna type '{args.get('antenna_type')}'. Supported: 'isotropic', 'dipole', 'directional'.",
        )

    if "tx_antenna_type" in args and args["tx_antenna_type"]:
        t_ant = str(args["tx_antenna_type"]).lower()
        if t_ant not in VALID_ANTENNAS:
            return ValidationResult(
                is_valid=False,
                tool_name=tool_name,
                arguments={},
                error_message=f"Unsupported TX antenna type '{args['tx_antenna_type']}'. Supported: 'isotropic', 'dipole', 'directional'.",
            )

    if "rx_antenna_type" in args and args["rx_antenna_type"]:
        r_ant = str(args["rx_antenna_type"]).lower()
        if r_ant not in VALID_ANTENNAS:
            return ValidationResult(
                is_valid=False,
                tool_name=tool_name,
                arguments={},
                error_message=f"Unsupported RX antenna type '{args['rx_antenna_type']}'. Supported: 'isotropic', 'dipole', 'directional'.",
            )

    pol = str(args.get("polarization", "V")).upper()
    if pol not in VALID_POLARIZATIONS:
        return ValidationResult(
            is_valid=False,
            tool_name=tool_name,
            arguments={},
            error_message=f"Unsupported polarization '{args.get('polarization')}'. Supported: 'V', 'H', 'VH', 'cross'.",
        )

    args["tx_position"] = [float(x) for x in args["tx_position"]]
    args["rx_position"] = [float(x) for x in args["rx_position"]]
    args["frequency_hz"] = float(args["frequency_hz"])
    args["tx_power_dbm"] = float(args["tx_power_dbm"])

    return ValidationResult(
        is_valid=True,
        tool_name=tool_name,
        arguments=args,
    )


def validate_get_experiment_args(params: Dict[str, Any], last_exp_id: Optional[str] = None) -> ValidationResult:
    """Validates parameters for `get_experiment_details`."""
    tool_name = "get_experiment_details"
    exp_id = params.get("experiment_id") or last_exp_id

    if not exp_id:
        return ValidationResult(
            is_valid=False,
            tool_name=tool_name,
            arguments={},
            needs_clarification=True,
            missing_param="experiment_id",
            clarification_prompt="Which experiment ID would you like to view? (e.g. experiment_20261101_...)",
        )

    return ValidationResult(
        is_valid=True,
        tool_name=tool_name,
        arguments={"experiment_id": str(exp_id).strip()},
    )


def validate_compare_experiments_args(
    params: Dict[str, Any],
    last_exp_id: Optional[str] = None,
    previous_exp_id: Optional[str] = None,
) -> ValidationResult:
    """Validates parameters for `compare_experiments`."""
    tool_name = "compare_experiments"
    exp_a = params.get("experiment_id_a")
    exp_b = params.get("experiment_id_b")

    # If user provided a list of experiment IDs
    ids = params.get("experiment_ids", [])
    if len(ids) >= 2:
        exp_a, exp_b = ids[0], ids[1]
    elif len(ids) == 1 and not exp_a:
        exp_a = ids[0]

    # If user requested to compare "last two" or "with previous"
    if params.get("_target_last_two_experiments"):
        if previous_exp_id and last_exp_id:
            exp_a = previous_exp_id
            exp_b = last_exp_id
        elif last_exp_id:
            exp_a = last_exp_id

    # If only one ID exists and no second is specified, check context
    if exp_a and not exp_b and last_exp_id and exp_a != last_exp_id:
        exp_b = last_exp_id

    if not exp_a and not exp_b:
        if previous_exp_id and last_exp_id:
            exp_a = previous_exp_id
            exp_b = last_exp_id
        else:
            return ValidationResult(
                is_valid=False,
                tool_name=tool_name,
                arguments={},
                needs_clarification=True,
                missing_param="experiment_id_a",
                clarification_prompt="Please provide the baseline Experiment A identifier to compare.",
            )

    if exp_a and not exp_b:
        return ValidationResult(
            is_valid=False,
            tool_name=tool_name,
            arguments={"experiment_id_a": exp_a},
            needs_clarification=True,
            missing_param="experiment_id_b",
            clarification_prompt=f"Comparing against baseline '{exp_a}'. What is the second experiment ID (Experiment B)?",
        )

    return ValidationResult(
        is_valid=True,
        tool_name=tool_name,
        arguments={
            "experiment_id_a": str(exp_a).strip(),
            "experiment_id_b": str(exp_b).strip(),
            "generate_heatmaps": True,
        },
    )
