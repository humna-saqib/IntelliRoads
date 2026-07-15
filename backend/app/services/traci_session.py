"""
IntelliRoads – TraCI session manager.

Wraps the SUMO TraCI API and provides transparent MOCK mode when SUMO
is not installed so the REST/WebSocket backend can run standalone.
"""

from __future__ import annotations

import os
import random
import subprocess
import time
from pathlib import Path
from typing import Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Optional TraCI import – graceful fallback to MOCK mode
# ---------------------------------------------------------------------------
try:
    import traci  # type: ignore
    import sumolib  # type: ignore

    SUMO_AVAILABLE: bool = True
    logger.info("TraCI / SUMO libraries detected – LIVE mode available.")
except ImportError:
    SUMO_AVAILABLE = False
    logger.warning(
        "TraCI / SUMO libraries NOT found.  "
        "TraCISession will operate in MOCK mode."
    )


class TraCISession:
    """
    Manages the lifecycle of a TraCI connection to a running SUMO process.

    If SUMO is not installed (``SUMO_AVAILABLE is False``), the session
    enters *mock* mode: ``start()`` and ``step()`` succeed immediately,
    and helper methods return plausible fake data so the frontend works
    without any SUMO installation.

    Parameters
    ----------
    config_path : str | Path
        Path to the ``.sumocfg`` configuration file.
    host : str
        Hostname for the TraCI TCP connection (default ``'localhost'``).
    port : int
        Port for the TraCI TCP connection (default ``8813``).
    step_length : float
        Simulation step length in seconds (default ``1.0``).
    """

    def __init__(
        self,
        config_path: str | Path,
        host: str = "localhost",
        port: int = 8813,
        step_length: float = 1.0,
    ) -> None:
        self.config_path: Path = Path(config_path)
        self.host: str = host
        self.port: int = port
        self.step_length: float = step_length

        self._process: Optional[subprocess.Popen] = None  # type: ignore[type-arg]
        self._connected: bool = False
        self._sim_time: float = 0.0
        self._mock_mode: bool = not SUMO_AVAILABLE

        if self._mock_mode:
            logger.warning(
                "TraCISession initialised in MOCK mode – "
                "no real SUMO process will be spawned."
            )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def start(self) -> None:
        """
        Launch the SUMO subprocess and connect via TraCI.

        In mock mode this is a no-op (just sets the connected flag).

        Raises
        ------
        FileNotFoundError
            If the SUMO binary or config file cannot be located.
        ConnectionRefusedError
            If TraCI cannot connect within the expected window.
        """
        if self._mock_mode:
            logger.info("MOCK start() – skipping SUMO subprocess launch.")
            self._connected = True
            self._sim_time = 0.0
            return

        if not self.config_path.exists():
            raise FileNotFoundError(
                f"SUMO config file not found: {self.config_path}"
            )

        sumo_binary: str = self._find_sumo_binary()

        cmd = [
            sumo_binary,
            "-c", str(self.config_path),
            "--remote-port", str(self.port),
            "--step-length", str(self.step_length),
            "--no-step-log", "true",
            "--verbose", "false",
        ]

        logger.info(f"Spawning SUMO: {' '.join(cmd)}")
        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                f"SUMO binary '{sumo_binary}' not found on PATH."
            ) from exc

        # Give SUMO a moment to open the TraCI socket
        time.sleep(1.5)

        try:
            traci.init(port=self.port, host=self.host)
            self._connected = True
            self._sim_time = traci.simulation.getTime()
            logger.info(
                f"TraCI connected on {self.host}:{self.port}  "
                f"sim_time={self._sim_time:.1f}s"
            )
        except ConnectionRefusedError as exc:
            self._terminate_process()
            raise ConnectionRefusedError(
                f"TraCI could not connect to SUMO on "
                f"{self.host}:{self.port}.  Is SUMO running?"
            ) from exc

    def step(self) -> float:
        """
        Advance the simulation by one step.

        Returns
        -------
        float
            The new simulation time in seconds.
        """
        if self._mock_mode:
            self._sim_time += self.step_length
            return self._sim_time

        if not self._connected:
            logger.warning("step() called while not connected – returning cached time.")
            return self._sim_time

        try:
            traci.simulationStep()
            self._sim_time = traci.simulation.getTime()
        except Exception as exc:  # noqa: BLE001
            logger.error(f"TraCI step() error: {exc}")
            self._connected = False

        return self._sim_time

    def close(self) -> None:
        """Close the TraCI connection and terminate the SUMO subprocess."""
        if self._mock_mode:
            logger.info("MOCK close() – nothing to tear down.")
            self._connected = False
            return

        if self._connected:
            try:
                traci.close()
                logger.info("TraCI connection closed.")
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Error while closing TraCI: {exc}")
            finally:
                self._connected = False

        self._terminate_process()

    def is_connected(self) -> bool:
        """Return ``True`` if the session is active (including mock mode)."""
        return self._connected

    def get_simulation_time(self) -> float:
        """Return the current simulation time in seconds."""
        if not self._mock_mode and self._connected:
            try:
                self._sim_time = traci.simulation.getTime()
            except Exception:  # noqa: BLE001
                pass
        return self._sim_time

    # ------------------------------------------------------------------
    # Mock helpers – used by VehicleDataService when SUMO not available
    # ------------------------------------------------------------------

    @property
    def mock_mode(self) -> bool:
        """``True`` when SUMO is not available or connection is closed."""
        return self._mock_mode or not self._connected

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_sumo_binary() -> str:
        """Locate the SUMO binary from the SUMO_HOME env variable or PATH."""
        binary_override: str | None = os.environ.get("SUMO_BINARY")
        if binary_override:
            return binary_override

        sumo_home: str | None = os.environ.get("SUMO_HOME")
        if sumo_home:
            gui_candidate = Path(sumo_home) / "bin" / "sumo-gui"
            if gui_candidate.exists():
                return str(gui_candidate)
            gui_candidate_exe = gui_candidate.with_suffix(".exe")
            if gui_candidate_exe.exists():
                return str(gui_candidate_exe)

            candidate = Path(sumo_home) / "bin" / "sumo"
            if candidate.exists():
                return str(candidate)
            candidate_exe = candidate.with_suffix(".exe")
            if candidate_exe.exists():
                return str(candidate_exe)

        # Fall back to whatever is on PATH, preferring the GUI binary.
        return "sumo-gui"

    def _terminate_process(self) -> None:
        """Terminate the SUMO subprocess if it is still running."""
        if self._process is not None:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
                logger.info("SUMO subprocess terminated.")
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Could not terminate SUMO process: {exc}")
            finally:
                self._process = None
