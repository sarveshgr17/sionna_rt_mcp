"""Deterministic, rule-based natural language parser for Sionna RT CLI.

Extracts structured domain parameters (frequencies, 3D Cartesian coordinates,
cell sizes, ray counts, RF powers, antenna modes, arrays, polarizations,
manual region bounds, and experiment IDs) from arbitrary English phrasing
without requiring external LLMs or internet connectivity.
"""

import math
import re
from typing import Any, Dict, List, Optional, Tuple


def extract_frequency(text: str) -> Optional[float]:
    """Extracts carrier frequency in Hertz from natural phrasing.

    Supports:
        - GHz: '3.5 GHz', '3.5GHz', '28 GHz', 'at 3.5 ghz' -> 3.5e9
        - MHz: '700 MHz', '3500 MHz', '3500mhz' -> 3.5e9
        - kHz: '100 kHz' -> 100e3
        - Hz: '3500000000 Hz', '3.5e9 Hz' -> 3.5e9
        - Bare scientific or integer with 'frequency' keyword: 'frequency 3.5e9'

    Returns:
        float: Carrier frequency in Hz, or None if not found.
    """
    # 1. Matches with explicit unit: GHz, MHz, kHz, Hz
    unit_pattern = re.compile(
        r"(\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*(ghz|mhz|khz|hz)\b",
        re.IGNORECASE,
    )
    match = unit_pattern.search(text)
    if match:
        val_str, unit_str = match.groups()
        try:
            val = float(val_str)
            unit = unit_str.lower()
            if unit == "ghz":
                return val * 1e9
            elif unit == "mhz":
                return val * 1e6
            elif unit == "khz":
                return val * 1e3
            elif unit == "hz":
                return val
        except ValueError:
            pass

    # 2. Matches bare frequency with keyword e.g. 'frequency: 3.5e9'
    keyword_pattern = re.compile(
        r"\bfrequency\s*(?:is|of|:)?\s*(\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\b",
        re.IGNORECASE,
    )
    kw_match = keyword_pattern.search(text)
    if kw_match:
        try:
            return float(kw_match.group(1))
        except ValueError:
            pass

    return None


def extract_coordinates(text: str) -> Tuple[Optional[List[float]], Optional[List[float]], List[List[float]]]:
    """Extracts 3D Cartesian coordinates [x, y, z] from text.

    Supports:
        - Bracketed coordinates: [0, -10, 5] or (0, -10, 5)
        - Named coordinates: x=0, y=-10, z=5
        - Tagged coordinates: TX: 0, -10, 5 or Receiver at 0, 10, 1.5

    Returns:
        Tuple of:
            - tx_position: [x, y, z] in meters if recognized as transmitter.
            - rx_position: [x, y, z] in meters if recognized as receiver.
            - all_coords: List of all 3-tuples found in order.
    """
    all_coords: List[List[float]] = []
    tx_pos: Optional[List[float]] = None
    rx_pos: Optional[List[float]] = None

    # 1. Check for x=..., y=..., z=...
    xyz_pattern = re.compile(
        r"\bx\s*=\s*(-?\d+(?:\.\d+)?)[,\s]+y\s*=\s*(-?\d+(?:\.\d+)?)[,\s]+z\s*=\s*(-?\d+(?:\.\d+)?)\b",
        re.IGNORECASE,
    )
    for m in xyz_pattern.finditer(text):
        try:
            c = [float(m.group(1)), float(m.group(2)), float(m.group(3))]
            all_coords.append(c)
            # Check prefix for tx vs rx
            start = m.start()
            prefix = text[max(0, start - 40):start].lower()
            if re.search(r"\b(tx|transmitter|source|base\s*station|bs)\b", prefix):
                tx_pos = c
            elif re.search(r"\b(rx|receiver|target|ue|user)\b", prefix):
                rx_pos = c
        except ValueError:
            continue

    # 2. Check for tagged unbracketed coordinates e.g. "TX coordinates: 0, 0, 10" or "TX: 0, -10, 5"
    tagged_pattern = re.compile(
        r"\b(tx|rx|transmitter|receiver)\s*(?:coordinates?|position|at)?\s*[:=]?\s*(-?\d+(?:\.\d+)?)[,\s]+(-?\d+(?:\.\d+)?)[,\s]+(-?\d+(?:\.\d+)?)\b",
        re.IGNORECASE,
    )
    for m in tagged_pattern.finditer(text):
        tag = m.group(1).lower()
        try:
            c = [float(m.group(2)), float(m.group(3)), float(m.group(4))]
            if c not in all_coords:
                all_coords.append(c)
            if tag in ("tx", "transmitter") and tx_pos is None:
                tx_pos = c
            elif tag in ("rx", "receiver") and rx_pos is None:
                rx_pos = c
        except ValueError:
            continue

    # 3. Check for bracketed coordinates: [x, y, z] or (x, y, z)
    coord_pattern = re.compile(
        r"[\[\(]\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*[\]\)]"
    )
    bracket_matches = list(coord_pattern.finditer(text))
    for m in bracket_matches:
        try:
            c = [float(m.group(1)), float(m.group(2)), float(m.group(3))]
            if c not in all_coords:
                all_coords.append(c)
            start = m.start()
            prefix = text[max(0, start - 40):start].lower()
            suffix = text[m.end():min(len(text), m.end() + 20)].lower()
            context_window = f"{prefix} {suffix}"

            if re.search(r"\b(tx|transmitter|source|base\s*station|bs)\b", context_window) and tx_pos is None:
                tx_pos = c
            elif re.search(r"\b(rx|receiver|target|ue|user)\b", context_window) and rx_pos is None:
                rx_pos = c
        except ValueError:
            continue

    # If coordinates exist but were not tagged:
    if len(all_coords) == 1 and tx_pos is None and rx_pos is None:
        tx_pos = all_coords[0]
    elif len(all_coords) >= 2:
        if tx_pos is None and rx_pos is None:
            tx_pos = all_coords[0]
            rx_pos = all_coords[1]
        elif tx_pos is not None and rx_pos is None:
            for c in all_coords:
                if c != tx_pos:
                    rx_pos = c
                    break
        elif rx_pos is not None and tx_pos is None:
            for c in all_coords:
                if c != rx_pos:
                    tx_pos = c
                    break

    return tx_pos, rx_pos, all_coords


def extract_cell_size(text: str) -> Optional[float]:
    """Extracts grid cell resolution / cell size in meters."""
    patterns = [
        re.compile(
            r"(\d+(?:\.\d+)?)\s*(?:m|meter|meters|metre|metres)?\s*(?:cell\s*size|resolution|grid\s*resolution|grid\s*size)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(?:cell\s*size|resolution|grid\s*resolution|grid\s*size)\s*(?:of|is|:)?\s*(\d+(?:\.\d+)?)\s*(?:m|meter|meters|metre|metres)?\b",
            re.IGNORECASE,
        ),
        re.compile(r"(\d+(?:\.\d+)?)\s*(?:m|meter|meters|metre|metres)\s+grid\b", re.IGNORECASE),
    ]

    for p in patterns:
        m = p.search(text)
        if m:
            try:
                val = float(m.group(1))
                if val > 0:
                    return val
            except ValueError:
                continue

    return None


def extract_samples_per_tx(text: str) -> Optional[int]:
    """Extracts Monte Carlo ray count / samples per transmitter."""
    patterns = [
        re.compile(
            r"(\d[\d,_]*(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*(?:monte\s*carlo\s*)?(?:rays?|samples?(?:\s*per\s*tx)?)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(?:ray\s*budget|ray\s*count|samples_per_tx|sample\s*count)\s*(?:of|is|:)?\s*(\d[\d,_]*(?:\.\d+)?(?:[eE][+-]?\d+)?)\b",
            re.IGNORECASE,
        ),
    ]

    for p in patterns:
        m = p.search(text)
        if m:
            val_str = m.group(1).replace(",", "").replace("_", "")
            try:
                val = float(val_str)
                if val > 0:
                    return int(val)
            except ValueError:
                continue

    return None


def extract_tx_power(text: str) -> Optional[float]:
    """Extracts transmitter power in dBm."""
    patterns = [
        re.compile(r"(-?\d+(?:\.\d+)?)\s*dbm\b", re.IGNORECASE),
        re.compile(
            r"\b(?:tx\s*power|transmitter\s*power|transmit\s*power|power)\s*(?:of|is|:)?\s*(-?\d+(?:\.\d+)?)\s*(?:dbm)?\b",
            re.IGNORECASE,
        ),
    ]

    for p in patterns:
        m = p.search(text)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                continue

    return None


def extract_receiver_height(text: str) -> Optional[float]:
    """Extracts evaluation receiver height in meters."""
    pattern = re.compile(
        r"\b(?:receiver\s*height|rx\s*height|rx_height|receiver\s*plane|height)\s*(?:of|is|:)?\s*(\d+(?:\.\d+)?)\s*(?:m|meter|meters|metre|metres)?\b",
        re.IGNORECASE,
    )
    m = pattern.search(text)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return None


def extract_scene_name(text: str, available_scenes: Optional[List[str]] = None) -> Optional[str]:
    """Extracts geometric scene identifier from text."""
    known = available_scenes or ["simple_reflector", "munich"]

    for scene in known:
        if re.search(rf"\b{re.escape(scene)}\b", text, re.IGNORECASE):
            return scene

    kw_pattern = re.compile(r"\bscene\s*(?:is|name|:)?\s*([a-zA-Z0-9_-]+)\b", re.IGNORECASE)
    m = kw_pattern.search(text)
    if m:
        candidate = m.group(1)
        if candidate.lower() not in ("simple", "3d", "the", "a", "of"):
            return candidate

    return None


def extract_experiment_ids(text: str) -> List[str]:
    """Extracts all experiment identifiers from text."""
    pattern = re.compile(r"\b(experiment_[a-zA-Z0-9_]+)\b", re.IGNORECASE)
    seen = set()
    exp_ids = []
    for m in pattern.finditer(text):
        exp_id = m.group(1)
        if exp_id not in seen:
            seen.add(exp_id)
            exp_ids.append(exp_id)
    return exp_ids


def extract_max_depth(text: str) -> Optional[int]:
    """Extracts maximum ray depth / bounce count."""
    patterns = [
        re.compile(r"\b(?:max\s*depth|depth|max\s*bounces?)\s*(?:of|is|:)?\s*(\d+)\b", re.IGNORECASE),
        re.compile(r"\b(\d+)\s*bounces?\b", re.IGNORECASE),
    ]
    for p in patterns:
        m = p.search(text)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                continue
    return None


def extract_antenna_config(text: str) -> Tuple[Optional[str], Optional[str]]:
    """Extracts antenna radiation pattern and polarization from text.

    Returns:
        Tuple of (antenna_type, polarization)
    """
    antenna_type: Optional[str] = None
    polarization: Optional[str] = None

    if re.search(r"\b(isotropic|omni|omnidirectional)\b", text, re.IGNORECASE):
        antenna_type = "isotropic"
    elif re.search(r"\bdipole\b", text, re.IGNORECASE):
        antenna_type = "dipole"
    elif re.search(r"\bdirectional\b", text, re.IGNORECASE):
        antenna_type = "directional"

    if re.search(r"\b(cross\s*polarization|dual\s*polarization|polarization\s*cross)\b", text, re.IGNORECASE):
        polarization = "cross"
    elif re.search(r"\b(horizontal\s*polarization|horizontal|polarization\s*h)\b", text, re.IGNORECASE):
        polarization = "H"
    elif re.search(r"\b(vertical\s*polarization|vertical|polarization\s*v)\b", text, re.IGNORECASE):
        polarization = "V"

    return antenna_type, polarization


def extract_separate_antennas(text: str) -> Tuple[Optional[str], Optional[str]]:
    """Extracts dedicated TX and RX antenna types if distinctively specified.

    Returns:
        Tuple of (tx_antenna_type, rx_antenna_type)
    """
    tx_antenna_type: Optional[str] = None
    rx_antenna_type: Optional[str] = None

    tx_match = re.search(
        r"\b(?:tx|transmitter)\s*(?:antenna)?\s*(?:is|type|:)?\s*(isotropic|omni|omnidirectional|dipole|directional)\b",
        text,
        re.IGNORECASE,
    )
    if tx_match:
        norm = tx_match.group(1).lower()
        tx_antenna_type = "isotropic" if norm in ("isotropic", "omni", "omnidirectional") else norm

    rx_match = re.search(
        r"\b(?:rx|receiver)\s*(?:antenna)?\s*(?:is|type|:)?\s*(isotropic|omni|omnidirectional|dipole|directional)\b",
        text,
        re.IGNORECASE,
    )
    if rx_match:
        norm = rx_match.group(1).lower()
        rx_antenna_type = "isotropic" if norm in ("isotropic", "omni", "omnidirectional") else norm

    return tx_antenna_type, rx_antenna_type


def extract_array_params(text: str) -> Dict[str, Any]:
    """Extracts antenna array dimensions and element spacings."""
    params: Dict[str, Any] = {}

    # "4x4 array" or "4x2 array"
    grid_m = re.search(r"\b(\d+)\s*[xX]\s*(\d+)\s*(?:antenna\s*)?array\b", text, re.IGNORECASE)
    if grid_m:
        params["num_rows"] = int(grid_m.group(1))
        params["num_cols"] = int(grid_m.group(2))

    # "4 rows", "num_rows: 4"
    rows_m = re.search(r"\b(?:num_rows|rows)\s*(?:is|of|:)?\s*(\d+)\b", text, re.IGNORECASE)
    if rows_m:
        params["num_rows"] = int(rows_m.group(1))

    # "4 columns", "num_cols: 4"
    cols_m = re.search(r"\b(?:num_cols|columns|cols)\s*(?:is|of|:)?\s*(\d+)\b", text, re.IGNORECASE)
    if cols_m:
        params["num_cols"] = int(cols_m.group(1))

    # Spacings
    h_m = re.search(r"\b(?:horizontal\s*spacing|h_spacing)\s*(?:is|of|:)?\s*(\d+(?:\.\d+)?)\b", text, re.IGNORECASE)
    if h_m:
        params["horizontal_spacing"] = float(h_m.group(1))

    v_m = re.search(r"\b(?:vertical\s*spacing|v_spacing)\s*(?:is|of|:)?\s*(\d+(?:\.\d+)?)\b", text, re.IGNORECASE)
    if v_m:
        params["vertical_spacing"] = float(v_m.group(1))

    return params


def extract_manual_region_bounds(text: str) -> Dict[str, Any]:
    """Extracts manual region bounding box parameters (x_min, x_max, y_min, y_max)."""
    bounds: Dict[str, Any] = {}

    if re.search(r"\b(manual\s*region|region\s*mode\s*manual)\b", text, re.IGNORECASE):
        bounds["region_mode"] = "manual"
    elif re.search(r"\b(auto\s*region|automatic\s*region|region\s*mode\s*auto)\b", text, re.IGNORECASE):
        bounds["region_mode"] = "auto"

    x_min_m = re.search(r"\bx_min\s*[:=]?\s*(-?\d+(?:\.\d+)?)\b", text, re.IGNORECASE)
    if x_min_m:
        bounds["x_min"] = float(x_min_m.group(1))
        bounds["region_mode"] = "manual"

    x_max_m = re.search(r"\bx_max\s*[:=]?\s*(-?\d+(?:\.\d+)?)\b", text, re.IGNORECASE)
    if x_max_m:
        bounds["x_max"] = float(x_max_m.group(1))
        bounds["region_mode"] = "manual"

    y_min_m = re.search(r"\by_min\s*[:=]?\s*(-?\d+(?:\.\d+)?)\b", text, re.IGNORECASE)
    if y_min_m:
        bounds["y_min"] = float(y_min_m.group(1))
        bounds["region_mode"] = "manual"

    y_max_m = re.search(r"\by_max\s*[:=]?\s*(-?\d+(?:\.\d+)?)\b", text, re.IGNORECASE)
    if y_max_m:
        bounds["y_max"] = float(y_max_m.group(1))
        bounds["region_mode"] = "manual"

    # "x from -20 to 20"
    x_range_m = re.search(r"\bx\s*(?:from|between)\s*(-?\d+(?:\.\d+)?)\s*(?:to|and)\s*(-?\d+(?:\.\d+)?)\b", text, re.IGNORECASE)
    if x_range_m:
        bounds["x_min"] = float(x_range_m.group(1))
        bounds["x_max"] = float(x_range_m.group(2))
        bounds["region_mode"] = "manual"

    # "y from -30 to 30"
    y_range_m = re.search(r"\by\s*(?:from|between)\s*(-?\d+(?:\.\d+)?)\s*(?:to|and)\s*(-?\d+(?:\.\d+)?)\b", text, re.IGNORECASE)
    if y_range_m:
        bounds["y_min"] = float(y_range_m.group(1))
        bounds["y_max"] = float(y_range_m.group(2))
        bounds["region_mode"] = "manual"

    return bounds


def extract_all_parameters(text: str, available_scenes: Optional[List[str]] = None) -> Dict[str, Any]:
    """Extracts all recognizable radio planning parameters from text."""
    params: Dict[str, Any] = {}

    freq = extract_frequency(text)
    if freq is not None:
        params["frequency_hz"] = freq

    tx_pos, rx_pos, all_coords = extract_coordinates(text)
    if tx_pos is not None:
        params["tx_position"] = tx_pos
    if rx_pos is not None:
        params["rx_position"] = rx_pos
    if all_coords:
        params["_all_coords"] = all_coords

    cell_size = extract_cell_size(text)
    if cell_size is not None:
        params["cell_size"] = cell_size

    samples = extract_samples_per_tx(text)
    if samples is not None:
        params["samples_per_tx"] = samples

    power = extract_tx_power(text)
    if power is not None:
        params["tx_power_dbm"] = power

    height = extract_receiver_height(text)
    if height is not None:
        params["receiver_height"] = height

    scene = extract_scene_name(text, available_scenes)
    if scene is not None:
        params["scene_name"] = scene
        params["scene"] = scene

    exp_ids = extract_experiment_ids(text)
    if exp_ids:
        params["experiment_ids"] = exp_ids
        if len(exp_ids) == 1:
            params["experiment_id"] = exp_ids[0]
        elif len(exp_ids) >= 2:
            params["experiment_id_a"] = exp_ids[0]
            params["experiment_id_b"] = exp_ids[1]

    # Special references to previous experiments
    if re.search(r"\b(previous|last)\s+experiment\b", text, re.IGNORECASE):
        params["_target_previous_experiment"] = True
    if re.search(r"\b(last\s+two\s+(?:radio\s*maps?|maps?|experiments?))\b", text, re.IGNORECASE):
        params["_target_last_two_experiments"] = True
    if re.search(r"\b(this\s+map\s+with\s+(?:my\s+)?previous\s+map)\b", text, re.IGNORECASE):
        params["_target_last_two_experiments"] = True

    max_depth = extract_max_depth(text)
    if max_depth is not None:
        params["max_depth"] = max_depth

    ant_type, pol = extract_antenna_config(text)
    if ant_type is not None:
        params["antenna_type"] = ant_type
    if pol is not None:
        params["polarization"] = pol

    tx_ant, rx_ant = extract_separate_antennas(text)
    if tx_ant is not None:
        params["tx_antenna_type"] = tx_ant
    if rx_ant is not None:
        params["rx_antenna_type"] = rx_ant

    array_params = extract_array_params(text)
    params.update(array_params)

    region_bounds = extract_manual_region_bounds(text)
    params.update(region_bounds)

    return params
