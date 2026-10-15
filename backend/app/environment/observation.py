"""
IntelliRoads FYP – corrected junction observation (Stage 1).

Replaces the single-lane, partly-constant 5-feature state of the legacy
``SUMOEnvironment.get_state`` with a measurement that

* reads **every incoming lane** of the junction (discovered from the traffic-light
  definition, not from a hard-coded lane name),
* uses only TraCI calls that exist (``lane.getLastStepHaltingNumber`` – the legacy
  ``lane.getHaltingNumber`` does not exist in TraCI),
* **fails with a clear ``EnvError``** when TraCI returns an invalid value, instead of
  substituting a made-up constant,
* encodes the signal phase one-hot and adds the time elapsed in the current phase.

The module is deliberately free of any import from the legacy environment so it can be
unit-tested with a fake TraCI connection.

State vector (``STATE_SIZE`` = 11, every entry in [0, 1])
--------------------------------------------------------
 0 count_frac        vehicles on the 4 incoming lanes / lane capacity
 1 halting_frac      halting vehicles (speed < 0.1 m/s, SUMO definition) / lane capacity
 2 mean_wait_norm    mean accumulated waiting time per vehicle / ``WAIT_MAX_S``
 3 occupancy         length-weighted mean lane occupancy (SUMO returns a fraction 0..1)
 4 halting_frac_g0   halting fraction of the lanes served by the first green phase
 5 halting_frac_g1   halting fraction of the lanes served by the second green phase
 6-9 phase_onehot    one-hot of the traffic-light phase index (4 phases)
10 elapsed_norm      seconds since the current phase started / max green (``ELAPSED_MAX_S`` = 60 s by default)

Features 4-5 keep the information *which approach is waiting*, which an all-lane sum
cannot express but a switch/extend decision needs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np


class EnvError(RuntimeError):
    """Raised for any invalid TraCI response or invalid environment usage (never swallowed)."""


# ---------------------------------------------------------------------------
# Normalisation constants (each one has a physical justification)
# ---------------------------------------------------------------------------
#: Jam spacing per vehicle on a lane: 5.0 m passenger car (route_generator.VTYPES_XML)
#: + 2.5 m minGap. Lane capacity = length / VEHICLE_SPACE_M.
VEHICLE_SPACE_M: float = 7.5
#: SUMO accumulates a vehicle's waiting time over a memory window of 100 s
#: (``--waiting-time-memory`` default), so a per-vehicle mean cannot exceed 100 s.
WAIT_MAX_S: float = 100.0
#: Default normaliser of the elapsed-phase feature = the default maximum green of the safe action
#: layer (``SignalSafetyConfig.max_green_s`` = 60 s).  A green can never be longer (Stage 2 enforces it),
#: so the feature spans the whole [0, 1] range; the environment passes the *configured* max green so the two
#: cannot drift apart.  (Stage 1 used the legacy 90 s EXTEND cap, which left the feature capped at 0.67.)
ELAPSED_MAX_S: float = 60.0
#: Number of phases of the junction programs (G, y, G, y – no all-red phase).
N_PHASES: int = 4
#: SUMO reports occupancy as a fraction; a value far above 1 would mean a unit change.
_OCCUPANCY_TOLERANCE: float = 1.05

FEATURE_NAMES: Tuple[str, ...] = (
    "count_frac", "halting_frac", "mean_wait_norm", "occupancy",
    "halting_frac_g0", "halting_frac_g1",
    "phase_0", "phase_1", "phase_2", "phase_3",
    "elapsed_norm",
)
STATE_SIZE: int = len(FEATURE_NAMES)


# ---------------------------------------------------------------------------
# Topology
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class JunctionTopology:
    """Incoming lanes of one signalised junction and the green group serving each lane."""

    junction_id: str
    lanes: Tuple[str, ...]
    lengths_m: Tuple[float, ...]
    #: ``groups[k]`` = indices (into ``lanes``) served by the k-th green phase.
    groups: Tuple[Tuple[int, ...], Tuple[int, ...]]
    green_phases: Tuple[int, int]
    n_phases: int

    @property
    def capacities(self) -> Tuple[float, ...]:
        return tuple(length / VEHICLE_SPACE_M for length in self.lengths_m)


def discover_topology(conn: Any, junction_id: str) -> JunctionTopology:
    """Derive incoming lanes and green groups from the traffic-light definition."""
    try:
        links = conn.trafficlight.getControlledLinks(junction_id)
        logics = conn.trafficlight.getAllProgramLogics(junction_id)
        program_id = conn.trafficlight.getProgram(junction_id)
    except Exception as exc:  # traci.TraCIException / FatalTraCIError / fake errors
        raise EnvError(f"cannot read traffic-light definition of '{junction_id}': {exc!r}") from exc

    link_lane: List[str] = []
    for i, group in enumerate(links):
        if not group:
            raise EnvError(f"junction '{junction_id}': link {i} has no incoming lane")
        link_lane.append(group[0][0])
    lanes = tuple(dict.fromkeys(link_lane))          # unique, in link order
    if not lanes:
        raise EnvError(f"junction '{junction_id}' controls no lanes")

    logic = next((lg for lg in logics if lg.programID == program_id), logics[0] if logics else None)
    if logic is None:
        raise EnvError(f"junction '{junction_id}' has no program logic")
    states = [p.state for p in logic.phases]
    if len(states) != N_PHASES:
        raise EnvError(f"junction '{junction_id}': expected {N_PHASES} phases, found {len(states)}")
    green_phases = tuple(i for i, s in enumerate(states) if any(c in "Gg" for c in s))
    if len(green_phases) != 2:
        raise EnvError(f"junction '{junction_id}': expected 2 green phases, found {len(green_phases)}")

    groups: List[Tuple[int, ...]] = []
    for phase in green_phases:
        state = states[phase]
        if len(state) != len(link_lane):
            raise EnvError(f"junction '{junction_id}': phase {phase} state length != number of links")
        served = {link_lane[i] for i, c in enumerate(state) if c in "Gg"}
        groups.append(tuple(sorted(lanes.index(l) for l in served)))
    covered = sorted(set(groups[0]) | set(groups[1]))
    if covered != list(range(len(lanes))) or set(groups[0]) & set(groups[1]):
        raise EnvError(f"junction '{junction_id}': green phases do not partition the incoming lanes ({groups})")

    try:
        lengths = tuple(float(conn.lane.getLength(l)) for l in lanes)
    except Exception as exc:
        raise EnvError(f"cannot read lane lengths of '{junction_id}': {exc!r}") from exc
    if any(not math.isfinite(x) or x <= 0 for x in lengths):
        raise EnvError(f"junction '{junction_id}': invalid lane lengths {lengths}")
    return JunctionTopology(junction_id, lanes, lengths, (groups[0], groups[1]),
                            (green_phases[0], green_phases[1]), len(states))


# ---------------------------------------------------------------------------
# Raw measurement
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class JunctionMeasurement:
    """Raw (un-normalised) measurement of one junction at one simulation instant."""

    count: float                      # vehicles on all incoming lanes
    halting: float                    # halting vehicles on all incoming lanes
    mean_wait_s: float                # mean accumulated waiting time per vehicle (0 if no vehicle)
    occupancy: float                  # length-weighted mean occupancy, fraction 0..1
    group_halting: Tuple[float, float]
    per_lane: Dict[str, Dict[str, float]]


def _checked(value: Any, what: str, lane: str, lo: float = 0.0, hi: float = math.inf) -> float:
    try:
        x = float(value)
    except (TypeError, ValueError) as exc:
        raise EnvError(f"TraCI returned a non-numeric {what} for lane '{lane}': {value!r}") from exc
    if not math.isfinite(x) or x < lo or x > hi:
        raise EnvError(f"TraCI returned an invalid {what} for lane '{lane}': {x!r}")
    return x


def read_measurement(conn: Any, topo: JunctionTopology) -> JunctionMeasurement:
    """Read and aggregate the four per-lane TraCI measurements of one junction."""
    per_lane: Dict[str, Dict[str, float]] = {}
    for lane in topo.lanes:
        try:
            count = _checked(conn.lane.getLastStepVehicleNumber(lane), "vehicle count", lane)
            halting = _checked(conn.lane.getLastStepHaltingNumber(lane), "halting number", lane)
            waiting = _checked(conn.lane.getWaitingTime(lane), "waiting time", lane)
            occupancy = _checked(conn.lane.getLastStepOccupancy(lane), "occupancy", lane, hi=_OCCUPANCY_TOLERANCE)
        except EnvError:
            raise
        except Exception as exc:
            raise EnvError(f"TraCI call failed for lane '{lane}': {exc!r}") from exc
        if halting > count:
            raise EnvError(f"lane '{lane}': halting ({halting}) exceeds vehicle count ({count})")
        per_lane[lane] = {"count": count, "halting": halting, "waiting_time": waiting, "occupancy": occupancy}

    count = sum(v["count"] for v in per_lane.values())
    halting = sum(v["halting"] for v in per_lane.values())
    waiting = sum(v["waiting_time"] for v in per_lane.values())
    mean_wait = waiting / count if count > 0 else 0.0           # empty junction: definition, not a fallback
    total_len = sum(topo.lengths_m)
    occupancy = sum(per_lane[l]["occupancy"] * ln for l, ln in zip(topo.lanes, topo.lengths_m)) / total_len
    group_halting = tuple(sum(per_lane[topo.lanes[i]]["halting"] for i in g) for g in topo.groups)
    return JunctionMeasurement(count, halting, mean_wait, occupancy, group_halting, per_lane)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Encoding
# ---------------------------------------------------------------------------
def _clip01(x: float, counter: List[int]) -> float:
    if x < 0.0 or x > 1.0:
        counter[0] += 1
    return min(1.0, max(0.0, x))


def encode_state(topo: JunctionTopology, meas: JunctionMeasurement, phase: int, elapsed_s: float,
                 elapsed_max_s: float = ELAPSED_MAX_S) -> Tuple[np.ndarray, int]:
    """Encode a measurement as the normalised state vector. Returns ``(vector, n_clipped_features)``."""
    if not isinstance(phase, (int, np.integer)) or not 0 <= int(phase) < topo.n_phases:
        raise EnvError(f"junction '{topo.junction_id}': invalid phase index {phase!r}")
    if not math.isfinite(elapsed_s) or elapsed_s < 0:
        raise EnvError(f"junction '{topo.junction_id}': invalid elapsed phase time {elapsed_s!r}")
    if not math.isfinite(elapsed_max_s) or elapsed_max_s <= 0:
        raise EnvError(f"invalid elapsed normaliser {elapsed_max_s!r}")
    caps = topo.capacities
    total_cap = sum(caps)
    clipped = [0]
    vec = np.zeros(STATE_SIZE, dtype=np.float64)
    vec[0] = _clip01(meas.count / total_cap, clipped)
    vec[1] = _clip01(meas.halting / total_cap, clipped)
    vec[2] = _clip01(meas.mean_wait_s / WAIT_MAX_S, clipped)
    vec[3] = _clip01(meas.occupancy, clipped)
    for k in (0, 1):
        cap_k = sum(caps[i] for i in topo.groups[k])
        vec[4 + k] = _clip01(meas.group_halting[k] / cap_k, clipped)
    vec[6 + int(phase)] = 1.0
    vec[10] = _clip01(elapsed_s / elapsed_max_s, clipped)
    return vec, clipped[0]


def feature_dict(vec: Sequence[float]) -> Dict[str, float]:
    """Name the entries of a state vector (debugging / tests)."""
    return dict(zip(FEATURE_NAMES, (float(v) for v in vec)))


# ---------------------------------------------------------------------------
# Observation schema versions (Stage 5).  v1 above is unchanged; v2 = v1 + 4 approach-presence features.
# ---------------------------------------------------------------------------
OBS_V1: str = "fyp-obs-v1"
OBS_V2: str = "fyp-obs-v2"
#: default detector range of the v2 presence features (an experimental parameter, not a tuned optimum;
#: 40 m equals the actuated-style controller's detector and the range used by the decision-logging diagnostic)
DEFAULT_DETECTOR_RANGE_M: float = 40.0
#: a vehicle slower than this counts as stopped (SUMO's halting definition, as for ``getLastStepHaltingNumber``)
STOPPED_SPEED_MS: float = 0.1
PRESENCE_FEATURE_NAMES: Tuple[str, ...] = ("served_moving_near", "served_stopped_near", "opposing_moving_near", "opposing_stopped_near")
FEATURE_NAMES_V2: Tuple[str, ...] = FEATURE_NAMES + PRESENCE_FEATURE_NAMES
OBS_SCHEMAS: Dict[str, Tuple[str, ...]] = {OBS_V1: FEATURE_NAMES, OBS_V2: FEATURE_NAMES_V2}


def schema_feature_names(obs_version: str) -> Tuple[str, ...]:
    if obs_version not in OBS_SCHEMAS:
        raise EnvError(f"unknown observation schema {obs_version!r}; known: {sorted(OBS_SCHEMAS)}")
    return OBS_SCHEMAS[obs_version]


def schema_state_size(obs_version: str) -> int:
    return len(schema_feature_names(obs_version))


def check_detector_range(range_m: float) -> float:
    x = float(range_m)
    if not math.isfinite(x) or x <= 0:
        raise EnvError(f"detector range must be a positive number of metres, got {range_m!r}")
    return x


def served_group(topo: JunctionTopology, phase: int) -> int:
    """Index (0/1) of the approach group the signal serves: during green the green's own group, during yellow the group whose
    green just ended (the programmes are G, y, G, y, so the yellow after green ``p`` is ``p + 1``)."""
    if not isinstance(phase, (int, np.integer)) or not 0 <= int(phase) < topo.n_phases:
        raise EnvError(f"junction '{topo.junction_id}': invalid phase index {phase!r}")
    p = int(phase)
    if p in topo.green_phases:
        return topo.green_phases.index(p)
    prev = (p - 1) % topo.n_phases
    if prev not in topo.green_phases:
        raise EnvError(f"junction '{topo.junction_id}': yellow phase {p} does not follow a green phase")
    return topo.green_phases.index(prev)


def presence_capacity(topo: JunctionTopology, group: int, range_m: float) -> float:
    """Most vehicles that fit within ``range_m`` of the stop line on the lanes of ``group`` (jam spacing ``VEHICLE_SPACE_M``)."""
    return sum(min(range_m, topo.lengths_m[i]) / VEHICLE_SPACE_M for i in topo.groups[group])


def read_group_presence(conn: Any, topo: JunctionTopology, group: int, range_m: float) -> Tuple[int, int]:
    """(moving, stopped) vehicles within ``range_m`` of the stop line on the lanes of ``group``; TraCI get-calls only.
    A vehicle exactly ``range_m`` away counts; an invalid TraCI value raises ``EnvError`` (no silent fallback)."""
    moving = stopped = 0
    for i in topo.groups[group]:
        lane, length = topo.lanes[i], topo.lengths_m[i]
        try:
            vids = list(conn.lane.getLastStepVehicleIDs(lane))
        except Exception as exc:
            raise EnvError(f"TraCI call failed for lane '{lane}': {exc!r}") from exc
        for vid in vids:
            try:
                pos = _checked(conn.vehicle.getLanePosition(vid), "lane position", lane, lo=-math.inf)
                speed = _checked(conn.vehicle.getSpeed(vid), "speed", lane)
            except EnvError:
                raise
            except Exception as exc:
                raise EnvError(f"TraCI call failed for vehicle '{vid}' on lane '{lane}': {exc!r}") from exc
            if length - pos <= range_m + 1e-9:
                if speed < STOPPED_SPEED_MS:
                    stopped += 1
                else:
                    moving += 1
    return moving, stopped


def read_presence(conn: Any, topo: JunctionTopology, phase: int, range_m: float) -> Tuple[int, int, int, int]:
    """Raw counts (served_moving, served_stopped, opposing_moving, opposing_stopped) relative to the served group."""
    k = served_group(topo, phase)
    sm, ss = read_group_presence(conn, topo, k, range_m)
    om, os_ = read_group_presence(conn, topo, 1 - k, range_m)
    return sm, ss, om, os_


def encode_state_v2(topo: JunctionTopology, meas: JunctionMeasurement, phase: int, elapsed_s: float,
                    presence: Sequence[float], range_m: float, elapsed_max_s: float = ELAPSED_MAX_S) -> Tuple[np.ndarray, int]:
    """v2 vector: the unchanged v1 vector followed by the four presence counts, each divided by the physical maximum of
    its group within ``range_m`` and clipped to [0, 1] (clipping is counted, as in v1)."""
    v1, clipped = encode_state(topo, meas, phase, elapsed_s, elapsed_max_s)
    range_m = check_detector_range(range_m)
    if len(presence) != 4 or any((not math.isfinite(float(x))) or float(x) < 0 for x in presence):
        raise EnvError(f"junction '{topo.junction_id}': invalid presence counts {presence!r}")
    k = served_group(topo, phase)
    caps = (presence_capacity(topo, k, range_m),) * 2 + (presence_capacity(topo, 1 - k, range_m),) * 2
    counter = [0]
    extra = [_clip01(float(x) / c, counter) for x, c in zip(presence, caps)]
    return np.concatenate([v1, np.asarray(extra, dtype=np.float64)]), clipped + counter[0]
