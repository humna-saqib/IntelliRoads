"""
IntelliRoads – 4-Action DQN Training Entry Point.

Trains the 4-action DQNAgent (app.agent.dqn_agent) directly using
SUMOEnvironment episodes (app.environment.sumo_environment), matching
the live controller (dqn_controller.py, main.py).

Usage:
    python train_dqn.py [--epochs 50] [--steps-per-epoch 20] [--batch-size 32]
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sqlite3
import sys
import time
from typing import List

# Ensure backend directory is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.agent.dqn_agent import DEFAULT_MODEL_PATH, DQNAgent
from app.core.database import DB_PATH
from app.core.dqn_config import load_dqn_config
from app.environment.sumo_environment import SUMOEnvironment
from app.services.traci_session import SUMO_AVAILABLE, TraCISession
from app.utils.logger import get_logger

if SUMO_AVAILABLE:
    import traci

logger = get_logger(__name__)


def get_real_throughput(session: TraCISession) -> int:
    """Return actual departed vehicle count this tick via TraCI (1 in mock mode fallback)."""
    if SUMO_AVAILABLE and not session.mock_mode:
        try:
            return int(traci.simulation.getDepartedNumber())
        except Exception:
            pass
    return 1


def _ensure_training_stats_table(db_path: Path) -> None:
    """Ensure dqn_training_stats table exists in SQLite database."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dqn_training_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                epoch INTEGER NOT NULL,
                avg_loss REAL NOT NULL,
                avg_q_value REAL NOT NULL,
                avg_reward REAL NOT NULL,
                epsilon REAL NOT NULL,
                buffer_size INTEGER NOT NULL,
                timestamp REAL NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_dqn_training_stats_epoch ON dqn_training_stats(epoch)"
        )
        conn.commit()
    finally:
        conn.close()


def _persist_stats(db_path: Path, epoch_stats: List[dict], buffer_size: int) -> None:
    """Write epoch statistics to SQLite database."""
    _ensure_training_stats_table(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executemany(
            "INSERT INTO dqn_training_stats "
            "(epoch, avg_loss, avg_q_value, avg_reward, epsilon, buffer_size, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    s["epoch"],
                    s["avg_loss"],
                    s["avg_q_value"],
                    s["avg_reward"],
                    s["epsilon"],
                    buffer_size,
                    s["timestamp"],
                )
                for s in epoch_stats
            ],
        )
        conn.commit()
    finally:
        conn.close()


def resolve_sumo_config_path() -> Path:
    """Locate intelliroads.sumocfg configuration file."""
    cwd = Path.cwd()
    candidates = [
        cwd / "sumo" / "config" / "intelliroads.sumocfg",
        cwd / "backend" / "sumo" / "config" / "intelliroads.sumocfg",
        Path(__file__).resolve().parent / "sumo" / "config" / "intelliroads.sumocfg",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


import csv
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

_BASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = _BASE_DIR / "training_results"
CHECKPOINTS_DIR = _BASE_DIR / "final_dqn_model"
GRAPHS_DIR = _BASE_DIR / "training_graphs"


def _make_output_dirs() -> None:
    for d in (RESULTS_DIR, CHECKPOINTS_DIR, GRAPHS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _generate_reward_plot(episodes: List[int], rewards: List[float], out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(episodes, rewards, color="#4a90d9", alpha=0.45, linewidth=1.0, label="Episode Reward (raw)")
    window = min(10, len(rewards))
    if window > 1:
        smoothed = [
            sum(rewards[max(0, i - window + 1):i + 1]) / min(window, i + 1)
            for i in range(len(rewards))
        ]
        ax.plot(episodes, smoothed, color="#e05c2d", linewidth=2.0, label=f"Rolling Mean (w={window})")
    ax.set_title("IntelliRoads DQN – Reward per Episode", fontsize=14)
    ax.set_xlabel("Episode / Epoch", fontsize=11)
    ax.set_ylabel("Avg Reward", fontsize=11)
    ax.xaxis.set_major_locator(ticker.MultipleLocator(max(10, len(episodes) // 10)))
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=10)
    plt.tight_layout()
    fig.savefig(str(out_path), dpi=150)
    plt.close(fig)


def main() -> None:
    config = load_dqn_config()

    parser = argparse.ArgumentParser(description="Standardized 4-Action DQN Training via SUMOEnvironment.")
    parser.add_argument("--epochs", type=int, default=1000, help="Number of training epochs/episodes")
    parser.add_argument("--steps-per-epoch", type=int, default=25, help="Steps per epoch/episode")
    parser.add_argument("--batch-size", type=int, default=config.batch_size_online, help="Minibatch SGD training size")
    parser.add_argument("--model-path", type=str, default=str(DEFAULT_MODEL_PATH), help="Output PyTorch checkpoint path")
    parser.add_argument("--lr", type=float, default=None, help="Learning rate override")
    parser.add_argument("--gamma", type=float, default=None, help="Gamma (discount factor) override")
    parser.add_argument("--hidden-size", type=int, default=None, help="Hidden layers dimension override")
    parser.add_argument("--target-update", type=int, default=5, help="Target update epoch frequency")
    parser.add_argument("--epsilon-start", type=float, default=config.epsilon_start, help="Starting epsilon")
    parser.add_argument("--epsilon-end", type=float, default=config.epsilon_end, help="Ending epsilon")
    parser.add_argument("--epsilon-decay", type=int, default=None, help="Epsilon decay duration in epochs (defaults to 25%% of total epochs)")
    parser.add_argument("--checkpoint-every", type=int, default=50, help="Save periodic checkpoint every N epochs")
    parser.add_argument("--resume", type=str, default=None, help="Path to checkpoint to resume from")

    args = parser.parse_args()
    _make_output_dirs()

    csv_path = RESULTS_DIR / "episode_log.csv"
    plot_path = GRAPHS_DIR / "reward_curve.png"

    # Initialize CSV header if file does not exist
    if not csv_path.exists():
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "episode", "avg_reward", "avg_loss", "avg_q_value",
                "epsilon", "buffer_size", "timestamp",
            ])

    # 1. Resolve SUMO config path & start TraCI session
    config_path = resolve_sumo_config_path()
    logger.info(f"Using SUMO config path: {config_path}")

    session = TraCISession(config_path=config_path, step_length=1.0)
    try:
        session.start()
    except Exception as exc:
        logger.warning(f"Could not start live SUMO process: {exc}. Operating in mock/simulation fallback mode.")

    env = SUMOEnvironment(session=session)
    agent = DQNAgent(
        state_size=5,
        action_size=4,
        gamma=args.gamma,
        learning_rate=args.lr,
        hidden_size=args.hidden_size,
        batch_size=args.batch_size,
    )

    start_epoch = 1
    if args.resume:
        resume_path = Path(args.resume)
        if resume_path.exists():
            agent.load(resume_path)
            import re
            match = re.search(r"episode_(\d+)", resume_path.name)
            if match:
                start_epoch = int(match.group(1)) + 1
            else:
                start_epoch = agent.train_step_count // args.steps_per_epoch + 1
            logger.info(f"Resuming training from epoch {start_epoch}")

    logger.info(
        f"Starting 4-Action DQN Training: epochs={args.epochs}, steps_per_epoch={args.steps_per_epoch}, "
        f"batch_size={args.batch_size}, target_update_freq={args.target_update}, checkpoint_every={args.checkpoint_every}"
    )

    target_update_freq = args.target_update
    epsilon_start = args.epsilon_start
    epsilon_end = args.epsilon_end
    epsilon_decay = args.epsilon_decay if args.epsilon_decay is not None else max(1, int(args.epochs * 0.25))

    epoch_stats: List[dict] = []
    all_episodes: List[int] = []
    all_rewards: List[float] = []

    try:
        for epoch in range(start_epoch, args.epochs + 1):
            # Compute epsilon schedule
            epsilon = max(
                epsilon_end,
                epsilon_start - (epsilon_start - epsilon_end) * (epoch / max(epsilon_decay, 1)),
            )

            losses: List[float] = []
            q_values: List[float] = []
            rewards: List[float] = []

            for _ in range(args.steps_per_epoch):
                if not session.is_connected():
                    session.start()
                    env.reset()

                session.step()
                throughput = get_real_throughput(session)

                for junction_id in env.junction_ids:
                    # 1. Read current state
                    state = env.get_state(junction_id=junction_id)

                    # 2. Select action via Epsilon-Greedy (0..3)
                    action = agent.select_action(state=state, epsilon=epsilon)

                    # 3. Step environment
                    next_state, reward, done, info = env.step(
                        action=action,
                        junction_id=junction_id,
                        throughput=throughput,
                    )

                    # 4. Store transition in agent memory
                    agent.store_transition(
                        state=state,
                        action=action,
                        reward=reward,
                        next_state=next_state,
                        done=done,
                    )
                    rewards.append(reward)

                    # 5. Train network on minibatch if sufficient buffer
                    train_res = agent.train_step(batch_size=args.batch_size)
                    if train_res is not None:
                        loss, mean_q = train_res
                        losses.append(loss)
                        q_values.append(mean_q)

                    if done:
                        logger.info("Simulation done or connection lost. Restarting TraCI session...")
                        session.close()
                        session.start()
                        env.reset()

            # Sync target network periodically
            if epoch % target_update_freq == 0:
                agent.update_target_network()

            stats = {
                "epoch": epoch,
                "avg_loss": round(sum(losses) / len(losses) if losses else 0.0, 5),
                "avg_q_value": round(sum(q_values) / len(q_values) if q_values else 0.0, 5),
                "avg_reward": round(sum(rewards) / len(rewards) if rewards else 0.0, 5),
                "epsilon": round(epsilon, 4),
                "timestamp": round(time.time(), 3),
            }
            epoch_stats.append(stats)
            all_episodes.append(epoch)
            all_rewards.append(stats["avg_reward"])

            # Append to CSV log
            with open(csv_path, "a", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    epoch, stats["avg_reward"], stats["avg_loss"],
                    stats["avg_q_value"], stats["epsilon"], len(agent.memory), stats["timestamp"],
                ])

            logger.info(
                f"Epoch {epoch:>4}/{args.epochs} | Loss: {stats['avg_loss']:.4f} | "
                f"Avg Q: {stats['avg_q_value']:.4f} | Avg Reward: {stats['avg_reward']:+.4f} | "
                f"Epsilon: {stats['epsilon']:.3f} | Buffer: {len(agent.memory)}"
            )

            # Periodic checkpointing to final_dqn_model/
            if epoch % args.checkpoint_every == 0:
                ckpt_path = CHECKPOINTS_DIR / f"dqn_episode_{epoch:04d}.pt"
                agent.save(ckpt_path)
                logger.info(f"Checkpoint saved -> {ckpt_path}")
                _generate_reward_plot(all_episodes, all_rewards, plot_path)

    except Exception as e:
        import traceback
        crash_log_path = _BASE_DIR / "crash_log.txt"
        with open(crash_log_path, "w") as f:
            f.write(traceback.format_exc())
        logger.error(f"Training crashed: {e}. Traceback saved to {crash_log_path}")
        raise
    finally:
        session.close()

    # 2. Persist statistics & Save 4-action model checkpoint
    _persist_stats(DB_PATH, epoch_stats, buffer_size=len(agent.memory))

    model_path = Path(args.model_path)
    agent.save(model_path)
    final_ckpt = CHECKPOINTS_DIR / "dqn_episode_final.pt"
    agent.save(final_ckpt)
    _generate_reward_plot(all_episodes, all_rewards, plot_path)

    print(f"\n==================================================")
    print(f"4-Action DQN Training Completed Successfully!")
    print(f"Model saved to: {model_path}")
    print(f"Final checkpoint saved to: {final_ckpt}")
    print(f"Action Space Size: {agent.action_size} (Compatible with main.py & dqn_controller.py)")
    if epoch_stats:
        first, last = epoch_stats[0], epoch_stats[-1]
        print(f"Loss trend:        {first['avg_loss']:.4f} -> {last['avg_loss']:.4f}")
        print(f"Avg Q-value trend: {first['avg_q_value']:.4f} -> {last['avg_q_value']:.4f}")
        print(f"Avg Reward trend:  {first['avg_reward']:.4f} -> {last['avg_reward']:.4f}")
    print(f"==================================================\n")


if __name__ == "__main__":
    main()

