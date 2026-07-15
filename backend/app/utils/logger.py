"""
IntelliRoads – Loguru-based structured logger.

Handlers:
  • Console  – colourised, INFO+
  • logs/app.log – all levels, rotation 10 MB, 7-day retention
  • logs/signals.log – signal-change events only
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

try:
    from loguru import logger as _loguru_logger
except ModuleNotFoundError:  # pragma: no cover - runtime fallback
    _loguru_logger = None

# ---------------------------------------------------------------------------
# Ensure logs directory exists
# ---------------------------------------------------------------------------
_LOG_DIR = Path("logs")
_LOG_DIR.mkdir(parents=True, exist_ok=True)

if _loguru_logger is not None:
    # Remove the default Loguru sink
    _loguru_logger.remove()

    # -----------------------------------------------------------------------
    # Console handler – colourised, INFO and above
    # -----------------------------------------------------------------------
    _loguru_logger.add(
        sys.stdout,
        level="INFO",
        colorize=True,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        enqueue=True,
    )

    # -----------------------------------------------------------------------
    # File handler – all levels, rotation & retention
    # -----------------------------------------------------------------------
    _loguru_logger.add(
        str(_LOG_DIR / "app.log"),
        level="DEBUG",
        rotation="10 MB",
        retention="7 days",
        compression="zip",
        encoding="utf-8",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
            "{name}:{function}:{line} | {message}"
        ),
        enqueue=True,
    )

    # -----------------------------------------------------------------------
    # Signal-change file handler – only records tagged with "SIGNAL"
    # -----------------------------------------------------------------------
    def _is_signal_record(record: dict) -> bool:
        """Filter: only forward records that carry the SIGNAL tag."""
        return record["extra"].get("signal") is True


    _loguru_logger.add(
        str(_LOG_DIR / "signals.log"),
        level="INFO",
        filter=_is_signal_record,
        rotation="10 MB",
        retention="7 days",
        compression="zip",
        encoding="utf-8",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | SIGNAL | "
            "junction={extra[junction_id]} | "
            "{extra[old_phase]} -> {extra[new_phase]} | "
            "duration={extra[duration]}s | reason={extra[reason]} | "
            "{message}"
        ),
        enqueue=True,
    )
else:
    class _FallbackLogger:
        def __init__(self, logger: logging.Logger) -> None:
            self._logger = logger

        def bind(self, **_: object) -> "_FallbackLogger":
            return self

        def debug(self, message: str) -> None:
            self._logger.debug(message)

        def info(self, message: str) -> None:
            self._logger.info(message)

        def warning(self, message: str) -> None:
            self._logger.warning(message)

        def error(self, message: str) -> None:
            self._logger.error(message)

        def exception(self, message: str) -> None:
            self._logger.exception(message)


    def _configure_fallback_logging() -> tuple[_FallbackLogger, logging.Logger]:
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s"
        )

        root_logger = logging.getLogger("intelliroads")
        root_logger.setLevel(logging.DEBUG)
        root_logger.handlers.clear()
        root_logger.propagate = False

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

        app_handler = logging.FileHandler(_LOG_DIR / "app.log", encoding="utf-8")
        app_handler.setLevel(logging.DEBUG)
        app_handler.setFormatter(formatter)
        root_logger.addHandler(app_handler)

        signal_logger = logging.getLogger("intelliroads.signal")
        signal_logger.setLevel(logging.INFO)
        signal_logger.handlers.clear()
        signal_logger.propagate = False
        signal_handler = logging.FileHandler(_LOG_DIR / "signals.log", encoding="utf-8")
        signal_handler.setLevel(logging.INFO)
        signal_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | SIGNAL | junction=%(junction_id)s | %(old_phase)s -> %(new_phase)s | duration=%(duration)ss | reason=%(reason)s | %(message)s"
            )
        )
        signal_logger.addHandler(signal_handler)

        return _FallbackLogger(root_logger), signal_logger


    _fallback_logger, _signal_logger = _configure_fallback_logging()


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_logger(name: str):
    """Return a Loguru logger bound with the given *name* context."""
    if _loguru_logger is not None:
        return _loguru_logger.bind(name=name)
    return _fallback_logger.bind(name=name)


def log_signal_change(
    junction_id: str,
    old_phase: str,
    new_phase: str,
    duration: float,
    reason: str,
) -> None:
    """
    Write a structured signal-change record to logs/signals.log.

    Parameters
    ----------
    junction_id : str
        The traffic-light junction identifier.
    old_phase : str
        The previous signal phase (e.g. 'RED').
    new_phase : str
        The new signal phase (e.g. 'GREEN').
    duration : float
        Planned duration of the new phase in seconds.
    reason : str
        Human-readable reason for the change (e.g. 'HIGH density detected').
    """
    if _loguru_logger is not None:
        _loguru_logger.bind(
            signal=True,
            junction_id=junction_id,
            old_phase=old_phase,
            new_phase=new_phase,
            duration=duration,
            reason=reason,
            name="signal_controller",
        ).info(
            f"Signal changed at {junction_id}: {old_phase} → {new_phase} "
            f"for {duration}s ({reason})"
        )
    else:
        _signal_logger.info(
            f"Signal changed at {junction_id}: {old_phase} -> {new_phase} for {duration}s ({reason})",
            extra={
                "junction_id": junction_id,
                "old_phase": old_phase,
                "new_phase": new_phase,
                "duration": duration,
                "reason": reason,
            },
        )


# Module-level convenience logger
logger = get_logger("intelliroads")
