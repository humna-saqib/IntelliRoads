# Emergency Vehicle Priority — Validation Summary

## Purpose

Confirms the emergency-priority override works correctly end-to-end: detection, signal override, resumption of normal control after the vehicle clears. This matters specifically because it demonstrates that reinforcement-learning control does not blindly override safety-critical traffic decisions — a real emergency vehicle always gets priority regardless of which signal controller (rule-based or DQN) is otherwise running.

## Why this is guaranteed, not just tested once

The override is implemented as a separate decision layer, not a modification of either controller. `EmergencyPriorityController.resolve_signals()` (`backend/app/services/priority_controller.py`) takes whichever signal decision the active controller (rule-based *or* DQN) already produced for that tick, and substitutes a forced-GREEN override for any junction with an active emergency vehicle — every other junction's decision passes through untouched. Neither `SignalController` nor `DQNController` is modified or even aware this layer exists. This is a structural guarantee, not a behavior that happens to hold in one test: the override applies identically no matter which controller is active underneath it.

## Test scenario

A dedicated, deterministic scenario (`app/sumo_tools/route_generator.py: generate_emergency_validation_routefile`), not the randomized training/evaluation scenario:
- One ambulance, guaranteed to depart at t=5s on `route_top_east`, passing through `junctionA`
- Light, fixed-period background traffic (not the exponential-period flows used elsewhere — see note below)
- Run via `backend/validate_emergency_priority.py`, which exercises the actual production services (`EmergencyVehicleDetector`, `EmergencyPriorityController`) exactly as `main.py`'s live loop does — not a mock of the logic

## Results (Rule-Based controller, real run)

| Check | Result |
| :--- | :---: |
| 1. Detection occurred | ✅ PASS |
| 2. Override activated with forced GREEN | ✅ PASS |
| 3. Vehicle cleared and override deactivated | ✅ PASS |
| 4. Normal control resumed after | ✅ PASS |

**Captured event timeline:**

| Sim time | Event | Detail |
| :---: | :--- | :--- |
| t=5s | `DETECTED` | Ambulance detected on `lane_A_west_in`, junctionA |
| t=5s | `ACTIVATED` | junctionA forced GREEN for 90s; normal decision (20s) suspended |
| t=57s | `INTERSECTION_CHANGE` | Ambulance left junctionA's approach |
| t=57s | `DEACTIVATED` | junctionA restored to normal density-based control |
| t=147s | `CLEARED` | Ambulance completed its route and left the simulation |

Note the deactivation at t=57s — well before the full 90-second override window would have elapsed (t=95s) — happened because the vehicle actually left the junction, not because of a timer. This confirms the override tracks the vehicle's real presence, not a fixed duration.

Full raw evidence: `backend/validation_results/ev_priority_validation.json`.

## Scope and honest limitations

- This run validates the **Rule-Based** controller. The same script supports `--use-dqn` to run the identical scenario with the DQN controller active, which would provide direct evidence (not just the structural argument above) for the DQN case specifically. That flag needs a trained checkpoint and a torch-capable environment; it wasn't run as part of this pass — noted as a good next step if stronger DQN-specific evidence is wanted before submission.
- This is a single scenario with one emergency vehicle. It confirms the mechanism works correctly, not that it's been stress-tested under concurrent multi-vehicle emergencies or edge cases (e.g. two emergency vehicles approaching the same junction from different directions).

## A separate finding surfaced while building this validation

While debugging why the ambulance initially failed to insert into the simulation at all under the original background-traffic settings, we found that `period="exp(X)"` in SUMO flow definitions (used throughout the existing route files, including the ones used for DQN training/evaluation) is interpreted as a Poisson arrival **rate of X vehicles per second**, not a mean gap of X seconds as the naming suggests. A minimal isolated test confirmed this: `period="exp(15)"` produced ~8,964 vehicle insertions over a 600-second window (≈15 veh/s), not the ~40 a "mean gap of 15s" reading would predict. This pattern predates this validation work and is not something introduced by it. It's flagged here since it may affect how "realistic" the traffic density used in the recently-completed training/evaluation run actually was, and is worth a team decision on whether to investigate further before finalizing the report.
