"""
Seeded, per-episode randomized route-file generation for IntelliRoads.

Rationale
---------
The original ``backend/sumo/routes/intelliroads.rou.xml`` defines a single,
fixed, non-randomized set of SUMO <flow> elements. Every training epoch and
every evaluation episode therefore replayed the exact same traffic demand,
which is why the original evaluation produced std = 0.0 across 30 "episodes"
(see rl_pipeline/evaluation_results/eval_raw.csv) and why the DQN was only
ever trained against one traffic pattern.

This module regenerates that route file per call, with a seed controlling:
  - per-flow vehicle spawn rate (period), sampled around each flow's
    original baseline so density genuinely varies episode to episode
  - a directional bias multiplier, so some episodes skew heavier
    N-S vs E-W traffic instead of every episode being symmetric

The seeded-per-episode-regeneration *pattern* (not the code) is adapted
from AndreaVidali/Deep-QLearning-Agent-for-Traffic-Signal-Control
(MIT License, Copyright (c) 2019 Andrea Vidali), whose generator.py
regenerates a route file per episode using a seeded RNG. The actual
route/flow structure here is specific to IntelliRoads' own network
(8 named routes, passenger/motorcycle/bus/emergency vehicle types)
and is not copied from that repo.

Usage
-----
    from app.sumo_tools.route_generator import generate_routefile
    generate_routefile(seed=epoch, output_path=ROUTE_FILE_PATH)
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import NamedTuple


class FlowSpec(NamedTuple):
    flow_id: str
    route: str
    vtype: str
    base_period: float  # seconds between spawns (or exp(x) mean gap)
    exp_distributed: bool  # True -> period="exp(x)", False -> fixed period


# Baseline flows, taken from the structure of the original
# backend/sumo/routes/intelliroads.rou.xml (same routes/vtypes, so the
# network/connections stay fully compatible - only demand is randomized).
BASE_FLOWS: list[FlowSpec] = [
    FlowSpec("flow_car_top_e", "route_top_east", "passenger", 15, True),
    FlowSpec("flow_moto_top_e", "route_top_east", "motorcycle", 30, True),
    FlowSpec("flow_car_top_w", "route_top_west", "passenger", 15, True),
    FlowSpec("flow_bus_top_w", "route_top_west", "bus", 180, False),
    FlowSpec("flow_car_bot_e", "route_bottom_east", "passenger", 15, True),
    FlowSpec("flow_car_bot_w", "route_bottom_west", "passenger", 15, True),
    FlowSpec("flow_moto_bot_w", "route_bottom_west", "motorcycle", 35, True),
    FlowSpec("flow_car_left_s", "route_left_south", "passenger", 15, True),
    FlowSpec("flow_car_left_n", "route_left_north", "passenger", 15, True),
    FlowSpec("flow_bus_left_n", "route_left_north", "bus", 180, False),
    FlowSpec("flow_car_right_s", "route_right_south", "passenger", 15, True),
    FlowSpec("flow_moto_right_s", "route_right_south", "motorcycle", 30, True),
    FlowSpec("flow_car_right_n", "route_right_north", "passenger", 15, True),
]

# Emergency flows are deliberately NOT density-randomized - EV priority
# testing needs a predictable-enough emergency arrival rate. Only their
# period jitters slightly so they don't land on identical simulation
# seconds every episode.
EMERGENCY_FLOWS: list[FlowSpec] = [
    FlowSpec("flow_amb_A", "route_top_east", "ambulance", 240, False),
    FlowSpec("flow_pol_B", "route_right_south", "police", 260, False),
    FlowSpec("flow_fire_D", "route_left_north", "firetruck", 280, False),
]

VTYPES_XML = """    <vType id="passenger" vClass="passenger" accel="2.6" decel="4.5" sigma="0.5" length="5.0" minGap="2.5" maxSpeed="33.33"/>
    <vType id="motorcycle" vClass="motorcycle" accel="6.0" decel="5.0" sigma="0.5" length="2.0" minGap="1.0" maxSpeed="41.67"/>
    <vType id="bus" vClass="bus" accel="1.2" decel="4.0" sigma="0.5" length="12.0" minGap="3.0" maxSpeed="22.22"/>
    <vType id="ambulance" vClass="emergency" guiShape="emergency" color="1,0,0" accel="3.0" decel="5.0" sigma="0.5" length="6.0" minGap="2.0" maxSpeed="38.89"/>
    <vType id="police" vClass="emergency" guiShape="police" color="1,0,0" accel="3.0" decel="5.0" sigma="0.5" length="5.0" minGap="2.0" maxSpeed="38.89"/>
    <vType id="firetruck" vClass="emergency" guiShape="firebrigade" color="1,0,0" accel="2.0" decel="4.0" sigma="0.5" length="10.0" minGap="3.0" maxSpeed="27.78"/>"""

ROUTES_XML = """    <route id="route_top_east" edges="edge_A_west_in edge_AB_east edge_B_east_out"/>
    <route id="route_top_west" edges="edge_B_east_in edge_AB_west edge_A_west_out"/>
    <route id="route_bottom_east" edges="edge_D_west_in edge_CD_east edge_C_east_out"/>
    <route id="route_bottom_west" edges="edge_C_east_in edge_CD_west edge_D_west_out"/>
    <route id="route_left_south" edges="edge_A_north_in edge_AD_south edge_D_south_out"/>
    <route id="route_left_north" edges="edge_D_south_in edge_AD_north edge_A_north_out"/>
    <route id="route_right_south" edges="edge_B_north_in edge_BC_south edge_C_south_out"/>
    <route id="route_right_north" edges="edge_C_south_in edge_BC_north edge_B_north_out"/>"""

DIRECTIONS = {
    "top": ["flow_car_top_e", "flow_moto_top_e", "flow_car_top_w", "flow_bus_top_w"],
    "bottom": ["flow_car_bot_e", "flow_car_bot_w", "flow_moto_bot_w"],
    "left": ["flow_car_left_s", "flow_car_left_n", "flow_bus_left_n"],
    "right": ["flow_car_right_s", "flow_moto_right_s", "flow_car_right_n"],
}


def generate_routefile(
    seed: int,
    output_path: Path,
    duration: int = 3600,
    density_jitter: tuple[float, float] = (0.6, 1.6),
    directional_bias_strength: float = 0.5,
) -> None:
    """Write a randomized route file for one training/evaluation episode.

    Args:
        seed: RNG seed. Same seed -> same route file (reproducible episodes).
        output_path: Path to write the .rou.xml to (overwrites in place).
        duration: Simulation duration in seconds (begin=0, end=duration).
        density_jitter: (min, max) multiplier range applied to each flow's
            base period. Values >1 = less frequent spawns (lighter traffic),
            <1 = more frequent (heavier traffic).
        directional_bias_strength: How much one random direction can be
            boosted relative to the others, simulating an uneven demand
            episode (e.g. a rush-hour skew toward one approach).
    """
    rng = random.Random(seed)

    # One direction gets a traffic boost this episode, chosen at random.
    biased_direction = rng.choice(list(DIRECTIONS.keys()))
    bias_multiplier = 1.0 - directional_bias_strength * rng.random()

    lines: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<routes xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/routes_file.xsd">',
        "    <!-- Vehicle Types (No Trucks) -->",
        VTYPES_XML,
        "",
        "    <!-- 8 Straight Routes Across the Grid -->",
        ROUTES_XML,
        "",
        f"    <!-- Randomized demand, seed={seed}, biased_direction={biased_direction} -->",
    ]

    flow_to_direction = {fid: d for d, ids in DIRECTIONS.items() for fid in ids}

    for flow in BASE_FLOWS:
        jitter = rng.uniform(*density_jitter)
        if flow_to_direction.get(flow.flow_id) == biased_direction:
            jitter *= bias_multiplier
        period = round(flow.base_period * jitter, 2)
        period_attr = f"exp({period})" if flow.exp_distributed else str(period)
        lines.append(
            f'    <flow id="{flow.flow_id}" begin="0" end="{duration}" '
            f'period="{period_attr}" route="{flow.route}" type="{flow.vtype}"/>'
        )

    lines.append("")
    lines.append("    <!-- Sparse emergency vehicle flows (period jitter only, not density-randomized) -->")
    for flow in EMERGENCY_FLOWS:
        jitter = rng.uniform(0.9, 1.1)
        period = round(flow.base_period * jitter, 2)
        lines.append(
            f'    <flow id="{flow.flow_id}" begin="0" end="{duration}" '
            f'period="{period}" route="{flow.route}" type="{flow.vtype}"/>'
        )

    lines.append("</routes>")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def generate_emergency_validation_routefile(
    output_path: Path,
    ambulance_depart: float = 5.0,
    duration: int = 400,
) -> None:
    """Write a route file for validating emergency-priority override behavior.

    Unlike generate_routefile(), this is deterministic, not seeded: it always
    places a single ambulance on route_top_east (through junctionA) departing
    at ``ambulance_depart`` seconds, guaranteed - not left to the sparse random
    EMERGENCY_FLOWS periods (~240-280s), which could easily miss a short
    validation run's simulated window entirely.

    Background traffic uses plain fixed periods (e.g. period="45"), NOT the
    period="exp(X)" form used elsewhere in this module. That was a deliberate
    choice after discovering exp(X) is interpreted by this SUMO version as a
    Poisson arrival RATE of X vehicles/second, not a mean gap of X seconds as
    the naming suggests - period="exp(15)" produces ~15 veh/s (confirmed via
    a minimal isolated test: 8,964 vehicles loaded from one such flow over
    600s, vs. the ~40 a "mean gap of 15s" reading would predict). That misread
    is present in the original route file this module was modeled on, and
    caused total insertion gridlock in this validation scenario - the
    ambulance was never able to insert at all with the original assumption
    of a "light" 1.5x-6x jitter on those periods. Using plain fixed periods
    here sidesteps that entirely for this validation scenario; it does not
    change generate_routefile() or the already-completed training/evaluation
    runs, which is a separate, larger decision flagged elsewhere.

    Args:
        output_path: Path to write the .rou.xml to (overwrites in place).
        ambulance_depart: Simulation second at which the single validation
            ambulance departs on route_top_east.
        duration: Simulation duration in seconds for background flows.
    """
    # Deliberately sparse, deterministic periods (one vehicle every N
    # seconds, N large) - just enough background presence to be a
    # realistic scenario without risking insertion gridlock blocking
    # the ambulance, which is the actual subject under test here.
    background_period = 45.0

    lines: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<routes xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/routes_file.xsd">',
        "    <!-- Vehicle Types (No Trucks) -->",
        VTYPES_XML,
        "",
        "    <!-- 8 Straight Routes Across the Grid -->",
        ROUTES_XML,
        "",
        f"    <!-- EV priority validation scenario: sparse fixed-period background "
        f"traffic (period={background_period}s, deterministic - see docstring for "
        f"why not exp()), one guaranteed ambulance departing at "
        f"t={ambulance_depart}s on route_top_east (junctionA) -->",
    ]

    for flow in BASE_FLOWS:
        lines.append(
            f'    <flow id="{flow.flow_id}" begin="0" end="{duration}" '
            f'period="{background_period}" route="{flow.route}" type="{flow.vtype}"/>'
        )

    lines.append("")
    lines.append(
        f'    <vehicle id="validation_ambulance" type="ambulance" '
        f'route="route_top_east" depart="{ambulance_depart}"/>'
    )

    lines.append("</routes>")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
