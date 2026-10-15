# Training the corrected DQN – how to run and reproduce

`train_dqn.py` trains a **mask-aware Double DQN** on `TrafficSignalEnv` (all-lane observation from Stage 1,
safe signal actions + action masks from Stage 2, optional obs-v2 features from Stage 5). It does not use the legacy `SUMOEnvironment`, never writes
the tracked route file and never writes into `data/models/`, `final_dqn_model/` or any evaluation folder.
Two runs were trained (`fyp_s0`, v1; `fyp_s0_obs_v2`, obs-v2), checkpoints were re-selected on trip-based validation waiting time, and both
selected models received a final evaluation (`EVALUATION_PROTOCOL.md` revision 3, sections 9 and 11; results in `reports/intelliroads_final_evaluation_report.md`).

> **Code availability (read first).** Both training runs record `git_commit` `d8b9701` with `git_dirty: true`: they were trained from an
> uncommitted working tree. The training, evaluation and selection implementation (`app/training/`, `app/evaluation/`, the corrected
> `app/environment/` modules, `train_dqn.py`, `select_checkpoint.py`, `evaluate_fyp.py` and their tests) is **not contained in a clean checkout
> of the committed repository**; at `d8b9701`, `train_dqn.py` is still the legacy script. The exact source files used are identified only by the
> SHA-256 hashes in each run's `config.json` → `source_sha256`. A clean, reproducible checkout requires a later, separately reviewed code commit;
> until then the procedure below can be followed only from the working tree that produced the runs.

## Prerequisites (recorded versions; a fresh installation has not been tested)

| Component | Version used for both training runs (`config.json` → `versions`) |
|---|---|
| Python | 3.13.16 |
| SUMO | 1.18.0 (`traci` and `sumolib` Python packages 1.18.0 in the environment used) |
| PyTorch | 2.14.1+cu130 (a CUDA-enabled build; training nevertheless runs on the CPU, see below) |
| NumPy | 2.5.4 |

Setup outline: create a virtual environment, `pip install -r requirements.txt`, and install SUMO 1.18.0 so that the `sumo` binary can be found
(the environment starts it via `sumolib.checkBinary("sumo")`, which looks in `SUMO_HOME`/`bin` or on `PATH`; setting `SUMO_HOME` to the SUMO
installation is the usual way). The `traci`/`sumolib` packages should match the SUMO version. `requirements.txt` does **not** pin `torch`, `numpy`,
`traci` or `sumolib` (nor install the SUMO binary), so a new installation may resolve different versions; use a pinned environment with the versions
above when reproducing. Training is CPU-only regardless of the installed PyTorch build: the agent's device defaults to `"cpu"` and the trainer
calls `torch.set_num_threads(1)` and `torch.use_deterministic_algorithms(True)`.

## Commands

```bash
cd backend
python train_dqn.py --smoke --run-id check            # ~10 s plumbing check, NOT training (output: system temp dir)
python train_dqn.py --run-id fyp_s0 --seed 0          # real training (defaults: 400 episodes x 1800 s, validation every 20)
```

The two runs used for the FYP were started with exactly these commands (`config.json` → `argv`; every option is accepted by the current CLI):

```bash
python train_dqn.py --run-id fyp_s0 --seed 0                                                            # v1 (fyp-obs-v1, 11 features)
python train_dqn.py --run-id fyp_s0_obs_v2 --seed 0 --obs-version fyp-obs-v2 --detector-range-m 40      # obs-v2 (15 features, 40 m)
```

All other settings were the defaults: 400 episodes, 1,800 s training horizon, decisions every 5 s, γ 0.95, learning rate 5·10⁻⁴, hidden size 64,
batch 64, buffer 50,000, warm-up 1,000 transitions, 4 updates per decision, target update every 500 gradient steps, ε 1.0 → 0.05,
reward scale 0.01, gradient clip 1.0, validation every 20 episodes on 5 seeds with metric `mean_wait_s`, `patience` 0 (no early stopping).

`--smoke` runs 2 episodes of 60 s and prefixes the run id with `smoke_`; its `config.json` carries `"smoke": true`.
It only proves that the pipeline is wired correctly. Results of a smoke run must never be reported as training.

## What a run writes (`training_runs/<run-id>/`, always a **new** directory)

| File | Content | Reproducible? |
|---|---|---|
| `config.json` | all hyper-parameters, command line, seeds, git commit **and dirty flag**, SHA-256 of every source file that determines the run (training, environment, agent, route generator, network), package + SUMO versions | – |
| `episodes.csv` | per training episode: seed, epsilon, decisions, buffer size, gradient steps, target syncs, mean reward / loss / Q | expected bit-identical (see below) |
| `validation.csv` | per validation: score and metrics on the fixed validation seeds, `is_best` | expected bit-identical |
| `best.json`, `ckpt_best_epNNNN.pt`, `best.pt` | the checkpoint selected by **validation score only** (`best.pt` is a copy of the selected file) | expected bit-identical |
| `ckpt_epNNNN.pt`, `last.pt` | checkpoints at every validation / at the end | yes |
| `timing.json` | wall-clock seconds | no |

Checkpoints hold the policy and target networks, the optimiser state and counters (episode, decisions, gradient steps), the validation score and
the training configuration and observation schema – **no replay buffer** (it is large, is
rebuilt within a few episodes and is not needed to select, evaluate or deploy a model; resuming training is not supported).
An existing run directory or checkpoint is never overwritten: during training `best.json` is the only file that is rewritten (atomically)
when the validation score improves; `best.pt` is created once, as a new file, by copying the finally selected `ckpt_best_epNNNN.pt` after training.

## Reproducing a run

Two levels must be distinguished:

* **Procedural reproducibility** (supported): the same commands, seeds, code (identified by `source_sha256`) and software versions repeat the
  same training procedure and produce a run of the same kind.
* **Bit-for-bit reproducibility** (expected, not demonstrated at full scale): with an identical code state, identical software builds and the
  same hardware platform, the logs and checkpoint tensors are expected to be identical. This has been tested only on the small deterministic
  configuration of the test suite (below); **no 400-episode training run has been repeated**, and identical output on other machines or
  library builds is not claimed.

1. Use the same code state: `config.json` → `git_commit`, `git_dirty` and `source_sha256` identify it. For the FYP runs `git_dirty` is
   `true`, so the commit alone is **not** sufficient (see "Code availability" above); the per-file hashes are authoritative.
2. Use the same software: Python / NumPy / PyTorch / SUMO versions are in `config.json` → `versions`. Training is
   CPU-only, single-threaded (`torch.set_num_threads(1)`, `torch.use_deterministic_algorithms(True)`).
3. Re-run the stored command (`config.json` → `argv`) with a **new** `--run-id`, e.g.
   `python train_dqn.py --run-id fyp_s0_repro --seed 0` plus the same options.
4. Compare `episodes.csv` and `validation.csv` (text-identical) and the checkpoint tensors (`torch.equal`).
   The test-suite does exactly this on a tiny configuration (`tests/test_training_sumo.py::test_same_seed_reproduces_logs_and_weights_exactly`);
   that test is the only evidence of bit-for-bit repeatability.

What the single `--seed` controls: Python `random`, NumPy, PyTorch (initial weights), the exploration generator
(`seed + 1`), the replay-sampling generator (`seed`). Traffic and SUMO randomness come from the **episode seeds**,
which are fixed by the run's seed ranges, not by `--seed`: episode *e* uses `TRAIN_SEED_BASE + e` as SUMO `--seed`
and demand seed (`TrafficSignalEnv.reset(seed)`). Export `PYTHONHASHSEED` as well for completeness
(the code never relies on hash ordering). Whether `PYTHONHASHSEED` was set during the original runs is **not recorded** in `config.json`.

## Seeds and the train / validation / evaluation separation

| Use | Seeds | Status / enforcement |
|---|---|---|
| training episodes | `2,000,000 + episode` (FYP runs: 2,000,001 – 2,000,400) | used by both runs |
| training-time validation (proxy selection inside `train_dqn.py`; early stopping only if `--patience` > 0) | `3,000,001 …` (`--val-n` of them; FYP runs: 3,000,001 – 3,000,005) | used by both runs |
| v1 checkpoint selection | stage A 3,000,101 – 3,000,110, stage B 3,000,201 – 3,000,220 | consumed |
| diagnostics (v1) | 3,000,301 – 3,000,310 (minimum-green sweep), 3,000,311 – 3,000,320 (decision logging) | consumed |
| obs-v2 checkpoint selection | stage A 3,000,401 – 3,000,410, stage B 3,000,501 – 3,000,520 | consumed; protected from training |
| v1 vs obs-v2 head-to-head | 3,000,601 – 3,000,630 | consumed; protected from training |
| **final evaluation** | 4,000,001 – 4,000,030 (v1, used); 4,000,031 – 4,000,060 (obs-v2, used) | whole 4,000,000 – 4,999,999 range protected from training and validation |
| evaluation-protocol smoke checks | 5,000,001 … | protected from training |
| legacy `evaluate_controllers.py` | 1,000,001 … | protected from training |

*Protected* ranges (`app/training/seeds.py` → `PROTECTED_RANGES`: 1,000,000 – 1,999,999; 4,000,000 – 4,999,999; 5,000,000 – 5,999,999;
3,000,401 – 3,000,410; 3,000,501 – 3,000,520; 3,000,601 – 3,000,630) are refused by training and its validation. *Consumed* ranges
(`app/evaluation/seeds.py` → `CONSUMED_VALIDATION_RANGES`: 3,000,001 – 3,000,099, 3,000,101 – 3,000,110, 3,000,201 – 3,000,220,
3,000,301 – 3,000,310, 3,000,311 – 3,000,320 and the three obs-v2 ranges) are refused for any *new* selection or comparison; a recorded
obs-v2 experiment may only re-derive its own exact range. Final seeds are accepted only by the final-evaluation guard.
**`--val-n` restriction:** training-time validation uses 3,000,001 … 3,000,000 + `--val-n`; keep `--val-n ≤ 99` so that it stays below the
selection range (3,000,100 and above). This is not enforced by the training code for the v1 selection ranges (the obs-v2 ranges are refused).

The selector (`CheckpointSelector.update(episode, val_score)`) accepts only a validation score; training rewards, losses
or evaluation results cannot influence which checkpoint is chosen.

## Algorithm notes

* **Action masks.** Every transition stores the legal-action mask of the state and of the next state. Exploration samples
  legal actions only; the greedy action is the best legal one.
* **Double-DQN target.** `a* = argmax_{a legal in s'} Q_policy(s', a)`, `y = r + γ·Q_target(s', a*)·(1 − terminated)`.
  The unmasked rule could bootstrap from an action the environment would reject.
* **Terminal vs truncation.** Reaching the 1800 s horizon is a *truncation*: `terminated = False`, so the target
  bootstraps. Only a true terminal state (nothing left to simulate) cuts the bootstrap.
* **Warm-up.** Until `--warmup` transitions are stored, actions are uniformly random legal actions and no gradient step
  is taken. The epsilon schedule starts counting after warm-up.
* **Target network.** Hard update every `--target-update-steps` **gradient steps** (default 500).
* **Reward scale.** The legacy reward formula is unchanged; it is multiplied by `--reward-scale` (default 0.01, not tuned)
  before learning, replacing the legacy `clamp(-100, 50)` of the targets.
* **Elapsed-phase feature.** Normalised by the configured maximum green (60 s), so a green of the maximum length maps to
  exactly 1.0 (Stage 1 divided by 90 s, leaving the feature capped at 0.67). `ELAPSED_MAX_S` equals
  `SignalSafetyConfig.max_green_s`, and the environment passes the configured value; both are tested.

## Known limits

* The legacy `evaluate_controllers.py` was corrected to use a temporary route file; the FYP evaluation is `evaluate_fyp.py`
  (`EVALUATION_PROTOCOL.md`). The training/validation path never writes the tracked route file.
* Training-time validation (`best.json`/`best.pt`) uses the lane-based waiting-time proxy `mean_wait_s`. Because it can rank checkpoints
  differently from trip waiting, a later **trip-based two-stage selection** re-ranked the periodic checkpoints of both runs
  (`EVALUATION_PROTOCOL.md` §9); it kept episode 400 (v1) and episode 240 (obs-v2).
* The reward is still the legacy formula; the live application and the emergency-priority code are unchanged.
* One training seed (seed 0) per run; the obs-v2 detector range (40 m) is untuned.

## Observation schemas (Stage 5)

| Schema | Features | Checkpoint format | Default |
|---|---|---|---|
| `fyp-obs-v1` | the 11 features above, unchanged | `fyp-stage3-v1` (unchanged payload) | **yes** – `train_dqn.py`, `EnvConfig` and all evaluation paths default to v1 |
| `fyp-obs-v2` | v1's 11 features + `served_moving_near`, `served_stopped_near`, `opposing_moving_near`, `opposing_stopped_near` (15) | `fyp-ckpt-v2` (records `obs_version`, `feature_names`, `state_size`, `detector_range_m`) | opt-in: `--obs-version fyp-obs-v2 [--detector-range-m 40]` |

v2 presence features: vehicles within `detector_range_m` (default 40 m, an experimental parameter) of the stop line on the lanes of the
*served* approach group (green: its own group; yellow: the group whose green just ended) and of the opposing group, split into
stopped (speed < 0.1 m/s, SUMO's halting definition) and moving; each count is divided by `sum(min(range, lane length) / 7.5 m)` over the
group's lanes and clipped to [0, 1] (clipping is counted). Read with TraCI get-calls only; an invalid TraCI value raises `EnvError`.
The reward is computed from the unchanged v1 measurement, so it is identical under both schemas.

Loading is strict: a `fyp-stage3-v1` checkpoint is always v1 (11 features, v1 names); a `fyp-ckpt-v2` checkpoint must carry consistent
schema metadata. A checkpoint is never loaded into an environment of another schema or detector range, and weights are never reshaped.

## Checkpoints used in the FYP evaluation (SHA-256 verified from the files)

| Run / model | File | SHA-256 |
|---|---|---|
| v1 `fyp_s0`, episode 400 – `best.pt` (copy of `ckpt_best_ep0400.pt`; used in the v1 final evaluation) | `training_runs/fyp_s0/best.pt` | `0e1862889f6fd3237697048e26225dca567bfe474dae3a4cd51f29010fb4f9e7` |
| v1 `fyp_s0`, episode 400 – periodic checkpoint (used in the head-to-head) | `training_runs/fyp_s0/ckpt_ep0400.pt` | `8727962b06d1632daca1e3c0d1722de96e747d43af647cd543cc1d2dce737da3` |
| obs-v2 `fyp_s0_obs_v2`, episode 240 – `best.pt` (copy of `ckpt_best_ep0240.pt`; used in the obs-v2 final evaluation) | `training_runs/fyp_s0_obs_v2/best.pt` | `e7bc8722fe62b1cec0b9d4cf06038347050092c8a6ed6193f398f41683a97055` |
| obs-v2 `fyp_s0_obs_v2`, episode 240 – periodic checkpoint (recorded by the selection; used in the head-to-head) | `training_runs/fyp_s0_obs_v2/ckpt_ep0240.pt` | `7a30427d4e6e2b1de842dec397ba16e3633f7c0a79610decea626805c750fb14` |
| run configurations | `training_runs/fyp_s0/config.json`, `training_runs/fyp_s0_obs_v2/config.json` | `78593bc7fe46d4d18687421918ebd54c867e77d08737e103da9155aaf4e01c1b`, `f2e989ba29e6406e1034cb405eaf3378f41561902835edf1c213b8975b28b21b` |

For each run, `best.pt` and the periodic `ckpt_epNNNN.pt` of the same episode are **different files with different hashes** (they are written
separately by `save_checkpoint`) but contain **identical policy-network weights** (checked with `torch.equal` on every tensor for both
runs). Cite the file hash together with the file name; the same episode-240 obs-v2 model was used in selection, head-to-head and final evaluation.

## End-to-end procedure (training → selection → final evaluation)

1. **Train** with the commands above (`training_runs/<run-id>/`).
2. **Select a checkpoint** on trip-based validation waiting time (`EVALUATION_PROTOCOL.md` §9):
   `python select_checkpoint.py --run-dir training_runs/fyp_s0 --run-id sel_fyp_s0 --confirm-selection` (use `--plan` first; output
   `selection_runs/<run-id>/`). The CLI uses the v1 seed set (3,000,101 …, 3,000,201 …) and incumbent episode 400. The obs-v2 selection
   (`selection_runs/sel_fyp_s0_obs_v2/`) used the obs-v2 seed set and incumbent 240, which the CLI does not expose: it was run by a short
   driver calling `app.evaluation.selection.build_plan(run_dir, incumbent_episode=240, seed_set="obs-v2")` and the module's selection routine.
   That driver is **not stored** with the outputs; the plan it produced (`plan.json`, plan hash `4d2d68cb…`) and the decision are.
3. **Head-to-head (v1 vs obs-v2, validation seeds 3,000,601 – 3,000,630)**: not a standard project CLI command. It was run once by the
   driver script stored with its output, `evaluation_runs/h2h_v1ep400_vs_v2ep240_s0/head_to_head.py`, which calls the unchanged
   `app.evaluation.runner.run_episode` for each checkpoint in an environment of its own schema.
4. **Final evaluation** (once per checkpoint; `ledger.jsonl` refuses a repeat without `--allow-repeat-final`):
   `python evaluate_fyp.py --mode final --run-id fyp_final_s0 --controllers fixed_time rule_based actuated_style dqn --dqn-run training_runs/fyp_s0 --confirm-final` (seeds 4,000,001 – 4,000,030) and
   `python evaluate_fyp.py --mode final --run-id fyp_final_s0_obs_v2 --dqn-run training_runs/fyp_s0_obs_v2 --n-seeds 30 --seed-base 4000030 --confirm-final`
   (seeds 4,000,031 – 4,000,060); both commands are the stored `protocol.json` → `argv`. The record of all runs is `EVALUATION_PROTOCOL.md` §11.
