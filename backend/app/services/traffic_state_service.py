"""
IntelliRoads – Traffic State & Occupancy Service (Qasim's Module).

Responsible for extracting, computing, and preparing the clean Reinforcement Learning
(RL) state vector from live SUMO/TraCI telemetry for Humna's DQN Agent.

State Vector Structure (5 features):
------------------------------------
1. Density / Vehicle Count: Total vehicles detected across incoming lanes.
2. Queue Information: Number of halted/stopped vehicles (speed < 2.0 m/s).
3. Waiting Time: Average waiting time in seconds of queued vehicles.
4. Lane Occupancy: Average percentage of lane space occupied by vehicles (0.0 to 100.0%).
5. Current Phase: Active traffic light phase index from the SUMO traffic light controller.

Primary Deliverable:
--------------------
get_rl_state(intersection_id) -> List[float]
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from app.services.traci_session import SUMO_AVAILABLE, TraCISession
from app.utils.logger import get_logger

if SUMO_AVAILABLE:
    import traci  # type: ignore

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Monitored Incoming Lanes per Intersection
# ---------------------------------------------------------------------------
INTERSECTION_INCOMING_LANES: Dict[str, List[str]] = {
    "junctionA": ["lane_A_west_in", "lane_A_north_in", "lane_AB_west", "lane_AD_north"],
    "junctionB": ["lane_B_east_in", "lane_B_north_in", "lane_AB_east", "lane_BC_north"],
    "junctionC": ["lane_C_east_in", "lane_C_south_in", "lane_CD_east", "lane_BC_south"],
    "junctionD": ["lane_D_west_in", "lane_D_south_in", "lane_CD_west", "lane_AD_south"],
}

# Speed threshold below which a vehicle is considered in queue / halted (m/s)
QUEUE_SPEED_THRESHOLD_MS: float = 2.0


class TrafficStateService:
    """
    Service to extract and assemble clean RL state representations from SUMO / TraCI.
    """

    def __init__(self, session: Optional[TraCISession] = None) -> None:
        self.session = session

    def get_raw_state(self, intersection_id: str) -> Dict[str, float]:
        """
        Extract raw traffic telemetry metrics for a given intersection.

        Returns
        -------
        Dict with keys:
            - vehicle_count: Total vehicles on incoming lanes
            - queue_length: Total halted vehicles on incoming lanes
            - avg_waiting_time: Average waiting time in seconds
            - lane_occupancy: Average lane occupancy percentage (0-100)
            - current_phase: Current traffic light phase index
        """
        incoming_lanes = INTERSECTION_INCOMING_LANES.get(
            intersection_id,
            [f"lane_{intersection_id[-1]}_0"] if intersection_id.startswith("junction") else [intersection_id],
        )

        total_vehicles: float = 0.0
        total_queue: float = 0.0
        total_waiting_time: float = 0.0
        total_occupancy: float = 0.0
        current_phase: float = 0.0

        is_live = SUMO_AVAILABLE and (self.session is None or not self.session.mock_mode)

        if is_live:
            try:
                # 1. Collect from incoming lanes via TraCI
                num_lanes = len(incoming_lanes)
                for lane_id in incoming_lanes:
                    try:
                        # 1a. Vehicle count per lane
                        veh_num = float(traci.lane.getLastStepVehicleNumber(lane_id))
                        total_vehicles += veh_num

                        # 1b. Queue length (halting vehicles)
                        total_queue += float(traci.lane.getHaltingNumber(lane_id))

                        # 1c. Cumulative waiting time
                        total_waiting_time += float(traci.lane.getWaitingTime(lane_id))

                        # 1d. Lane occupancy (0.0 to 1.0 -> convert to 0-100%)
                        total_occupancy += float(traci.lane.getLastStepOccupancy(lane_id)) * 100.0
                    except Exception as lane_err:
                        logger.debug(f"TraCI lane read failed for {lane_id}: {lane_err}")

                avg_occupancy = total_occupancy / max(num_lanes, 1)
                avg_waiting = total_waiting_time / max(total_vehicles, 1.0)

                # 1e. Traffic light current phase
                try:
                    current_phase = float(traci.trafficlight.getPhase(intersection_id))
                except Exception:
                    current_phase = 0.0

                return {
                    "vehicle_count": round(total_vehicles, 2),
                    "queue_length": round(total_queue, 2),
                    "avg_waiting_time": round(avg_waiting, 2),
                    "lane_occupancy": round(avg_occupancy, 2),
                    "current_phase": round(current_phase, 2),
                }

            except Exception as exc:
                logger.warning(f"TraCI state extraction error for {intersection_id}: {exc}. Using fallback.")

        # Fallback values when TraCI is not connected or in mock mode
        return {
            "vehicle_count": 8.0,
            "queue_length": 2.0,
            "avg_waiting_time": 10.5,
            "lane_occupancy": 28.5,
            "current_phase": 0.0,
        }

    def get_state_vector(self, intersection_id: str) -> List[float]:
        """
        Return the 5-element state vector required by DQNAgent:
        [vehicle_count, queue_length, avg_waiting_time, lane_occupancy, current_phase]
        """
        raw = self.get_raw_state(intersection_id)
        return [
            raw["vehicle_count"],
            raw["queue_length"],
            raw["avg_waiting_time"],
            raw["lane_occupancy"],
            raw["current_phase"],
        ]


# ---------------------------------------------------------------------------
# Global Service Instance & Qasim's Final Deliverable Function
# ---------------------------------------------------------------------------
_default_service: Optional[TrafficStateService] = None


def get_traffic_state_service(session: Optional[TraCISession] = None) -> TrafficStateService:
    """Get or create singleton TrafficStateService instance."""
    global _default_service
    if _default_service is None or session is not None:
        _default_service = TrafficStateService(session=session)
    return _default_service


def get_rl_state(
    intersection_id: str,
    session: Optional[TraCISession] = None,
) -> List[float]:
    """
    QASIM'S FINAL DELIVERABLE:
    Returns the clean 5-dimensional RL state vector for the specified intersection.

    Parameters
    ----------
    intersection_id : str
        Intersection identifier (e.g. 'junctionA', 'junctionB', 'junctionC', 'junctionD').
    session : TraCISession, optional
        Active TraCI session. If omitted, uses ambient TraCI connection.

    Returns
    -------
    List[float]
        [vehicle_count, queue_length, avg_waiting_time, lane_occupancy, current_phase]
    """
    service = get_traffic_state_service(session=session)
    return service.get_state_vector(intersection_id)
