"""Per-episode measurement, identical for every controller (Stage 4).

Everything is measured from raw TraCI quantities by the same code, whatever controller drives the signals:

* **Lane metrics** – all 16 incoming lanes (the four incoming lanes of each of the four junctions) at every simulated
  second of the measurement window: vehicles, halting vehicles (speed < 0.1 m/s), occupancy.
* **Trip metrics** – every vehicle, tracked from departure to arrival: time spent at speed <= 0.1 m/s (SUMO's own
  ``waitingTime`` definition), travel time, completed / unfinished status.

Time convention: TraCI reports the clock *after* a step; SUMO's trip records use the *start* of the step.  All times
here are step-start times (``t - step_length``) so they equal SUMO's ``tripinfo`` ``depart`` / ``arrival`` exactly
(verified against SUMO's trip file in the tests).  A vehicle's waiting is counted for every step after its insertion
step in which its speed is <= 0.1 m/s, which reproduces ``tripinfo`` ``waitingTime`` exactly.

Measurement window: lane statistics use the steps whose start time lies in ``[warmup_s, warmup_s + measure_s)``; trip
statistics use the vehicles *departing* in that window.  Vehicles still driving at the end are **unfinished**: they are
reported separately, counted with their partial waiting time, and their travel time is right-censored at the end of the
window (so completed-only travel times, which are biased low, are never the only number reported).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence

import numpy as np

STOPPED_SPEED_MS = 0.1                  # SUMO's definition of "waiting"
CONGESTION_OCCUPANCY = 0.70             # congestion rule of the project's reward (occupancy > 70 % ...
CONGESTION_VEHICLES_PER_LANE = 15       # ... or more than 15 vehicles on a lane); a lane-step is "congested" if either holds
_OCC_TOLERANCE = 1.05


class MeasurementError(RuntimeError):
    pass


@dataclass
class Trip:
    depart_s: float
    arrive_s: Optional[float] = None
    wait_s: float = 0.0


class TripLedger:
    """Departures, arrivals and accumulated waiting of every vehicle of one episode."""

    def __init__(self) -> None:
        self.trips: Dict[str, Trip] = {}

    def depart(self, vid: str, depart_s: float) -> None:
        if vid in self.trips:
            raise MeasurementError(f"vehicle {vid} departed twice")
        self.trips[vid] = Trip(depart_s)

    def arrive(self, vid: str, arrive_s: float) -> None:
        trip = self.trips.get(vid)
        if trip is None:
            raise MeasurementError(f"vehicle {vid} arrived without having departed")
        if trip.arrive_s is not None:
            raise MeasurementError(f"vehicle {vid} arrived twice")
        if arrive_s < trip.depart_s:
            raise MeasurementError(f"vehicle {vid} arrived before it departed")
        trip.arrive_s = arrive_s

    def add_wait(self, vid: str, seconds: float) -> None:
        trip = self.trips.get(vid)
        if trip is None or trip.arrive_s is not None:
            raise MeasurementError(f"waiting reported for vehicle {vid} that is not travelling")
        trip.wait_s += seconds

    def summary(self, window_start_s: float, window_end_s: float, run_end_s: Optional[float] = None,
                not_inserted: int = 0) -> Dict[str, float]:
        """Trip statistics of the measured cohort = vehicles inserted at or after ``window_start_s``.  Demand stops at
        ``window_end_s``, so a vehicle inserted *after* it is the delayed insertion of window demand (SUMO queues a flow
        vehicle until its lane has room) and stays in the cohort (``departed_after_window``).  ``not_inserted`` counts
        window vehicles still waiting for insertion at the end of the run (they are unfinished and have no travel time).
        Vehicles are followed until ``run_end_s``
        (end of the drain; default: ``window_end_s``).  Travel times are never mixed: ``travel_time_completed_s`` covers
        finished trips only, ``unfinished_age_mean_s`` covers unfinished trips only (a lower bound of their travel time)."""
        run_end_s = window_end_s if run_end_s is None else run_end_s
        nan = float("nan")
        inc = [t for t in self.trips.values() if t.depart_s >= window_start_s]
        done = [t for t in inc if t.arrive_s is not None]
        unf = [t for t in inc if t.arrive_s is None]
        mean = lambda xs: float(np.mean(xs)) if len(xs) else nan
        arrivals = sum(1 for t in self.trips.values() if t.arrive_s is not None and window_start_s <= t.arrive_s < window_end_s)
        hours = (window_end_s - window_start_s) / 3600.0
        return {
            "trips_departed": float(len(inc)), "trips_completed": float(len(done)), "trips_unfinished": float(len(unf)),
            "unfinished_share": len(unf) / len(inc) if inc else nan,
            "trips_not_inserted": float(not_inserted), "trips_scheduled": float(len(inc) + not_inserted),
            "departed_after_window": float(sum(1 for t in inc if t.depart_s >= window_end_s)),
            "completion_rate": len(done) / (len(inc) + not_inserted) if inc else nan,
            "wait_per_vehicle_all_s": mean([t.wait_s for t in inc]),                  # unfinished trips count with their partial waiting
            "wait_per_vehicle_completed_s": mean([t.wait_s for t in done]),
            "travel_time_completed_s": mean([t.arrive_s - t.depart_s for t in done]),  # biased low: only trips that finished
            "unfinished_age_mean_s": mean([run_end_s - t.depart_s for t in unf]),
            "arrivals_in_window": float(arrivals), "throughput_veh_per_h": arrivals / hours,
        }


class LaneAccumulator:
    """Sums of the per-second lane observations over the measurement window."""

    def __init__(self, n_lanes: int) -> None:
        self.n_lanes = n_lanes
        self.steps = 0
        self.sum_count = self.sum_halt = self.sum_occ = 0.0
        self.congested = 0
        self.max_halt = 0.0
        self.count_by_lane = np.zeros(n_lanes)
        self.halt_by_lane = np.zeros(n_lanes)
        self.occ_by_lane = np.zeros(n_lanes)
        self.cong_by_lane = np.zeros(n_lanes)

    def add(self, counts: Sequence[float], halting: Sequence[float], occupancy: Sequence[float]) -> None:
        c, h, o = (np.asarray(x, dtype=float) for x in (counts, halting, occupancy))
        if not (c.shape == h.shape == o.shape == (self.n_lanes,)):
            raise MeasurementError(f"expected {self.n_lanes} lane observations, got {c.shape}")
        if not (np.isfinite(c).all() and np.isfinite(h).all() and np.isfinite(o).all()) or (c < 0).any() or (h < 0).any() or (o < 0).any():
            raise MeasurementError("invalid (non-finite or negative) lane observation")
        if (h > c + 1e-9).any() or (o > _OCC_TOLERANCE).any():
            raise MeasurementError("inconsistent lane observation (halting > count, or occupancy not a fraction)")
        self.steps += 1
        self.sum_count += float(c.sum()); self.sum_halt += float(h.sum()); self.sum_occ += float(o.sum())
        cong = (o > CONGESTION_OCCUPANCY) | (c > CONGESTION_VEHICLES_PER_LANE)
        self.congested += int(cong.sum())
        self.count_by_lane += c
        self.cong_by_lane += cong
        self.max_halt = max(self.max_halt, float(h.max()))
        self.halt_by_lane += h
        self.occ_by_lane += o

    def summary(self) -> Dict[str, float]:
        n = self.steps * self.n_lanes
        nan = float("nan")
        return {
            "mean_vehicles_per_lane": self.sum_count / n if n else nan,
            "mean_queue_per_lane": self.sum_halt / n if n else nan,
            "mean_occupancy_pct": 100.0 * self.sum_occ / n if n else nan,
            "pct_lane_steps_congested": 100.0 * self.congested / n if n else nan,
            "max_queue_any_lane": self.max_halt,
            "n_lane_obs": float(n), "n_steps_measured": float(self.steps),
        }


    def per_lane(self) -> List[Dict[str, float]]:
        """Per-lane means over the measured window (same definitions as the network-wide summary)."""
        n = max(self.steps, 1)
        return [{"mean_vehicles": float(self.count_by_lane[i] / n), "mean_queue": float(self.halt_by_lane[i] / n),
                 "mean_occupancy_pct": float(100.0 * self.occ_by_lane[i] / n), "pct_steps_congested": float(100.0 * self.cong_by_lane[i] / n)}
                for i in range(self.n_lanes)]


class EpisodeMeasurer:
    """Second-by-second hook for ``TrafficSignalEnv.add_second_hook``; one instance per episode."""

    def __init__(self, lanes: Sequence[str], warmup_s: int, measure_s: int, step_length_s: float = 1.0) -> None:
        if len(set(lanes)) != len(lanes):
            raise MeasurementError("duplicate lanes")
        self.lanes = list(lanes)
        self.warmup_s, self.measure_s, self.step = float(warmup_s), float(measure_s), float(step_length_s)
        self.ledger, self.lane_acc = TripLedger(), LaneAccumulator(len(self.lanes))
        self.steps_total = 0
        self.teleports = 0

    def __call__(self, conn: Any, t: float) -> None:
        import traci.constants as tc
        start = t - self.step
        departed = list(conn.simulation.getDepartedIDList())
        for vid in departed:
            self.ledger.depart(vid, start)
            conn.vehicle.subscribe(vid, [tc.VAR_SPEED])
        for vid in conn.simulation.getArrivedIDList():
            self.ledger.arrive(vid, start)
        just_inserted = set(departed)
        for vid, res in conn.vehicle.getAllSubscriptionResults().items():
            if vid not in just_inserted and res[tc.VAR_SPEED] <= STOPPED_SPEED_MS and vid in self.ledger.trips and self.ledger.trips[vid].arrive_s is None:
                self.ledger.add_wait(vid, self.step)
        self.teleports += int(conn.simulation.getStartingTeleportNumber())
        if self.warmup_s <= start < self.warmup_s + self.measure_s:
            lane = conn.lane
            self.lane_acc.add([lane.getLastStepVehicleNumber(l) for l in self.lanes],
                              [lane.getLastStepHaltingNumber(l) for l in self.lanes],
                              [lane.getLastStepOccupancy(l) for l in self.lanes])
        self.steps_total += 1

    def finalize(self, expected_steps: int, run_end_s: Optional[float] = None, not_inserted: int = 0) -> Dict[str, float]:
        """All metrics of the episode; raises if the episode was not measured completely."""
        window_end = self.warmup_s + self.measure_s
        if self.steps_total != expected_steps:
            raise MeasurementError(f"measured {self.steps_total} simulated seconds, expected {expected_steps}")
        if self.lane_acc.steps != self.measure_s:
            raise MeasurementError(f"lane statistics cover {self.lane_acc.steps} steps, expected {int(self.measure_s)}")
        out = {**self.ledger.summary(self.warmup_s, window_end, run_end_s, not_inserted), **self.lane_acc.summary()}
        out["n_steps_total"] = float(self.steps_total)
        out["teleports"] = float(self.teleports)
        return out
