"""Evaluation protocol definition, signal-timing verification, checkpoint loading and the evaluation ledger (Stage 4)."""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import torch

from app.environment.observation import STATE_SIZE
from app.training.double_dqn import MaskedDoubleDQN
from app.training.runs import CHECKPOINT_FORMAT, checkpoint_schema

BACKEND = Path(__file__).resolve().parents[2]
DEFAULT_NET_XML = BACKEND / "sumo" / "network" / "intelliroads.net.xml"
DEFAULT_EVAL_ROOT = BACKEND / "evaluation_runs"
JUNCTIONS = ("junctionA", "junctionB", "junctionC", "junctionD")
CONTROLLER_ORDER = ("fixed_time", "rule_based", "actuated_style", "dqn")


class ProtocolError(RuntimeError):
    """The evaluation protocol was violated or could not be verified."""


@dataclass(frozen=True)
class EvalProtocol:
    """Everything that defines one evaluation, identical for every controller.

    An episode has three parts: a warm-up (``warmup_s``), the measured window (``measure_s``) and a **drain** of at most
    ``drain_max_s``.  Demand is inserted from t = 0 until the end of the measured window and then stops, so the drain
    only lets the vehicles already in the network finish; the episode ends as soon as the network is empty or when the
    maximum drain is used up.  Controllers act in all three parts.  **Nothing from the warm-up or the drain enters the
    lane statistics**, which use the steps that start in ``[warmup_s, warmup_s + measure_s)``; trip statistics use the
    vehicles that depart in the measured window, followed until they arrive or until the drain ends.
    """

    warmup_s: int = 300
    measure_s: int = 1800
    decision_interval_s: int = 5
    n_seeds: int = 30
    drain_max_s: int = 600                   # maximum drain after the measured window (no new demand; ends earlier when the network is empty)
    mode: str = "final"                      # 'final' (reported), 'smoke' (plumbing check) or 'validation' (checkpoint selection only)

    def __post_init__(self) -> None:
        if self.mode not in ("final", "smoke", "validation"):
            raise ProtocolError("mode must be 'final', 'smoke' or 'validation'")
        if self.warmup_s < 0 or self.measure_s < 1 or self.decision_interval_s < 1 or self.n_seeds < 1:
            raise ProtocolError("warmup_s >= 0, measure_s >= 1, decision_interval_s >= 1, n_seeds >= 1 required")
        if self.warmup_s % self.decision_interval_s or self.measure_s % self.decision_interval_s:
            raise ProtocolError("warmup_s and measure_s must be multiples of decision_interval_s")
        if self.drain_max_s < 0 or self.drain_max_s % self.decision_interval_s:
            raise ProtocolError("drain_max_s must be >= 0 and a multiple of decision_interval_s")

    @property
    def demand_end_s(self) -> int:
        """Time at which new demand stops = end of the measured window."""
        return self.warmup_s + self.measure_s

    @property
    def horizon_s(self) -> int:
        """Latest possible end of an episode: warm-up + measured window + maximum drain."""
        return self.demand_end_s + self.drain_max_s


# ------------------------------------------------------------------ the configured SUMO programme
def program_from_net(net_xml: Path = DEFAULT_NET_XML) -> Dict[str, List[Tuple[float, str]]]:
    """``{junction: [(duration_s, state), ...]}`` read from the ``tlLogic`` elements of the network file."""
    root = ET.parse(net_xml).getroot()
    out: Dict[str, List[Tuple[float, str]]] = {}
    for tl in root.findall("tlLogic"):
        out[tl.get("id")] = [(float(p.get("duration")), p.get("state")) for p in tl.findall("phase")]
    return out


def verify_fixed_time_timing(signal_log: Sequence[Mapping[str, Any]], program: Mapping[str, Sequence[Tuple[float, str]]],
                             junctions: Sequence[str] = JUNCTIONS, min_phases: int = 8) -> Dict[str, Any]:
    """Check that the *actual* phase durations equal SUMO's configured programme, phase for phase.

    ``signal_log`` is ``TrafficSignalEnv.signal_log`` (completed phases with scheduled start and duration, built from
    per-second TraCI polls).  Every junction must show the programme's cycle in order, every duration equal to the
    configured one (no drift: a 31 s green or 6 s yellow is a mismatch), and at least ``min_phases`` completed phases.
    Raises ``ProtocolError`` on any mismatch and returns a per-junction report otherwise.
    """
    report: Dict[str, Any] = {}
    problems: List[str] = []
    for j in junctions:
        if j not in program:
            raise ProtocolError(f"no configured programme for {j}")
        durations = [d for d, _ in program[j]]
        n = len(durations)
        entries = [e for e in signal_log if e["junction"] == j]
        report[j] = {"configured_durations": durations, "completed_phases": len(entries)}
        if len(entries) < min_phases:
            problems.append(f"{j}: only {len(entries)} completed phases (need >= {min_phases}) to verify the timing")
        for k, e in enumerate(entries):
            want_phase = (entries[0]["phase"] + k) % n
            if e["phase"] != want_phase:
                problems.append(f"{j}: phase #{k} is {e['phase']}, programme order requires {want_phase}")
            if abs(e["duration_s"] - durations[e["phase"]]) > 1e-9:
                problems.append(f"{j}: phase {e['phase']} #{k} lasted {e['duration_s']:g}s, configured {durations[e['phase']]:g}s")
        if entries and entries[0]["phase"] != 0:
            problems.append(f"{j}: the episode did not start in phase 0")
    report["ok"] = not problems
    report["problems"] = problems
    if problems:
        raise ProtocolError("fixed-time baseline does not follow SUMO's configured programme: " + "; ".join(problems[:6]))
    return report


# ------------------------------------------------------------------ validation-selected checkpoints only
def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _schema_or_refuse(ck: Dict[str, Any], path: Path) -> Dict[str, Any]:
    """Validated observation schema of a checkpoint (``fyp-stage3-v1`` = 11-feature v1; ``fyp-ckpt-v2`` = recorded schema).
    The agent is then built with exactly that input size - weights are never reshaped or partially loaded."""
    try:
        return checkpoint_schema(ck)
    except Exception as exc:
        raise ProtocolError(f"{path} is not a usable {CHECKPOINT_FORMAT}/fyp-ckpt-v2 checkpoint: {exc} "
                            f"(the legacy 5-feature model cannot drive the corrected environment)") from exc


def load_validation_selected_checkpoint(run_dir: Path) -> Tuple[MaskedDoubleDQN, Dict[str, Any]]:
    """Load the checkpoint a *training run selected on validation seeds* (``best.json`` / ``best.pt``) – and nothing else.

    The final evaluation therefore cannot pick a checkpoint by looking at test results: the only loadable model is the
    one whose selection is recorded, with its validation score, by the training run.  The legacy 5-feature checkpoint
    (``data/models/dqn_agent.pt``) is incompatible with the corrected 11-feature environment and is refused.
    """
    run_dir = Path(run_dir)
    best_json = run_dir / "best.json"
    best_pt = run_dir / "best.pt"
    if not best_json.is_file() or not best_pt.is_file():
        raise ProtocolError(f"{run_dir} has no best.json/best.pt – evaluate only runs finished by train_dqn.py")
    best = json.loads(best_json.read_text())
    selected = run_dir / best["file"]
    if not selected.is_file() or sha256_file(selected) != sha256_file(best_pt):
        raise ProtocolError("best.pt does not match the checkpoint recorded in best.json (the selection was altered)")
    ck = torch.load(str(best_pt), map_location="cpu", weights_only=False)
    schema = _schema_or_refuse(ck, best_pt)
    if ck.get("val_score") is None or abs(float(ck["val_score"]) - float(best["score"])) > 1e-9:
        raise ProtocolError("checkpoint is not the validation-selected one (missing or inconsistent validation score)")
    agent = MaskedDoubleDQN(ck["state_size"], ck["n_actions"], hidden=int(ck["train_config"]["hidden"]))
    agent.policy_net.load_state_dict(ck["policy_net"])
    agent.policy_net.eval()
    info = {"run_dir": str(run_dir), "best_file": best["file"], "sha256": sha256_file(best_pt), "selected_episode": ck["episode"],
            "val_metric": ck["val_metric"], "val_score": float(ck["val_score"]), "smoke_training_run": bool(ck["train_config"].get("smoke")),
            "obs_version": schema["obs_version"], "detector_range_m": schema["detector_range_m"]}
    info["policy_sha256"] = policy_weights_sha256(agent)
    return agent, info


_CANDIDATE_FILE = re.compile(r"^ckpt_ep(\d{4})\.pt$")


def candidate_checkpoints(run_dir: Path) -> List[Tuple[int, Path]]:
    """Periodic checkpoints ``ckpt_epNNNN.pt`` of a finished training run as ``[(episode, path)]`` sorted by episode.

    Only file *names* are read.  The ``ckpt_best_*`` copies (same episodes) and ``last.pt`` are not separate candidates."""
    run_dir = Path(run_dir)
    out = []
    for p in sorted(run_dir.iterdir()):
        m = _CANDIDATE_FILE.match(p.name)
        if m and p.is_file():
            out.append((int(m.group(1)), p))
    return out


def load_candidate_checkpoint(run_dir: Path, filename: str) -> Tuple[MaskedDoubleDQN, Dict[str, Any]]:
    """Load one *periodic* checkpoint of a finished training run for checkpoint selection (read-only).

    Same refusals as ``load_validation_selected_checkpoint`` (legacy 5-feature models, wrong feature count, smoke runs), and the
    file must be a plain ``ckpt_epNNNN.pt`` directly inside ``run_dir`` (no paths, no other directories)."""
    run_dir = Path(run_dir)
    if Path(filename).name != filename or not _CANDIDATE_FILE.match(filename):
        raise ProtocolError(f"{filename!r} is not a periodic checkpoint name (ckpt_epNNNN.pt)")
    path = run_dir / filename
    if not path.is_file() or not (run_dir / "config.json").is_file():
        raise ProtocolError(f"{path} (or the run's config.json) is missing – candidates come from runs finished by train_dqn.py")
    ck = torch.load(str(path), map_location="cpu", weights_only=False)
    schema = _schema_or_refuse(ck, path)
    if ck["train_config"].get("smoke"):
        raise ProtocolError("a checkpoint from a --smoke training run cannot take part in checkpoint selection")
    m = _CANDIDATE_FILE.match(filename)
    if int(ck["episode"]) != int(m.group(1)):
        raise ProtocolError(f"{filename} claims episode {ck['episode']} (file name says {int(m.group(1))})")
    agent = MaskedDoubleDQN(ck["state_size"], ck["n_actions"], hidden=int(ck["train_config"]["hidden"]))
    agent.policy_net.load_state_dict(ck["policy_net"])
    agent.policy_net.eval()
    info = {"run_dir": str(run_dir), "file": filename, "sha256": sha256_file(path), "selected_episode": int(ck["episode"]),
            "val_metric": ck.get("val_metric"), "val_score": ck.get("val_score"), "smoke_training_run": False,
            "obs_version": schema["obs_version"], "detector_range_m": schema["detector_range_m"]}
    info["policy_sha256"] = policy_weights_sha256(agent)
    return agent, info


# ------------------------------------------------------------------ ledger: one reported evaluation per selected model
def policy_weights_sha256(agent: Any) -> str:
    """SHA-256 of the policy-network weights (names, dtypes, shapes and values in key order): identical for two checkpoint
    files that hold the same model, whatever else the files contain."""
    h = hashlib.sha256()
    for name, t in sorted(agent.policy_net.state_dict().items()):
        t = t.detach().cpu().contiguous()
        h.update(f"{name}|{t.dtype}|{tuple(t.shape)}|".encode())
        h.update(t.numpy().tobytes())
    return h.hexdigest()


def read_ledger(path: Path) -> List[Dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []
    out = []
    for n, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ProtocolError(f"ledger {path} is corrupt at line {n} ({exc}); repair it by hand before any further final run") from exc
    return out


def append_ledger(path: Path, entry: Mapping[str, Any]) -> None:
    path = Path(path)
    with open(path, "a") as f:
        f.write(json.dumps(dict(entry), sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())


@contextlib.contextmanager
def ledger_lock(path: Path):
    """Exclusive, non-blocking lock beside the ledger (``<ledger>.lock``) for the check-and-record sequence of a run.
    A second run holding the lock is refused at once; the lock is released by the OS if the process dies."""
    lock_path = Path(str(path) + ".lock")
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ProtocolError(f"another evaluation is recording in {path} right now (lock {lock_path}); "
                                f"wait for it to finish – concurrent final runs are refused") from exc
        yield
    finally:
        os.close(fd)                                           # closing the descriptor releases the lock


def _prior_finals(ledger: Sequence[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    """Final-mode ledger entries of earlier attempts: completed runs **and** runs that started but never completed
    (a crashed or killed final run still counts – its partial results may have been seen). Entries written before the
    status field existed are completed runs."""
    return [e for e in ledger if e.get("mode") == "final" and e.get("status", "completed") in ("started", "completed")]


def assert_final_not_repeated(ledger: Sequence[Mapping[str, Any]], checkpoint_sha: str, allow_repeat: bool,
                              policy_sha: Optional[str] = None) -> None:
    """A selected model gets one *final* evaluation; re-running it (to tune, re-select, or cherry-pick) needs an explicit flag
    and is recorded as a repeat in the ledger. The model is matched by its file hash **or** its policy-weight hash, and an
    attempt that started but never completed counts as a previous evaluation."""
    prior = [e for e in _prior_finals(ledger)
             if e.get("checkpoint_sha256") == checkpoint_sha or (policy_sha is not None and e.get("policy_sha256") == policy_sha)]
    if prior and not allow_repeat:
        what = "started (and did not complete)" if all(e.get("status") == "started" for e in prior) else "already has"
        raise ProtocolError(f"checkpoint {checkpoint_sha[:12]} {what} a final evaluation ({prior[0].get('run_id')}); "
                            f"repeating it is refused unless --allow-repeat-final is given (and is then recorded)")


def assert_final_seeds_unused(ledger: Sequence[Mapping[str, Any]], seeds: Sequence[int]) -> None:
    """Final seeds are used once: a final run may not use any seed of a range already recorded in the ledger (completed or
    merely started), whichever checkpoint it evaluates."""
    lo, hi = min(seeds), max(seeds)
    used = [e for e in _prior_finals(ledger) if isinstance(e.get("seeds"), (list, tuple)) and len(e["seeds"]) == 2]
    clash = [e for e in used if not (hi < int(e["seeds"][0]) or lo > int(e["seeds"][1]))]
    if clash:
        top = max(int(e["seeds"][1]) for e in used)
        names = ", ".join(f"{e.get('run_id')} ({int(e['seeds'][0]):,}-{int(e['seeds'][1]):,})" for e in clash)
        raise ProtocolError(f"final seeds {lo:,}-{hi:,} overlap seeds already used by {names}; results on them have been seen. "
                            f"Choose unused final seeds, e.g. --seed-base {top} (first seed {top + 1:,})")
