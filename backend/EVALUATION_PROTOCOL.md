# FYP evaluation protocol (Stage 4, revision 3)

Status: **implemented and run.** Two final evaluations exist, each recorded in `evaluation_runs/ledger.jsonl`:

| Run | Checkpoint | Seeds |
|---|---|---|
| `evaluation_runs/fyp_final_s0/` | v1 `fyp_s0` `best.pt` (episode 400, `0e186288…`) | 4,000,001 … 4,000,030 |
| `evaluation_runs/fyp_final_s0_obs_v2/` | obs-v2 `fyp_s0_obs_v2` `best.pt` (episode 240, `e7bc8722…`) | 4,000,031 … 4,000,060 |

Revision 3 updates only the status text, the seed lines (sections 1 and 5), the DQN controller description (section 4), section 8, the section 9 heading and a new run record (section 11) to match what was run; the episode
structure, metric definitions, statistical procedure and baseline controllers are unchanged. The results are reported in
`reports/intelliroads_final_evaluation_report.md`. The legacy checkpoint (`data/models/dqn_agent.pt`, 5 features) is refused by the loader and is not evidence of anything.

```bash
cd backend
python evaluate_fyp.py --mode final --plan --controllers fixed_time rule_based actuated_style dqn   # print the final protocol + runtime estimate, simulate nothing
python evaluate_fyp.py --mode smoke --run-id chk --controllers fixed_time rule_based actuated_style   # plumbing check, system temp dir, smoke seeds
python evaluate_fyp.py --mode final --run-id fyp_final --dqn-run training_runs/<run> --confirm-final --controllers fixed_time rule_based actuated_style dqn
```

## 1. Episode structure: warm-up, measured window, drain

```
t = 0 ──────── 300 ───────────────────── 2100 ─────────────── ≤ 2700
   warm-up        measured window (1800 s)        drain (≤ 600 s)
   demand on      demand on                       NO new demand
   not measured   lane + trip metrics             trips finish; no lane metrics
```

* **Warm-up (300 s):** the controllers act; nothing is measured, so the empty start does not dominate.
* **Measured window (1800 s, steps starting in [300, 2100)):** all lane statistics come from here and only from here.
* **Demand stops at t = 2100 s.** The episode's route file is generated per episode in a temporary directory with every flow ending at
  2100 s (`EnvConfig.demand_end_s`); the random draws are independent of the end time (tested), so each seed is exactly the first 2100 s of its
  usual demand. The tracked route file is never written.
* **Drain (maximum 600 s):** the simulation continues with the controllers still acting (as in operation; the signal is not frozen) until the
  network is empty (SUMO reports no vehicle left or waiting for insertion) or 600 s have passed. Drain observations are **never** used in lane,
  queue, occupancy or congestion metrics (tested: `n_lane_obs` is 16 × 1800 whatever the drain length).
* **Measured cohort:** every vehicle inserted at or after t = 300 s. Because demand stops at 2100 s, a vehicle inserted *after* 2100 s is a delayed insertion
  of window demand (SUMO queues a flow vehicle until its lane has room) and stays in the cohort (`departed_after_window`).
  Vehicles inserted before 300 s are excluded.
* **Completed vs unfinished:** a cohort trip is *completed* if it arrived before the drain ended, otherwise *unfinished*. Cohort vehicles that
  never got inserted (`trips_not_inserted`) are also unfinished. They are counted, never silently dropped; an episode in which the drain was
  used up has `drain_exhausted = 1` and is flagged in `episodes.csv`.
* **No mixing of partial and completed durations:** `travel_time_completed_s` is the mean over completed trips only; `unfinished_age_mean_s` is the
  mean age (run end − insertion) of unfinished trips only and is a **lower bound** of their travel time; the two are never averaged together.
  If a controller leaves trips unfinished, its `travel_time_completed_s` is optimistic and must be read together with `completion_rate`.
* **Seeds:** 30 matched seeds per final evaluation (4,000,001 … 4,000,030 for the v1 checkpoint; the fresh reserved seeds 4,000,031 … 4,000,060 for the obs-v2
  checkpoint, see section 9); every controller runs on each seed (same demand, same SUMO seed).
* **Abort conditions (the run stops with an error rather than reporting):** episode ending before demand stopped, truncation at the wrong time, wrong decision
  count, any illegal action or safety violation, lane observations ≠ 16 × 1800, `terminated` with unfinished trips, no vehicle in the window, fixed-time timing mismatch.

## 2. Metric definitions

Every metric is first reduced to **one network-wide value per episode** (= per seed and controller) unless marked per-lane/per-junction.
`n` = trips of the measured cohort that were inserted; `N` = `n` + `trips_not_inserted` (= `trips_scheduled`, identical for all controllers on a seed).
Trip times use the step-start convention, which equals SUMO's own tripinfo `depart` / `duration` / `waitingTime` (cross-checked in the tests).

| Metric (column) | Formula | Unit | Level | Unfinished trips |
|---|---|---|---|---|
| `wait_per_vehicle_all_s` (**primary**) | (1/n) Σ_v w_v, w_v = seconds the vehicle travelled at speed ≤ 0.1 m/s since insertion (insertion step excluded) | s / vehicle | network, all cohort trips | included with the waiting accumulated until the run end |
| `wait_per_vehicle_completed_s` | same, completed trips only | s / vehicle | network | excluded |
| `travel_time_completed_s` | (1/\|C\|) Σ_{v∈C} (arrive_v − depart_v) | s | network | excluded (reported separately) |
| `unfinished_age_mean_s` | (1/\|U\|) Σ_{v∈U} (run_end − depart_v); NaN if U is empty | s | network | only these; lower bound |
| `trips_departed`, `trips_completed`, `trips_unfinished`, `trips_not_inserted`, `trips_scheduled`, `departed_after_window` | counts of the cohort | vehicles | network | each reported |
| `unfinished_share` | trips_unfinished / trips_departed | – | network | – |
| `completion_rate` | trips_completed / trips_scheduled | – | network | counts not-inserted vehicles as not completed |
| `arrivals_in_window`, `throughput_veh_per_h` | vehicles (any insertion time) arriving in [300, 2100); ÷ 0.5 h | veh, veh/h | network | arrivals in the drain are not throughput |
| `mean_queue_per_lane` | (1/(16·1800)) Σ_t Σ_lane halting_lane,t; halting = vehicles with speed < 0.1 m/s (SUMO `getLastStepHaltingNumber`) | veh / lane | network (mean of the 16 lanes) | n/a (lane state) |
| `max_queue_any_lane` | max over t and lanes of halting | veh | network (worst single lane-second) | n/a |
| `mean_vehicles_per_lane` | same average of the vehicle count | veh / lane | network | n/a |
| `mean_occupancy_pct` | 100 · same average of SUMO lane occupancy (fraction of lane length covered) | % | network | n/a |
| `pct_lane_steps_congested` | 100 · (lane-seconds with occupancy > 0.70 **or** > 15 vehicles) / (16·1800) | % | network | n/a |
| `teleports` | vehicles SUMO teleported during the whole run | veh | network | diagnostic |
| `drain_s_used`, `drain_exhausted`, `vehicles_left_at_end` | drain length actually used; 1 if the 600 s were used up; vehicles still in or waiting for the network | s, flag, veh | network | diagnostic |

**Levels.** The tables in `summary.json` and the paired statistics are **network-wide** (16 lanes, all trips pooled). Per-lane values (`mean_vehicles`,
`mean_queue`, `mean_occupancy_pct`, `pct_steps_congested`, same definitions restricted to one lane) are written for every lane and episode to `lanes.csv`
(the junction is a column), so per-junction summaries can be formed by averaging the four lanes of a junction; they are descriptive and not part of the
primary analysis. Trip metrics are network-wide only (a trip crosses several junctions). The 16 lanes are the incoming lanes of junctionA–D discovered from the traffic-light definitions.

## 3. Statistical protocol (descriptive)

* **Unit of analysis:** the episode = one seed. The 30 seeds are the replicates; vehicles within an episode are not treated as independent.
* **Aggregation over seeds:** unweighted mean and sample standard deviation (ddof = 1) of the 30 per-seed values, plus min/max. A seed in which a metric is
  undefined (e.g. `unfinished_age_mean_s` with no unfinished trip) is left out for that metric and `n` is reported.
* **Paired difference:** for controller c and metric m, d_s = m(c, s) − m(fixed_time, s) for each seed s. Reported: mean(d), SD(d) (ddof = 1), median(d), n, and the
  **95 % Student-t interval** mean(d) ± t(0.975, n−1) · SD(d)/√n (t = 2.045 for n = 30). Pairing is by seed (same traffic). The demand generator is seeded per seed,
  so seeds are treated as independent draws.
* **Assumptions and meaning:** the interval assumes approximately normal differences; it describes the size and spread of the difference on these
  30 scenarios of one demand generator. **No hypothesis test, p-value, multiple-comparison claim or "better/worse" verdict is produced**, and none should be written
  from these numbers alone. An interval containing 0 is inconclusive; one that excludes 0 describes this demand family and is not proof of general superiority.
* `fixed_time` is the reference only because it is SUMO's own programme. The primary metric is fixed in advance (`wait_per_vehicle_all_s`); all others are secondary.

## 4. Controllers (all act through the same safe action layer: green 10–60 s, yellow untouched, decisions every 5 s)

* **`fixed_time`** – SUMO's own programme, action KEEP at every decision, nothing else. Verified in **every** episode (tested): (a) before the run, the programme SUMO reports
  through TraCI (phases, durations, states) equals the `tlLogic` of `intelliroads.net.xml` for all four junctions (programme `static`, offset 0: 30 s green, 5 s yellow, 30 s green, 5 s yellow);
  (b) after the run, the recorded phases of every junction, **through the measured window and the drain**, start in phase 0, follow 0→1→2→3→0 and each lasted exactly 30/5/30/5 s,
  with at least 8 completed phases; any deviation aborts the run. A negative-control controller that switches early is detected. (The phase still running when the episode ends is incomplete and not checked.)
* **`rule_based`** – the legacy density rule: for the running green phase, take the maximum density (vehicles per km) over its served lanes when the phase starts;
  < 20 → target total green 20 s, < 40 → 35 s, ≥ 40 → 55 s. The green is moved toward the target by the safe EXTEND/REDUCE actions (±5 s per decision, never below the minimum or above the maximum green).
  The thresholds are the legacy ones and are not tuned here.
* **`actuated_style`** – **a custom, untuned emulation of a gap-based actuated signal written for this project; it is not SUMO's native actuated control** (no `type="actuated"` logic, no SUMO detectors).
  Rules: min green 10 s; max green 50 s; "detector" = vehicles within 40 m of the stop line (read from TraCI vehicle positions); gap-out (SWITCH) when the served approach has no vehicle in range, the other has, and
  the min green has elapsed; extend by 5 s when the green is about to end while vehicles are still in range and the total green stays ≤ 50 s. Its parameters are guesses; report it as "a simple actuated-style heuristic", not as SUMO's actuated baseline.
* **`dqn`** – the greedy policy of the checkpoint **selected on validation seeds by the training run** (`best.json` / `best.pt`). Accepted formats: `fyp-stage3-v1` (11 features, `fyp-obs-v1`)
  and `fyp-ckpt-v2` (records `obs_version`, `feature_names`, `state_size`, `detector_range_m`; e.g. `fyp-obs-v2`, 15 features, 40 m). The environment is built with the checkpoint's
  schema (section 10). The loader refuses anything else, including the legacy model. Evaluated so far: `fyp_s0` episode 400 (v1) and `fyp_s0_obs_v2` episode 240 (obs-v2).

## 5. Seed ranges (strictly separate; enforced in code and tests)

| Use | Seeds |
|---|---|
| training | 2,000,000 + episode |
| validation (`train_dqn.py` proxy) | 3,000,001 … 3,000,099 |
| checkpoint selection, head-to-head, diagnostics | 3,000,100 … 3,999,999 (consumed ranges in `app/evaluation/seeds.py` `CONSUMED_VALIDATION_RANGES`) |
| **final evaluation** | 4,000,001 … 4,000,030 (v1, used); 4,000,031 … 4,000,060 (obs-v2, used) |
| evaluation-protocol smoke checks | 5,000,001 … |
| legacy `evaluate_controllers.py` | 1,000,001 … (protected from training) |

Training and validation refuse 1M–1.999M and 4M–5.999M. Final mode needs `--confirm-final`, refuses smoke-trained checkpoints and a second final evaluation of the same
checkpoint (`ledger.jsonl`) unless `--allow-repeat-final` (recorded). Final results cannot influence checkpoint selection, which happens only inside training on validation seeds.

## 6. Outputs and integrity

Each run creates a **new** directory `evaluation_runs/<run-id>/`: `protocol.json` (protocol, seeds, controller parameters, source hashes, git state), `episodes.csv` (one row per controller and seed, written
incrementally), `lanes.csv`, `summary.json`, `timing_check.json`, `timing.json`; `ledger.jsonl` beside it. Existing directories, `evaluation_results/`, checkpoints and the tracked route file are never written
(tested with hashes). `evaluate_controllers.py` (legacy 5-feature protocol, no warm-up or drain) was corrected the same way: temp route + temp sumocfg per episode, a new output directory, tracked route refused.

## 7. Expected runtime (development container, 1 CPU, measured on smoke seed 5,000,001 at full length)

≈ 14.3–14.7 s per episode including the drain (the drain used 160–205 s of the 600 s allowed on that seed; other seeds may need more, at most +25 % of the episode time).
3 baselines × 30 seeds = 90 episodes ≈ 22 min; with the DQN 120 episodes ≈ 29 min; start-up ≈ 1 min. The estimate printed by `--plan` is rough.

## 8. Limitations

* One demand family (the existing randomised generator, 8 routes, sparse emergency-vehicle flows pooled with the other vehicles); results do not generalise beyond it.
* A delayed insertion is not counted as travel time (SUMO's convention); `departed_after_window` and `trips_not_inserted` expose it, but a controller that causes insertion backlogs is not penalised in travel time.
* `unfinished_age_mean_s` is only a lower bound; if many trips stay unfinished, completed-only means are biased and the run is flagged by `drain_exhausted`.
* `actuated_style` is an untuned emulation; `rule_based` uses legacy thresholds; the environment's reward is still the legacy formula.
* Per-lane and per-junction data are descriptive; there are no per-junction trip metrics.
* `evaluation_v2/evaluate_v2.py` (outside this stage) still overwrites the tracked route file.
* One training seed (seed 0) per DQN run; one network; the obs-v2 detector range (40 m) is untuned; intervals are not corrected for multiple comparisons.

## 9. Checkpoint selection on trip-based validation waiting time (run for `fyp_s0` and `fyp_s0_obs_v2`)

`train_dqn.py` selected `best.pt` (episode 400 of run `fyp_s0`) with a lane proxy (`mean_wait_s`) that ranks controllers differently from trip waiting.
`select_checkpoint.py` (module `app/evaluation/selection.py`) re-ranks the 20 periodic checkpoints `ckpt_ep0020 … ckpt_ep0400` with the measurement of this
protocol (300 s warm-up, 1800 s window, drain ≤ 600 s, all 16 lanes, primary metric `wait_per_vehicle_all_s`) on **fresh validation seeds only**.

```bash
python select_checkpoint.py --run-dir training_runs/fyp_s0 --plan                                   # prints the plan (seeds, rule, plan hash, runtime); simulates nothing
python select_checkpoint.py --run-dir training_runs/fyp_s0 --run-id sel_fyp_s0 --confirm-selection   # ~280 episodes; requires explicit approval
```

* **Seeds.** Stage A (screening) 3,000,101 … 3,000,110; stage B (confirmation) 3,000,201 … 3,000,220 (at most 99 per stage; the two stages never overlap).
  Accepted range 3,000,100 – 3,999,999. Refused, with a reason: final seeds (every 4,000,000 – 4,999,999, in particular the **reserved fresh final seeds 4,000,031 – 4,000,060**),
  smoke seeds, training seeds (2,xxx,xxx) and the proxy-validation seeds of `train_dqn.py` (3,000,000 – 3,000,099, already used for the original selection).
  `EvalProtocol(mode="validation")` exists only for this tool; `runner.evaluate()` refuses it and the final/smoke modes refuse selection seeds.
* **Stage A.** Each candidate on the stage-A seeds. A candidate is *eligible* only if no episode exhausted its drain, no measured trip is unfinished or not inserted and
  the mean completion is ≥ 0.999 (otherwise the waiting-time mean is biased). The 3 eligible challengers with the lowest mean trip waiting advance together with the incumbent.
  Stage-A numbers are reported but never enter the decision.
* **Stage B.** The finalists on the independent stage-B seeds. Paired differences d = challenger − incumbent per seed; the **incumbent (episode 400) stays unless**
  a challenger is eligible **and** the two-sided t-interval of mean(d) with Bonferroni-adjusted confidence 1 − 0.05/k (k = number of challengers, df = n − 1) lies **entirely below 0**.
  If several qualify, the one with the largest mean improvement wins. Otherwise the result is "keep episode 400" – an equally valid outcome.
* **Integrity.** The plan (candidate SHA-256s, seeds, rule) is written with its hash to `plan.json` before the first episode; a checkpoint changed after planning is refused; the periodic
  checkpoint of episode 400 must carry the same weights as `best.pt`. The tool never touches `ledger.jsonl`, `best.json`, `best.pt`, any training-run file or `evaluation_runs/`;
  its only output is a new `selection_runs/<run-id>/` (`plan.json`, `stage_a.csv`, `stage_b.csv`, `decision.json`). Each row also records the switching rate (descriptive, not a criterion).
* **After a selection.** The result is a validation-seed decision, not a performance claim. A final evaluation of a replaced checkpoint must use fresh final seeds
  (`evaluate_fyp.py --seed-base 4000030` → 4,000,031 – 4,000,060), never the 4,000,001 – 4,000,030 seeds whose results were already seen.
* **Limitations.** 20 correlated checkpoints of **one** training run; two-stage selection reduces but cannot remove selection bias; 10/20 seeds are planning values, not a power calculation; one demand family;
  `train_dqn.py` validation must keep `--val-n ≤ 99` to stay disjoint from the selection seeds (not enforced by the Stage-3 code); the optional lane-proxy/action-log instrumentation is not implemented.

## 10. Observation schemas in evaluation (Stage 5)

The evaluation protocol itself is unchanged. The environment of an evaluation or selection run is built with the observation schema
recorded in the evaluated checkpoint (`fyp-obs-v1` for `fyp-stage3-v1` checkpoints such as `fyp_s0`); the DQN controller refuses an
environment whose schema or detector range differs. Baseline controllers do not use the observation. See TRAINING_REPRODUCIBILITY.md.

## 11. Runs performed (record)

| Run | Output | Seeds | Outcome |
|---|---|---|---|
| v1 selection | `selection_runs/sel_fyp_s0/` | 3,000,101–110 (A), 3,000,201–220 (B) | kept episode 400 |
| obs-v2 selection | `selection_runs/sel_fyp_s0_obs_v2/` | 3,000,401–410 (A), 3,000,501–520 (B) | kept episode 240 (no challenger's Bonferroni-adjusted interval below 0) |
| v1 vs obs-v2 head-to-head (validation, not final) | `evaluation_runs/h2h_v1ep400_vs_v2ep240_s0/` | 3,000,601–630 | obs-v2 − v1 waiting −4.39 s, 95 % CI [−4.90, −3.87] |
| v1 final evaluation | `evaluation_runs/fyp_final_s0/` | 4,000,001–030 | see its `summary.json` |
| obs-v2 final evaluation | `evaluation_runs/fyp_final_s0_obs_v2/` | 4,000,031–060 | see its `summary.json` and the report |

The obs-v2 entrypoint evaluated `best.pt` = `ckpt_best_ep0240.pt` (`e7bc8722…`); the selection recorded the periodic file `ckpt_ep0240.pt` (`7a30427d…`).
The two files differ but carry identical policy weights (checked before the final run). No further final evaluation of either checkpoint is permitted
without `--allow-repeat-final`, which the ledger would record.
