"""Training loop, greedy validation and hyper-parameters (Stage 3).

``train(cfg)`` trains the mask-aware Double DQN on ``TrafficSignalEnv`` (corrected observation, safe actions):

* every episode uses a fresh training seed (``seeds.train_seed``); SUMO's seed and the demand follow from it;
* transitions (4 per decision – one per junction, shared policy) are stored with current- and next-state masks;
* **warm-up**: until the buffer holds ``warmup`` transitions, actions are uniformly random *legal* actions and
  no gradient step is taken;
* **target network**: hard update every ``target_update_steps`` *gradient steps*;
* **validation**: every ``val_every`` episodes the greedy policy is run on the fixed validation seeds; the
  checkpoint with the best validation score is selected – nothing else is used for selection;
* output goes to a new ``<out_root>/<run_id>/`` directory (see ``runs``): ``config.json``, ``episodes.csv``,
  ``validation.csv``, ``best.json``, model-only checkpoints, ``timing.json`` (wall-clock, the only non-reproducible file).
"""

from __future__ import annotations

import csv
import dataclasses
import hashlib
import platform
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import torch

from app.environment.observation import (DEFAULT_DETECTOR_RANGE_M, FEATURE_NAMES, OBS_V1, STATE_SIZE, check_detector_range,
                                         schema_feature_names, schema_state_size)
from app.environment.traffic_env import EnvConfig, TrafficSignalEnv, replay_done_flag
from app.training import seeds as S
from app.training.double_dqn import MaskedDoubleDQN
from app.training.replay import MaskedReplayBuffer
from app.training.runs import (
    BACKEND as BACKEND_DIR,
    DEFAULT_RUNS_ROOT,
    METRICS,
    CheckpointSelector,
    create_run_dir,
    finalize_best,
    save_checkpoint,
    write_json_atomic,
)


@dataclass(frozen=True)
class TrainConfig:
    run_id: str
    out_root: Path = DEFAULT_RUNS_ROOT
    seed: int = 0
    # episodes / environment
    episodes: int = 400
    horizon_s: int = 1800
    decision_interval_s: int = 5
    # seeds
    train_seed_base: int = S.TRAIN_SEED_BASE
    val_seed_base: int = S.VAL_SEED_BASE
    # validation / selection
    val_every: int = 20
    val_n: int = 5
    select_metric: str = "mean_wait_s"
    patience: int = 0                       # stop after this many validations without improvement; 0 = never
    # learning
    gamma: float = 0.95
    lr: float = 5e-4
    hidden: int = 64
    batch_size: int = 64
    buffer_size: int = 50_000
    warmup: int = 1000                      # transitions collected with random legal actions before learning starts
    updates_per_decision: int = 4
    target_update_steps: int = 500          # gradient steps between hard target updates
    eps_start: float = 1.0
    eps_end: float = 0.05
    eps_decay_decisions: Optional[int] = None   # decisions after warm-up; default = half of the planned decisions
    reward_scale: float = 0.01              # rewards are multiplied by this before learning (hyper-parameter, untuned)
    grad_clip: float = 1.0
    smoke: bool = False                     # marks a tiny pipeline check – NOT a real training run
    obs_version: str = OBS_V1               # Stage 5: observation schema (v1 = the unchanged 11 features)
    detector_range_m: float = DEFAULT_DETECTOR_RANGE_M   # Stage 5: range of the v2 presence features (ignored by v1)

    def __post_init__(self) -> None:
        if self.episodes < 1 or self.val_every < 1 or self.val_n < 1:
            raise ValueError("episodes, val_every and val_n must be >= 1")
        if self.select_metric not in METRICS:
            raise ValueError(f"select_metric must be one of {sorted(METRICS)}")
        if self.warmup < self.batch_size:
            raise ValueError("warmup must be >= batch_size")
        if self.buffer_size < self.warmup:
            raise ValueError("buffer_size must be >= warmup")
        if min(self.updates_per_decision, self.target_update_steps, self.batch_size) < 1:
            raise ValueError("updates_per_decision, target_update_steps and batch_size must be >= 1")
        if not 0.0 <= self.eps_end <= self.eps_start <= 1.0:
            raise ValueError("need 0 <= eps_end <= eps_start <= 1")
        try:
            schema_feature_names(self.obs_version)
            check_detector_range(self.detector_range_m)
        except Exception as exc:
            raise ValueError(str(exc)) from exc

    @property
    def decay_decisions(self) -> int:
        if self.eps_decay_decisions is not None:
            return max(1, self.eps_decay_decisions)
        return max(1, int(0.5 * self.episodes * self.horizon_s / self.decision_interval_s))

    def epsilon(self, decisions_after_warmup: int) -> float:
        frac = min(1.0, decisions_after_warmup / self.decay_decisions)
        return self.eps_start + (self.eps_end - self.eps_start) * frac


def evaluate_policy(agent: MaskedDoubleDQN, env: TrafficSignalEnv, seeds: Sequence[int]) -> Dict[str, float]:
    """Greedy (epsilon = 0) rollouts with legal-action masks on ``seeds``; returns the mean validation metrics."""
    waits, halts, rewards = [], [], []
    for seed in seeds:
        S.assert_not_protected(seed)
        obs = env.reset(seed)
        masks = env.action_masks()
        w, h, r = [], [], []
        while True:
            res = env.step({j: agent.greedy(obs[j], masks[j]) for j in env.cfg.junction_ids})
            js = env.cfg.junction_ids
            w.append(np.mean([res.info["metrics"][j].mean_wait_s for j in js]))
            h.append(np.mean([res.info["metrics"][j].halting for j in js]))
            r.append(np.mean([res.rewards[j] for j in js]))
            obs, masks = res.obs, res.info["action_masks"]
            if res.terminated or res.truncated:
                break
        waits.append(np.mean(w)); halts.append(np.mean(h)); rewards.append(np.mean(r))
    return {"mean_wait_s": float(np.mean(waits)), "mean_halting": float(np.mean(halts)), "mean_reward": float(np.mean(rewards))}


def _git_commit() -> Optional[str]:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=Path(__file__).parent, capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or None
    except Exception:
        return None


def _git_dirty() -> Optional[bool]:
    try:
        out = subprocess.run(["git", "status", "--porcelain", "--", str(BACKEND_DIR)], cwd=Path(__file__).parent, capture_output=True,
                             text=True, timeout=10)
        return bool(out.stdout.strip()) if out.returncode == 0 else None
    except Exception:
        return None


def _source_hashes() -> Dict[str, str]:
    """SHA-256 of every source file that determines a run (reproducible even when the working tree is uncommitted)."""
    files = sorted((BACKEND_DIR / "app" / "training").glob("*.py")) + sorted((BACKEND_DIR / "app" / "environment").glob("*.py")) + [
        BACKEND_DIR / "train_dqn.py", BACKEND_DIR / "app" / "agent" / "dqn_agent.py", BACKEND_DIR / "app" / "sumo_tools" / "route_generator.py",
        BACKEND_DIR / "sumo" / "network" / "intelliroads.net.xml", BACKEND_DIR / "sumo" / "config" / "intelliroads.sumocfg"]
    return {str(f.relative_to(BACKEND_DIR)): hashlib.sha256(f.read_bytes()).hexdigest() for f in files}


def _jsonable(cfg: TrainConfig) -> Dict[str, Any]:
    d = dataclasses.asdict(cfg)
    d["out_root"] = str(cfg.out_root)
    return d


def _write_csv_row(path: Path, header: List[str], row: List[Any]) -> None:
    new = not path.exists()
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(header)
        w.writerow(row)


EPISODE_HEADER = ["episode", "seed", "epsilon", "decisions", "transitions", "buffer", "grad_steps", "mean_reward", "mean_loss",
                  "mean_q", "terminated", "truncated", "target_syncs"]
VAL_HEADER = ["episode", "grad_steps", "select_metric", "score", "mean_wait_s", "mean_halting", "mean_reward", "is_best", "seeds"]


def _close_envs(*envs: Optional[TrafficSignalEnv], suppress: bool = False) -> None:
    """Close every environment even if an earlier ``close()`` fails; re-raise the first failure unless ``suppress``."""
    first: Optional[BaseException] = None
    for e in envs:
        if e is None:
            continue
        try:
            e.close()
        except Exception as exc:                              # noqa: BLE001 - every environment must get its close() call
            first = first or exc
    if first is not None and not suppress:
        raise first


def train(cfg: TrainConfig, argv: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """Run one training run into a **new** directory and return a summary. Never touches existing artefacts."""
    train_seeds = [S.train_seed(e, cfg.train_seed_base) for e in range(1, cfg.episodes + 1)]
    val_seed_list = S.val_seeds(cfg.val_n, cfg.val_seed_base)
    S.assert_training_seed_plan(train_seeds, val_seed_list)
    S.check_seed(cfg.seed)                                   # every configuration check happens before the run directory exists

    run_dir = create_run_dir(cfg.out_root, cfg.run_id)
    S.seed_everything(cfg.seed)
    env_cfg = EnvConfig(horizon_s=cfg.horizon_s, decision_interval_s=cfg.decision_interval_s,
                        obs_version=cfg.obs_version, detector_range_m=cfg.detector_range_m)
    feature_names, state_size = schema_feature_names(cfg.obs_version), schema_state_size(cfg.obs_version)
    agent = MaskedDoubleDQN(state_size, 4, cfg.hidden, cfg.gamma, cfg.lr, cfg.grad_clip, cfg.seed)
    buffer = MaskedReplayBuffer(cfg.buffer_size, state_size, seed=cfg.seed)
    selector = CheckpointSelector(cfg.select_metric)
    t0 = time.time()
    decisions = learn_decisions = target_syncs = 0
    since_best = 0
    best_file: Optional[Path] = None
    stopped_early = False
    meta = {
        "config": _jsonable(cfg), "argv": list(argv) if argv is not None else sys.argv, "smoke": cfg.smoke,
        "train_seeds": [train_seeds[0], train_seeds[-1]], "val_seeds": val_seed_list, "protected_seed_ranges": [list(r) for r in S.PROTECTED_RANGES],
        "feature_names": list(feature_names), "obs_version": cfg.obs_version,
        "detector_range_m": cfg.detector_range_m if cfg.obs_version != OBS_V1 else None, "git_commit": _git_commit(), "git_dirty": _git_dirty(),
        "source_sha256": _source_hashes(),
        "versions": {"python": platform.python_version(), "numpy": np.__version__, "torch": torch.__version__, "sumo": None},
    }
    write_json_atomic(run_dir / "config.json", meta)         # persisted at once; the SUMO version is added after the first reset
    env = val_env = None
    try:
        env, val_env = TrafficSignalEnv(env_cfg), TrafficSignalEnv(env_cfg)
        for ep in range(1, cfg.episodes + 1):
            seed = train_seeds[ep - 1]
            obs = env.reset(seed)
            masks = env.action_masks()
            if ep == 1:
                meta["versions"]["sumo"] = env.conn.getVersion()[1] if env.conn is not None else None
                write_json_atomic(run_dir / "config.json", meta)
            losses, qs, rewards = [], [], []
            n_trans = 0
            while True:
                warming = len(buffer) < cfg.warmup
                eps = cfg.epsilon(learn_decisions)
                actions = {j: (agent.random_legal(masks[j]) if warming else agent.act(obs[j], masks[j], eps)) for j in env.cfg.junction_ids}
                res = env.step(actions)
                next_masks = res.info["action_masks"]
                done_flag = replay_done_flag(res.terminated, res.truncated)
                for j in env.cfg.junction_ids:
                    buffer.push(obs[j], actions[j], res.rewards[j] * cfg.reward_scale, res.obs[j], done_flag, res.truncated,
                                masks[j], next_masks[j])
                    rewards.append(res.rewards[j])
                    n_trans += 1
                decisions += 1
                if not warming:
                    learn_decisions += 1
                if len(buffer) >= cfg.warmup:                         # warm-up complete -> learn
                    for _ in range(cfg.updates_per_decision):
                        loss, q = agent.train_step(buffer.sample(cfg.batch_size, agent.device))
                        target_syncs += int(agent.maybe_sync_target(cfg.target_update_steps))
                        losses.append(loss); qs.append(q)
                obs, masks = res.obs, next_masks
                if res.terminated or res.truncated:
                    break
            _write_csv_row(run_dir / "episodes.csv", EPISODE_HEADER, [
                ep, seed, cfg.epsilon(learn_decisions), decisions, n_trans, len(buffer), agent.grad_steps,
                float(np.mean(rewards)), float(np.mean(losses)) if losses else "", float(np.mean(qs)) if qs else "",
                res.terminated, res.truncated, target_syncs])

            if ep % cfg.val_every == 0 or ep == cfg.episodes:
                metrics = evaluate_policy(agent, val_env, val_seed_list)
                score = metrics[cfg.select_metric]
                improved = selector.update(ep, score)
                if improved:
                    since_best = 0
                    best_file = run_dir / f"ckpt_best_ep{ep:04d}.pt"
                    save_checkpoint(best_file, agent, episode=ep, decisions=decisions, val_score=score, val_metric=cfg.select_metric,
                                    train_config=meta["config"], feature_names=feature_names, obs_version=cfg.obs_version,
                                    detector_range_m=cfg.detector_range_m)
                    write_json_atomic(run_dir / "best.json", {"episode": ep, "score": score, "metric": cfg.select_metric, "file": best_file.name})
                else:
                    since_best += 1
                save_checkpoint(run_dir / f"ckpt_ep{ep:04d}.pt", agent, episode=ep, decisions=decisions, val_score=score,
                                val_metric=cfg.select_metric, train_config=meta["config"], feature_names=feature_names, obs_version=cfg.obs_version,
                                    detector_range_m=cfg.detector_range_m)
                _write_csv_row(run_dir / "validation.csv", VAL_HEADER, [
                    ep, agent.grad_steps, cfg.select_metric, score, metrics["mean_wait_s"], metrics["mean_halting"],
                    metrics["mean_reward"], improved, " ".join(map(str, val_seed_list))])
                if cfg.patience and since_best >= cfg.patience:
                    stopped_early = True
                    break
        last_ep = ep
        save_checkpoint(run_dir / "last.pt", agent, episode=last_ep, decisions=decisions, val_score=None, val_metric=cfg.select_metric,
                        train_config=meta["config"], feature_names=feature_names, obs_version=cfg.obs_version,
                                    detector_range_m=cfg.detector_range_m)
        best_path = finalize_best(run_dir, best_file) if best_file else None
    except BaseException:
        _close_envs(env, val_env, suppress=True)             # keep the original error; still close both simulations
        raise
    _close_envs(env, val_env)
    write_json_atomic(run_dir / "timing.json", {"wall_seconds": round(time.time() - t0, 2)})
    return {"run_dir": run_dir, "best_episode": selector.best_episode, "best_score": selector.best_score, "best_path": best_path,
            "last_path": run_dir / "last.pt", "grad_steps": agent.grad_steps, "decisions": decisions, "episodes_run": last_ep,
            "stopped_early": stopped_early, "smoke": cfg.smoke, "buffer": buffer}
