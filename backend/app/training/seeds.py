"""Reproducible seeding and seed-range bookkeeping (Stage 3).

One integer ``seed`` fixes Python's ``random``, NumPy, PyTorch (weights, replay sampling and
exploration use generators derived from it) and, through ``TrafficSignalEnv.reset(episode_seed)``,
SUMO's ``--seed`` and the generated traffic demand of every episode.

Seed ranges (all disjoint, none of them overlaps the seeds used by the legacy evaluation script):

* training episodes   ``TRAIN_SEED_BASE + episode``            (2,000,001 ...)
* validation episodes ``VAL_SEED_BASE + 1 .. val_n``            (3,000,001 ...)  – checkpoint selection only
* PROTECTED: the legacy evaluation seeds ``1,000,001 ... 1,999,999`` used by ``evaluate_controllers.py``,
  the range ``4,000,000 ... 4,999,999`` reserved for the final evaluation, and ``5,000,000 ... 5,999,999`` used
  only to smoke-check the evaluation protocol (Stage 4).  Training and validation refuse to run on a protected
  seed, so a model can never be tuned on evaluation traffic.
"""

from __future__ import annotations

import random
from typing import List, Tuple

import numpy as np
import torch

TRAIN_SEED_BASE = 2_000_000
VAL_SEED_BASE = 3_000_000
PROTECTED_RANGES: Tuple[Tuple[int, int, str], ...] = (
    (1_000_000, 1_999_999, "legacy evaluation seeds (evaluate_controllers.py)"),
    (4_000_000, 4_999_999, "reserved for the final evaluation"),
    (5_000_000, 5_999_999, "evaluation-protocol smoke-check seeds (never used for training or selection)"),
    # Stage 6 (additive): seeds reserved for the obs-v2 checkpoint selection and head-to-head comparison
    (3_000_401, 3_000_410, "reserved: obs-v2 selection stage A"),
    (3_000_501, 3_000_520, "reserved: obs-v2 selection stage B"),
    (3_000_601, 3_000_630, "reserved: obs-v2 head-to-head validation"),
)


#: allowed ranges of a training run (inclusive): training episodes stay in 2,xxx,xxx; training-time validation stays below the
#: checkpoint-selection seeds (3,000,100 and above, app.evaluation.seeds.SELECTION_RANGE)
TRAIN_SEED_RANGE = (2_000_000, 2_999_999)
VAL_SEED_RANGE = (3_000_001, 3_000_099)
MAX_VAL_N = VAL_SEED_RANGE[1] - VAL_SEED_RANGE[0] + 1          # 99


class SeedError(ValueError):
    """A seed outside its allowed range was requested."""


def train_seed(episode: int, base: int = TRAIN_SEED_BASE) -> int:
    if episode < 1:
        raise SeedError("episodes are numbered from 1")
    return assert_not_protected(base + episode)


def val_seeds(n: int, base: int = VAL_SEED_BASE) -> List[int]:
    if n < 1:
        raise SeedError("need at least one validation seed")
    if n > MAX_VAL_N:
        raise SeedError(f"--val-n must be <= {MAX_VAL_N}: more validation seeds would reach the checkpoint-selection seeds (3,000,100 ...)")
    return [assert_not_protected(base + i) for i in range(1, n + 1)]


def assert_not_protected(seed: int) -> int:
    for lo, hi, why in PROTECTED_RANGES:
        if lo <= seed <= hi:
            raise SeedError(f"seed {seed} is protected ({why})")
    return seed


def assert_disjoint(train: List[int], val: List[int]) -> None:
    both = set(train) & set(val)
    if both:
        raise SeedError(f"training and validation seeds overlap: {sorted(both)[:5]}")


def check_seed(seed: int) -> int:
    """The global ``--seed`` must fit NumPy/PyTorch seeding."""
    if not isinstance(seed, (int, np.integer)) or isinstance(seed, bool) or not 0 <= seed < 2 ** 32:
        raise SeedError(f"seed must be an integer in [0, 2**32), got {seed!r}")
    return int(seed)


def assert_training_seed_plan(train: List[int], val: List[int]) -> None:
    """Training episodes must lie in 2,000,000 - 2,999,999 and validation in 3,000,001 - 3,000,099 (checked before any output is created)."""
    for name, seeds, (lo, hi) in (("training", train, TRAIN_SEED_RANGE), ("validation", val, VAL_SEED_RANGE)):
        bad = [sd for sd in seeds if not lo <= sd <= hi]
        if bad:
            raise SeedError(f"{name} seeds must lie in {lo:,} - {hi:,}; got {bad[0]:,} (check --train-seed-base / --val-seed-base / --val-n / --episodes)")
    assert_disjoint(train, val)


def seed_everything(seed: int) -> None:
    """Seed Python, NumPy and PyTorch and make CPU PyTorch single-threaded and deterministic.

    The code never relies on hash ordering; ``TRAINING_REPRODUCIBILITY.md`` still tells users to export
    ``PYTHONHASHSEED`` for completeness (it cannot be changed for an already running interpreter).
    """
    seed = check_seed(seed)
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():                      # pragma: no cover - CPU-only container
        torch.cuda.manual_seed_all(seed)
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
