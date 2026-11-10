"""Application configuration loader reading from environment variables and .env file."""
from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path

def _load_env_file(filepath: Path) -> None:
    """Lightweight zero-dependency .env file parser."""
    if not filepath.exists():
        return
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip("'\"")
                if key not in os.environ:
                    os.environ[key] = val
    except Exception:
        pass

# Automatically load .env if present
_env_path = Path(__file__).resolve().parent / ".env"
_load_env_file(_env_path)

@dataclass(frozen=True)
class Settings:
    BALE_BOT_TOKEN: str = os.getenv("BALE_BOT_TOKEN", "YOUR_BALE_BOT_TOKEN_HERE")
    BASE_URL: str = os.getenv("BALE_BASE_URL", "https://tapi.bale.ai")
    ADMIN_USER_ID: int = int(os.getenv("ADMIN_USER_ID", "1695871927"))
    DB_PATH: str = os.getenv("DB_PATH", "data/monitor.db")
    SCHEDULER_INTERVAL_SECS: int = int(os.getenv("SCHEDULER_INTERVAL_SECS", "30"))
    WORKERS_COUNT: int = int(os.getenv("WORKERS_COUNT", "8"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

settings = Settings()
