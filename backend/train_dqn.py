"""
IntelliRoads FYP – DQN training entry point (Stage 3).

Trains the mask-aware Double DQN on the corrected ``TrafficSignalEnv`` (all-lane observation, safe signal
actions with action masks).  It never touches the legacy environment, the tracked route file, the existing
model ``data/models/dqn_agent.pt`` or ``final_dqn_model/``: every run writes into a NEW directory
``training_runs/<run-id>/`` (see ``TRAINING_REPRODUCIBILITY.md``).

    python train_dqn.py --run-id my_run --seed 0                # real training (defaults: 400 x 1800 s episodes)
    python train_dqn.py --smoke --run-id check                  # tiny pipeline check, written to the system temp dir

``--smoke`` is a plumbing check (2 episodes of 60 s) and must never be reported as training.

This script replaces the former legacy trainer: its ``--epochs`` / ``--steps-per-epoch`` interface, its write to
``data/models/dqn_agent.pt`` and its ``dqn_training_stats`` database logging were removed (no caller in the repository used them).
The live application still loads the existing ``data/models/dqn_agent.pt``, which this script never writes.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path
from typing import Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.training.runs import DEFAULT_RUNS_ROOT  # noqa: E402
from app.environment.observation import OBS_SCHEMAS  # noqa: E402
from app.training.trainer import TrainConfig, train  # noqa: E402

SMOKE_PRESET = dict(episodes=2, horizon_s=60, val_every=1, val_n=1, warmup=32, batch_size=16, buffer_size=2000,
                    updates_per_decision=1, target_update_steps=5, eps_decay_decisions=20)


def build_parser() -> argparse.ArgumentParser:
    d = TrainConfig(run_id="x")
    p = argparse.ArgumentParser(description="Train the mask-aware Double DQN on TrafficSignalEnv.")
    p.add_argument("--run-id", required=True, help="name of the NEW output directory (must not exist)")
    p.add_argument("--out-root", type=Path, default=None, help=f"parent of the run directory (default {DEFAULT_RUNS_ROOT}; smoke: system temp)")
    p.add_argument("--seed", type=int, default=d.seed)
    p.add_argument("--episodes", type=int, default=d.episodes)
    p.add_argument("--horizon-s", type=int, default=d.horizon_s)
    p.add_argument("--decision-interval-s", type=int, default=d.decision_interval_s)
    p.add_argument("--train-seed-base", type=int, default=d.train_seed_base)
    p.add_argument("--val-seed-base", type=int, default=d.val_seed_base)
    p.add_argument("--val-every", type=int, default=d.val_every, help="episodes between validations")
    p.add_argument("--val-n", type=int, default=d.val_n, help="number of validation seeds")
    p.add_argument("--select-metric", default=d.select_metric, choices=["mean_wait_s", "mean_halting", "mean_reward"])
    p.add_argument("--patience", type=int, default=d.patience, help="stop after N validations without improvement (0 = never)")
    p.add_argument("--gamma", type=float, default=d.gamma)
    p.add_argument("--lr", type=float, default=d.lr)
    p.add_argument("--hidden", type=int, default=d.hidden)
    p.add_argument("--batch-size", type=int, default=d.batch_size)
    p.add_argument("--buffer-size", type=int, default=d.buffer_size)
    p.add_argument("--warmup", type=int, default=d.warmup, help="transitions collected with random legal actions before learning")
    p.add_argument("--updates-per-decision", type=int, default=d.updates_per_decision)
    p.add_argument("--target-update-steps", type=int, default=d.target_update_steps, help="gradient steps between hard target updates")
    p.add_argument("--eps-start", type=float, default=d.eps_start)
    p.add_argument("--eps-end", type=float, default=d.eps_end)
    p.add_argument("--eps-decay-decisions", type=int, default=None)
    p.add_argument("--reward-scale", type=float, default=d.reward_scale)
    p.add_argument("--grad-clip", type=float, default=d.grad_clip)
    p.add_argument("--obs-version", default=d.obs_version, choices=sorted(OBS_SCHEMAS), help="observation schema (default: the unchanged v1)")
    p.add_argument("--detector-range-m", type=float, default=d.detector_range_m, help="detector range of the v2 presence features (m)")
    p.add_argument("--smoke", action="store_true", help="tiny plumbing check (NOT training); output goes to the system temp dir")
    return p


def config_from_args(a: argparse.Namespace) -> TrainConfig:
    kw = dict(seed=a.seed, episodes=a.episodes, horizon_s=a.horizon_s, decision_interval_s=a.decision_interval_s,
              train_seed_base=a.train_seed_base, val_seed_base=a.val_seed_base, val_every=a.val_every, val_n=a.val_n,
              select_metric=a.select_metric, patience=a.patience, gamma=a.gamma, lr=a.lr, hidden=a.hidden,
              batch_size=a.batch_size, buffer_size=a.buffer_size, warmup=a.warmup, updates_per_decision=a.updates_per_decision,
              target_update_steps=a.target_update_steps, eps_start=a.eps_start, eps_end=a.eps_end,
              eps_decay_decisions=a.eps_decay_decisions, reward_scale=a.reward_scale, grad_clip=a.grad_clip,
              obs_version=a.obs_version, detector_range_m=a.detector_range_m)
    run_id, out_root = a.run_id, a.out_root
    if a.smoke:
        kw.update(SMOKE_PRESET, smoke=True)
        run_id = run_id if run_id.startswith("smoke") else f"smoke_{run_id}"
        out_root = out_root or Path(tempfile.gettempdir()) / "intelliroads_smoke_runs"
    return TrainConfig(run_id=run_id, out_root=out_root or DEFAULT_RUNS_ROOT, **kw)


def main(argv: Optional[Sequence[str]] = None) -> dict:
    args = build_parser().parse_args(argv)
    cfg = config_from_args(args)
    banner = "SMOKE CHECK (not a training run)" if cfg.smoke else "TRAINING"
    print(f"[{banner}] run '{cfg.run_id}' -> {cfg.out_root / cfg.run_id}")
    res = train(cfg, argv=list(argv) if argv is not None else sys.argv)
    print(f"[{banner}] done: episodes={res['episodes_run']} grad_steps={res['grad_steps']} "
          f"best episode={res['best_episode']} ({cfg.select_metric}={res['best_score']:.4f}) best={res['best_path']}")
    return res


if __name__ == "__main__":
    main()
