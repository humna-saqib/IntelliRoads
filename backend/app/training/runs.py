"""Dedicated output directories, checkpoints and validation-only checkpoint selection (Stage 3).

Safety rules
------------
* A run writes only into ``<out_root>/<run_id>/``, which must **not exist yet**; ``out_root`` may not be (or
  lie inside) any directory that holds existing models, checkpoints, evaluation results or route files.
* Checkpoints are never overwritten (``save_checkpoint`` refuses an existing path).  The only file that is
  rewritten during a run is the tiny ``best.json`` index.
* Routine checkpoints contain **no replay buffer**: it is large (10^5 transitions), is rebuilt in a few
  episodes, and is not needed to select, evaluate or deploy a model.  (Resuming training is not supported.)
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

import torch

BACKEND = Path(__file__).resolve().parents[2]
DEFAULT_RUNS_ROOT = BACKEND / "training_runs"
#: directories that hold existing artefacts of the project – a training run may never write into them
PROTECTED_DIRS = tuple(BACKEND / d for d in (
    "data", "final_dqn_model", "evaluation_results", "evaluation_v2", "validation_results", "sumo", "app", "tests", "comparison_graphs",
))
CHECKPOINT_FORMAT = "fyp-stage3-v1"          # 11-feature fyp-obs-v1 checkpoints (unchanged; still written by v1 runs)
CHECKPOINT_FORMAT_V2 = "fyp-ckpt-v2"          # Stage 5: always records obs_version, feature_names, state_size, detector_range_m
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")

#: metric -> True if lower is better
METRICS = {"mean_wait_s": True, "mean_halting": True, "mean_reward": False}


class RunDirError(RuntimeError):
    pass


def assert_output_root_allowed(out_root: Path) -> Path:
    """Pure check (touches nothing): raise ``RunDirError`` if ``out_root`` is, or lies inside, a protected directory."""
    root = Path(out_root).resolve()
    for p in PROTECTED_DIRS:
        p = Path(p).resolve()
        if root == p or p in root.parents:
            raise RunDirError(f"refusing to write training output into protected directory {p}")
    if root.exists() and not root.is_dir():
        raise RunDirError(f"{root} is not a directory")
    return root


def create_run_dir(out_root: Path, run_id: str) -> Path:
    if not _RUN_ID.match(run_id):
        raise RunDirError(f"invalid run id {run_id!r} (use letters, digits, '_', '-', '.')")
    root = assert_output_root_allowed(out_root)
    path = root / run_id
    if path.exists():
        raise RunDirError(f"run directory {path} already exists – choose a new --run-id (existing runs are never overwritten)")
    path.mkdir(parents=True)
    return path


class CheckpointSchemaError(RunDirError):
    """A checkpoint's observation schema is missing, inconsistent, or does not match the environment."""


def checkpoint_schema(ck: Dict[str, Any]) -> Dict[str, Any]:
    """Strictly validated observation schema of a loaded checkpoint dict: ``{obs_version, feature_names, state_size, detector_range_m}``.

    * ``fyp-stage3-v1`` -> always ``fyp-obs-v1``: state size 11 and, if feature names were stored, exactly the v1 names.
    * ``fyp-ckpt-v2``   -> the recorded ``obs_version``, whose names, size and (for v2) detector range must all be consistent.
    Anything else (e.g. the legacy 5-feature model) raises ``CheckpointSchemaError``.  Nothing is ever reshaped."""
    from app.environment.observation import OBS_V1, OBS_V2, check_detector_range, schema_feature_names
    fmt = ck.get("format")
    if fmt == CHECKPOINT_FORMAT:
        names = tuple(ck.get("feature_names") or ())
        v1 = schema_feature_names(OBS_V1)
        if ck.get("state_size") != len(v1) or (names and names != v1):
            raise CheckpointSchemaError(f"{CHECKPOINT_FORMAT} checkpoint is not a valid fyp-obs-v1 model "
                                        f"(state_size={ck.get('state_size')}, feature_names={list(names)[:3]}...)")
        return {"obs_version": OBS_V1, "feature_names": v1, "state_size": len(v1), "detector_range_m": None}
    if fmt == CHECKPOINT_FORMAT_V2:
        ver = ck.get("obs_version")
        try:
            names = schema_feature_names(ver)
        except Exception as exc:
            raise CheckpointSchemaError(f"{CHECKPOINT_FORMAT_V2} checkpoint has an unknown obs_version {ver!r}") from exc
        if tuple(ck.get("feature_names") or ()) != names or ck.get("state_size") != len(names):
            raise CheckpointSchemaError(f"{CHECKPOINT_FORMAT_V2} checkpoint: feature names / state size do not match schema {ver}")
        rng = ck.get("detector_range_m")
        if ver == OBS_V2:
            try:
                rng = check_detector_range(rng)
            except Exception as exc:
                raise CheckpointSchemaError(f"{CHECKPOINT_FORMAT_V2} checkpoint has an invalid detector range {rng!r}") from exc
        return {"obs_version": ver, "feature_names": names, "state_size": len(names), "detector_range_m": rng}
    raise CheckpointSchemaError(f"not a {CHECKPOINT_FORMAT} or {CHECKPOINT_FORMAT_V2} checkpoint (format={fmt!r}); "
                                f"the legacy 5-feature model cannot drive the corrected environment")


def assert_schema_matches(schema: Dict[str, Any], obs_version: str, detector_range_m: Optional[float]) -> None:
    """Refuse to pair a checkpoint with an environment of a different observation schema (or v2 detector range)."""
    if schema["obs_version"] != obs_version:
        raise CheckpointSchemaError(f"checkpoint uses observation schema {schema['obs_version']}, the environment provides {obs_version}")
    if schema["detector_range_m"] is not None and detector_range_m is not None and abs(float(schema["detector_range_m"]) - float(detector_range_m)) > 1e-9:
        raise CheckpointSchemaError(f"checkpoint was trained with detector range {schema['detector_range_m']} m, the environment uses {detector_range_m} m")


def save_checkpoint(path: Path, agent: Any, *, episode: int, decisions: int, val_score: Optional[float], val_metric: str,
                    train_config: Dict[str, Any], feature_names=(), obs_version: Optional[str] = None,
                    detector_range_m: Optional[float] = None) -> None:
    """Write a model-only checkpoint; refuses to replace an existing file.

    ``obs_version`` None or ``fyp-obs-v1`` writes the unchanged ``fyp-stage3-v1`` payload; any other schema writes ``fyp-ckpt-v2``
    with the schema recorded (and validated before writing)."""
    path = Path(path)
    if path.exists():
        raise RunDirError(f"refusing to overwrite existing checkpoint {path}")
    from app.environment.observation import OBS_V1
    payload = {
        "format": CHECKPOINT_FORMAT,
        "policy_net": agent.policy_net.state_dict(), "target_net": agent.target_net.state_dict(),
        "optimizer": agent.optimizer.state_dict(), "grad_steps": agent.grad_steps,
        "episode": episode, "decisions": decisions, "val_score": val_score, "val_metric": val_metric,
        "state_size": agent.state_size, "n_actions": agent.n_actions, "train_config": train_config,
        "feature_names": list(feature_names),
    }
    if obs_version is not None and obs_version != OBS_V1:
        payload.update(format=CHECKPOINT_FORMAT_V2, obs_version=obs_version, detector_range_m=detector_range_m)
        checkpoint_schema(payload)                                       # refuse to write an inconsistent v2 checkpoint
        if payload["state_size"] != len(payload["feature_names"]):
            raise CheckpointSchemaError("agent state size does not match the feature names")
    tmp = path.with_suffix(".tmp")
    torch.save(payload, str(tmp))
    os.replace(tmp, path)                     # the target did not exist (checked above)


def load_checkpoint(path: Path, agent: Any) -> Dict[str, Any]:
    ck = torch.load(str(path), map_location="cpu", weights_only=False)
    if ck.get("format") not in (CHECKPOINT_FORMAT, CHECKPOINT_FORMAT_V2):
        raise RunDirError(f"{path} is not a {CHECKPOINT_FORMAT} checkpoint")
    checkpoint_schema(ck)
    if ck["state_size"] != agent.state_size or ck["n_actions"] != agent.n_actions:
        raise RunDirError("checkpoint dimensions do not match the agent")
    agent.policy_net.load_state_dict(ck["policy_net"])
    agent.target_net.load_state_dict(ck["target_net"])
    agent.optimizer.load_state_dict(ck["optimizer"])
    agent.grad_steps = ck["grad_steps"]
    return ck


class CheckpointSelector:
    """Keeps the best checkpoint according to a **validation** metric only.

    ``update`` accepts nothing but an episode number and a validation score, so training-episode returns,
    losses or any evaluation-seed result cannot influence which checkpoint is selected.  Ties keep the earlier one.
    """

    def __init__(self, metric: str) -> None:
        if metric not in METRICS:
            raise ValueError(f"unknown selection metric {metric!r}; choose from {sorted(METRICS)}")
        self.metric, self.lower_is_better = metric, METRICS[metric]
        self.best_episode: Optional[int] = None
        self.best_score: Optional[float] = None

    def update(self, episode: int, val_score: float) -> bool:
        if val_score != val_score or val_score in (float("inf"), float("-inf")):
            raise ValueError("validation score must be finite")
        better = (self.best_score is None or (val_score < self.best_score if self.lower_is_better else val_score > self.best_score))
        if better:
            self.best_episode, self.best_score = episode, float(val_score)
        return better


def write_json_atomic(path: Path, obj: Any) -> None:
    tmp = Path(path).with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)


def finalize_best(run_dir: Path, best_file: Path) -> Path:
    """Create ``best.pt`` as a copy of the selected checkpoint (a new file, never replacing one).

    The copy is written to a unique temporary file, flushed and fsync'ed, then published with ``os.link`` – atomic, and it fails if
    ``best.pt`` already exists, even under concurrent execution.  Any failure removes the temporary file, so a truncated ``best.pt``
    can never appear.  **Requirement:** the run directory must be on a filesystem with hard links (ext4, xfs, btrfs, overlayfs, tmpfs
    – the development container uses ext4).  Without hard-link support finalisation fails with a clear error and writes no ``best.pt``;
    the selected ``ckpt_best_epNNNN.pt`` and ``best.json`` remain the record of the selection.  (No rename fallback: ``os.rename``
    cannot refuse an existing target atomically.)"""
    run_dir = Path(run_dir)
    dst = run_dir / "best.pt"
    if dst.exists():
        raise RunDirError(f"refusing to overwrite {dst}")
    fd, tmp_name = tempfile.mkstemp(prefix=".best.pt.", suffix=".tmp", dir=run_dir)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as out, open(best_file, "rb") as src:
            shutil.copyfileobj(src, out)
            out.flush()
            os.fsync(out.fileno())
        try:
            os.link(tmp, dst)                       # atomic publish; refuses an existing target (no silent overwrite)
        except FileExistsError as exc:
            raise RunDirError(f"refusing to overwrite {dst}") from exc
        except OSError as exc:
            raise RunDirError(f"cannot publish {dst}: the filesystem of {run_dir} must support hard links ({exc})") from exc
        dir_fd = os.open(run_dir, os.O_RDONLY)
        try:
            os.fsync(dir_fd)                        # make the new directory entry durable
        finally:
            os.close(dir_fd)
    finally:
        tmp.unlink(missing_ok=True)                 # always: after a failed copy, a refused or a successful publish
    return dst
