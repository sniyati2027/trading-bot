"""
Logging configuration for the trading bot.

Design decisions:
- File handler  → structured JSON (machine-readable, grep-friendly)
- Console handler → human-readable with colour via rich (suppressed in --quiet mode)
- A single call to `setup_logging()` at startup wires everything up.
- Module-level loggers (`logging.getLogger(__name__)`) work automatically.
"""

import json
import logging
import logging.handlers
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Attempt to import rich for coloured console output; fall back gracefully.
try:
    from rich.console import Console
    from rich.logging import RichHandler
    _RICH_AVAILABLE = True
except ImportError:
    _RICH_AVAILABLE = False

# ---------------------------------------------------------------------------
# Log directory
# ---------------------------------------------------------------------------

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

LOG_FILE = LOG_DIR / "trading_bot.log"


# ---------------------------------------------------------------------------
# JSON formatter for file handler
# ---------------------------------------------------------------------------

class JSONFormatter(logging.Formatter):
    """
    Emits one JSON object per line — easy to parse with `jq` or ship to
    any log aggregator (Datadog, CloudWatch, etc.).
    """

    RESERVED = {"message", "asctime", "levelname", "name", "pathname",
                 "lineno", "funcName", "exc_info", "exc_text", "stack_info"}

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Attach any extra key=value pairs passed to the logger
        for key, value in record.__dict__.items():
            if key not in self.RESERVED and not key.startswith("_"):
                if key not in ("args", "created", "filename", "levelno",
                               "msecs", "msg", "name", "pathname", "process",
                               "processName", "relativeCreated", "stack_info",
                               "taskName", "thread", "threadName"):
                    log_entry[key] = value

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)


# ---------------------------------------------------------------------------
# Public setup function
# ---------------------------------------------------------------------------

def setup_logging(
    log_level: str = "INFO",
    quiet: bool = False,
    log_file: Optional[Path] = None,
) -> None:
    """
    Call once at bot startup.

    Parameters
    ----------
    log_level : str
        Root log level (DEBUG / INFO / WARNING / ERROR). Defaults to INFO.
    quiet : bool
        If True, suppress console output entirely (file logging continues).
    log_file : Path, optional
        Override default log file path.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Remove any handlers that may have been added by imported libraries
    root_logger.handlers.clear()

    # -----------------------------------------------------------------------
    # File handler — JSON, rotates at 5 MB, keeps 5 backups
    # -----------------------------------------------------------------------
    file_path = log_file or LOG_FILE
    file_handler = logging.handlers.RotatingFileHandler(
        file_path,
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(JSONFormatter())
    file_handler.setLevel(logging.DEBUG)  # Capture everything in the file
    root_logger.addHandler(file_handler)

    # -----------------------------------------------------------------------
    # Console handler
    # -----------------------------------------------------------------------
    if not quiet:
        if _RICH_AVAILABLE:
            console_handler = RichHandler(
                rich_tracebacks=True,
                show_path=False,
                markup=True,
                log_time_format="[%H:%M:%S]",
            )
        else:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(
                logging.Formatter(
                    fmt="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
                    datefmt="%H:%M:%S",
                )
            )
        console_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
        root_logger.addHandler(console_handler)

    # Silence overly-chatty third-party loggers
    for noisy in ("urllib3", "requests", "httpx", "hpack", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Convenience wrapper — use in every module as `logger = get_logger(__name__)`."""
    return logging.getLogger(name)