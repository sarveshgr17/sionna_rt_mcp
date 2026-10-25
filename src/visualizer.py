"""Visualization generator for Sionna RT simulations and wireless channel analysis."""

import math
import os
from typing import Any, Dict, List, Optional

import matplotlib
matplotlib.use("Agg")  # Non-interactive headless backend
import matplotlib.pyplot as plt

try:
    from src.storage import SimulationStorage
except ImportError:
    from storage import SimulationStorage


class Visualizer:
    """Generates scientifically readable, deterministic plots for Sionna RT simulations."""

    def __init__(self, storage: Optional[SimulationStorage] = None) -> None:
        self.storage = storage or SimulationStorage()

    def plot_propagation_paths(self, sim_data: Dict[str, Any], output_path: str) -> str:
        """Plot the 2D top-down geometric propagation ray paths between TX and RX.

        Shows TX position, RX position, planar reflector surface, and traced multipath rays.
        """
        sim = sim_data.get("simulation", {})
        tx_pos = sim.get("tx_position", [0.0, -10.0, 5.0])
        rx_pos = sim.get("rx_position", [0.0, 10.0, 5.0])
        delays = sim.get("delays_ns", sim.get("path_delays", []))
        gains = sim.get("path_gains_db", sim.get("path_gains", []))
        itypes = sim.get("interaction_types", [])
        freq_ghz = sim.get("frequency_hz", 3.5e9) / 1e9

        fig, ax = plt.subplots(figsize=(9, 7), dpi=150)

        # Plot Reflector Wall (for simple_reflector geometry, reflector plane is at x=5.0)
        reflector_x = 5.0
        reflector_y_span = [-15.0, 15.0]
        ax.plot(
            [reflector_x, reflector_x],
            reflector_y_span,
            color="#4A5568",
            linewidth=4,
            linestyle="-",
            label="Planar Reflector (x = 5.0 m)",
            zorder=2,
        )

        # Plot Transmitter and Receiver
        ax.scatter(
            [tx_pos[0]],
            [tx_pos[1]],
            color="#E53E3E",
            s=120,
            marker="s",
            label=f"TX ({tx_pos[0]:.1f}, {tx_pos[1]:.1f}, {tx_pos[2]:.1f}) m",
            zorder=5,
        )
        ax.scatter(
            [rx_pos[0]],
            [rx_pos[1]],
            color="#3182CE",
            s=120,
            marker="^",
            label=f"RX ({rx_pos[0]:.1f}, {rx_pos[1]:.1f}, {rx_pos[2]:.1f}) m",
            zorder=5,
        )

        # Plot Individual Multipath Rays
        colors = ["#38A169", "#DD6B20", "#805AD5", "#D69E2E"]
        num_paths = len(delays)

        for i in range(num_paths):
            delay = delays[i] if i < len(delays) else 0.0
            gain = gains[i] if i < len(gains) else 0.0
            itype = itypes[i] if i < len(itypes) else "Path"
            color = colors[i % len(colors)]

            if "line of sight" in itype.lower() or "los" in itype.lower():
                # Direct Line of Sight ray: TX -> RX
                ax.plot(
                    [tx_pos[0], rx_pos[0]],
                    [tx_pos[1], rx_pos[1]],
                    color=color,
                    linewidth=2.2,
                    linestyle="-",
                    label=f"Path #{i+1}: {itype} ({delay:.1f} ns, {gain:.1f} dB)",
                    zorder=3,
                )
            else:
                # Specular Reflection ray: TX -> Reflection Point (5.0, 0.0) -> RX
                bounce_point = [5.0, 0.0]
                ax.plot(
                    [tx_pos[0], bounce_point[0], rx_pos[0]],
                    [tx_pos[1], bounce_point[1], rx_pos[1]],
                    color=color,
                    linewidth=2.0,
                    linestyle="--",
                    label=f"Path #{i+1}: {itype} ({delay:.1f} ns, {gain:.1f} dB)",
                    zorder=3,
                )

        if num_paths == 0:
            ax.text(
                0.5,
                0.5,
                "No propagation paths detected",
                ha="center",
                va="center",
                transform=ax.transAxes,
                fontsize=11,
                color="#E53E3E",
                bbox=dict(boxstyle="round,pad=0.5", facecolor="#FFF5F5", edgecolor="#FEB2B2"),
            )

        ax.set_title(
            f"Multipath Propagation Geometry ({freq_ghz:.1f} GHz)\nScene: {sim.get('scene_name', 'simple_reflector')}",
            fontsize=13,
            fontweight="bold",
            pad=12,
        )
        ax.set_xlabel("X Position (meters)", fontsize=11)
        ax.set_ylabel("Y Position (meters)", fontsize=11)
        ax.set_xlim(-5.0, 10.0)
        ax.set_ylim(-18.0, 18.0)
        ax.grid(True, linestyle=":", alpha=0.6)
        if num_paths > 0:
            ax.legend(loc="upper left", framealpha=0.9, fontsize=9)
        fig.tight_layout()

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        fig.savefig(output_path, dpi=150)
        plt.close(fig)
        return output_path

    def plot_received_power(self, sim_data: Dict[str, Any], output_path: str) -> str:
        """Plot the link power budget and path attenuation breakdown."""
        sim = sim_data.get("simulation", {})
        tx_pwr = sim.get("tx_power_dbm", 30.0)
        path_loss = sim.get("total_path_loss", sim.get("total_path_loss_db", 0.0))
        rx_pwr = sim.get("received_power", sim.get("received_power_dbm", 0.0))
        freq_ghz = sim.get("frequency_hz", 3.5e9) / 1e9

        fig, ax = plt.subplots(figsize=(8, 6), dpi=150)

        categories = ["TX Power\n(dBm)", "Total Path Loss\n(dB)", "Received Power\n(dBm)"]
        values = [tx_pwr, path_loss, rx_pwr]
        bar_colors = ["#3182CE", "#E53E3E", "#38A169"]

        bars = ax.bar(categories, values, color=bar_colors, width=0.5, edgecolor="#2D3748", linewidth=1.2)

        # Annotate bar values
        for bar, val in zip(bars, values):
            y_pos = bar.get_height()
            offset = 2.5 if y_pos >= 0 else -6.0
            ax.annotate(
                f"{val:.2f}",
                xy=(bar.get_x() + bar.get_width() / 2, y_pos + offset),
                ha="center",
                va="center",
                fontsize=11,
                fontweight="bold",
            )

        ax.axhline(0, color="#718096", linewidth=0.8, linestyle="--")
        ax.set_title(
            f"Wireless Link Power Budget ({freq_ghz:.1f} GHz)\nScene: {sim.get('scene_name', 'simple_reflector')}",
            fontsize=13,
            fontweight="bold",
            pad=12,
        )
        ax.set_ylabel("Power / Loss Level", fontsize=11)
        ax.grid(axis="y", linestyle=":", alpha=0.6)

        # Set readable scale with padding
        y_min = min(min(values) - 15.0, -50.0)
        y_max = max(max(values) + 15.0, 80.0)
        ax.set_ylim(y_min, y_max)
        fig.tight_layout()

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        fig.savefig(output_path, dpi=150)
        plt.close(fig)
        return output_path

    def plot_cir(self, sim_data: Dict[str, Any], output_path: str) -> str:
        """Plot the Channel Impulse Response (CIR) showing path delays and power gains."""
        sim = sim_data.get("simulation", {})
        analysis = sim_data.get("analysis") or {}

        delays = sim.get("delays_ns", sim.get("path_delays", []))
        gains = sim.get("path_gains_db", sim.get("path_gains", []))
        itypes = sim.get("interaction_types", [])
        freq_ghz = sim.get("frequency_hz", 3.5e9) / 1e9

        fig, ax = plt.subplots(figsize=(9, 6), dpi=150)

        baseline_gain = -100.0  # Reference baseline in dB for CIR stem plot

        if delays:
            stems = ax.stem(
                delays,
                gains,
                bottom=baseline_gain,
                linefmt="C0-",
                markerfmt="C0o",
                basefmt="k-",
            )
            plt.setp(stems.stemlines, linewidth=2.0, color="#2B6CB0")
            plt.setp(stems.markerline, markersize=8, color="#2B6CB0")

            # Annotate individual path interaction types and values
            for i, (d, g) in enumerate(zip(delays, gains)):
                itype = itypes[i] if i < len(itypes) else f"Path #{i+1}"
                ax.annotate(
                    f"Path #{i+1}: {itype}\n{g:.2f} dB @ {d:.2f} ns",
                    xy=(d, g),
                    xytext=(d + 1.2, g + 2.5),
                    arrowprops=dict(arrowstyle="->", color="#4A5568", lw=0.8),
                    fontsize=9,
                    fontweight="medium",
                )

        ax.set_title(
            f"Channel Impulse Response (CIR) - {freq_ghz:.1f} GHz\nScene: {sim.get('scene_name', 'simple_reflector')}",
            fontsize=13,
            fontweight="bold",
            pad=12,
        )
        ax.set_xlabel("Propagation Delay (ns)", fontsize=11)
        ax.set_ylabel("Path Gain (dB)", fontsize=11)

        if delays:
            x_min = max(0.0, min(delays) - 10.0)
            x_max = max(delays) + 20.0
            ax.set_xlim(x_min, x_max)
            ax.set_ylim(baseline_gain - 5.0, max(gains) + 12.0)
        else:
            ax.set_xlim(0, 100)
            ax.set_ylim(-105, 0)
            ax.text(
                0.5,
                0.5,
                "No paths detected in Channel Impulse Response",
                ha="center",
                va="center",
                transform=ax.transAxes,
                fontsize=11,
                color="#718096",
                bbox=dict(boxstyle="round,pad=0.5", facecolor="#EDF2F7", edgecolor="#CBD5E0"),
            )

        # Summary annotation box
        rms_ds = analysis.get("rms_delay_spread_ns", 0.0)
        path_loss = sim.get("total_path_loss", sim.get("total_path_loss_db", 0.0))
        summary_text = (
            f"Paths: {len(delays)}\n"
            f"Path Loss: {path_loss:.2f} dB\n"
            f"RMS Delay Spread: {rms_ds:.2f} ns"
        )
        ax.text(
            0.03,
            0.92,
            summary_text,
            transform=ax.transAxes,
            fontsize=9.5,
            verticalalignment="top",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="#EDF2F7", edgecolor="#CBD5E0"),
        )

        ax.grid(True, linestyle=":", alpha=0.6)
        fig.tight_layout()

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        fig.savefig(output_path, dpi=150)
        plt.close(fig)
        return output_path

    def plot_comparison(
        self,
        sim_data_1: Dict[str, Any],
        sim_data_2: Dict[str, Any],
        output_path: str,
    ) -> str:
        """Plot a dual-panel scenario comparison comparing propagation at two frequencies."""
        sim1 = sim_data_1.get("simulation", {})
        sim2 = sim_data_2.get("simulation", {})

        freq1_ghz = sim1.get("frequency_hz", 3.5e9) / 1e9
        freq2_ghz = sim2.get("frequency_hz", 28.0e9) / 1e9

        pl1 = sim1.get("total_path_loss", sim1.get("total_path_loss_db", 0.0))
        pl2 = sim2.get("total_path_loss", sim2.get("total_path_loss_db", 0.0))
        rx1 = sim1.get("received_power", sim1.get("received_power_dbm", 0.0))
        rx2 = sim2.get("received_power", sim2.get("received_power_dbm", 0.0))

        delays1 = sim1.get("delays_ns", sim1.get("path_delays", []))
        gains1 = sim1.get("path_gains_db", sim1.get("path_gains", []))

        delays2 = sim2.get("delays_ns", sim2.get("path_delays", []))
        gains2 = sim2.get("path_gains_db", sim2.get("path_gains", []))

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6), dpi=150)

        # Panel 1: Bar comparison of Path Loss & Received Power
        import numpy as np
        metrics_labels = ["Total Path Loss (dB)", "Received Power (dBm)"]
        x = np.arange(len(metrics_labels))
        width = 0.35

        vals1 = [pl1, rx1]
        vals2 = [pl2, rx2]

        bars1 = ax1.bar(x - width / 2, vals1, width, label=f"{freq1_ghz:.1f} GHz", color="#3182CE")
        bars2 = ax1.bar(x + width / 2, vals2, width, label=f"{freq2_ghz:.1f} GHz", color="#DD6B20")

        # Value labels
        for bar in bars1:
            h = bar.get_height()
            ax1.annotate(f"{h:.1f}", xy=(bar.get_x() + bar.get_width() / 2, h + (2 if h >= 0 else -5)),
                         ha="center", fontsize=10, fontweight="bold")
        for bar in bars2:
            h = bar.get_height()
            ax1.annotate(f"{h:.1f}", xy=(bar.get_x() + bar.get_width() / 2, h + (2 if h >= 0 else -5)),
                         ha="center", fontsize=10, fontweight="bold")

        ax1.axhline(0, color="#718096", linewidth=0.8, linestyle="--")
        ax1.set_title("Power & Attenuation Comparison", fontsize=12, fontweight="bold")
        ax1.set_xticks(x)
        ax1.set_xticklabels(metrics_labels, fontsize=10)
        ax1.set_ylabel("Level (dB / dBm)", fontsize=11)
        ax1.grid(axis="y", linestyle=":", alpha=0.6)
        ax1.legend(loc="upper right", fontsize=10)
        ax1.set_ylim(-70, 100)

        # Panel 2: Channel Impulse Response Comparison
        baseline = -110.0
        if delays1:
            ax2.stem(
                [d - 0.3 for d in delays1],
                gains1,
                bottom=baseline,
                linefmt="C0-",
                markerfmt="C0o",
                basefmt="k-",
                label=f"{freq1_ghz:.1f} GHz CIR",
            )
        if delays2:
            ax2.stem(
                [d + 0.3 for d in delays2],
                gains2,
                bottom=baseline,
                linefmt="C1--",
                markerfmt="C1s",
                basefmt="k-",
                label=f"{freq2_ghz:.1f} GHz CIR",
            )

        ax2.set_title("Multipath Channel Impulse Response Comparison", fontsize=12, fontweight="bold")
        ax2.set_xlabel("Delay (ns)", fontsize=11)
        ax2.set_ylabel("Path Gain (dB)", fontsize=11)
        all_delays = list(delays1) + list(delays2)
        all_gains = list(gains1) + list(gains2)
        if all_delays and all_gains:
            ax2.set_xlim(min(all_delays) - 8, max(all_delays) + 12)
            ax2.set_ylim(baseline - 5, max(all_gains) + 12)
        else:
            ax2.set_xlim(0, 100)
            ax2.set_ylim(baseline - 5, 0)
            ax2.text(
                0.5,
                0.5,
                "No paths detected for comparison",
                ha="center",
                va="center",
                transform=ax2.transAxes,
                fontsize=11,
                color="#718096",
            )
        ax2.grid(True, linestyle=":", alpha=0.6)
        ax2.legend(loc="upper right", fontsize=10)

        delta_pl = pl2 - pl1
        fig.suptitle(
            f"Frequency Scaling Comparison: {freq1_ghz:.1f} GHz vs {freq2_ghz:.1f} GHz "
            f"(Δ Path Loss = +{delta_pl:.1f} dB at 28 GHz)",
            fontsize=13,
            fontweight="bold",
            y=0.98,
        )
        fig.tight_layout()

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        fig.savefig(output_path, dpi=150)
        plt.close(fig)
        return output_path

    def generate_plots(
        self,
        simulation_id: str,
        plot_type: str = "all",
        comparison_simulation_id: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """Generate requested plots for a given simulation ID.

        Args:
            simulation_id: Unique identifier of the simulation.
            plot_type: One of 'all', 'propagation_paths', 'received_power', 'cir', 'comparison'.
            comparison_simulation_id: Optional second simulation ID for comparison.

        Returns:
            list of dicts containing 'plot_type' and 'file_path'.
        """
        valid_types = {"all", "propagation_paths", "received_power", "cir", "comparison"}
        if plot_type not in valid_types:
            raise ValueError(
                f"Unsupported plot type '{plot_type}'. Supported: {', '.join(sorted(valid_types))}"
            )

        sim_data = self.storage.load(simulation_id)
        sim_dir = self.storage.get_simulation_dir(simulation_id)
        generated: List[Dict[str, str]] = []

        if plot_type in ("all", "propagation_paths"):
            out_file = os.path.join(sim_dir, "propagation_paths.png")
            self.plot_propagation_paths(sim_data, out_file)
            generated.append({"plot_type": "propagation_paths", "file_path": out_file})

        if plot_type in ("all", "received_power"):
            out_file = os.path.join(sim_dir, "received_power.png")
            self.plot_received_power(sim_data, out_file)
            generated.append({"plot_type": "received_power", "file_path": out_file})

        if plot_type in ("all", "cir"):
            out_file = os.path.join(sim_dir, "cir.png")
            self.plot_cir(sim_data, out_file)
            generated.append({"plot_type": "cir", "file_path": out_file})

        if plot_type == "comparison":
            if not comparison_simulation_id:
                raise ValueError("comparison_simulation_id is required when plot_type='comparison'.")
            sim_data_2 = self.storage.load(comparison_simulation_id)
            out_file = os.path.join(sim_dir, "comparison.png")
            self.plot_comparison(sim_data, sim_data_2, out_file)
            generated.append({"plot_type": "comparison", "file_path": out_file})

        return generated
