"""Central configuration — pydantic-settings loaded lazily with caching (H12, H13, H14)."""

from __future__ import annotations

import functools
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_env_file() -> Path | None:
    # 1. Current working directory
    cwd_env = Path.cwd() / ".env"
    if cwd_env.is_file():
        return cwd_env
    # 2. Repo root
    repo_root = Path(__file__).resolve().parents[3] / ".env"
    if repo_root.is_file():
        return repo_root
    # 3. User config dir
    try:
        import platformdirs
        cfg_env = Path(platformdirs.user_config_dir("syssathi")) / ".env"
        if cfg_env.is_file():
            return cfg_env
    except Exception:
        pass
    return None


_env_file = _find_env_file()
if _env_file:
    load_dotenv(_env_file)


class Settings(BaseSettings):
    """SysSathi configuration loaded from environment and .env file."""

    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=_env_file,
        extra="ignore",
    )

    # LLM backend selection: "evon_remote" | "openai_compatible" | "mock"
    SYSSATHI_LLM_BACKEND: str = ""
    SYSSATHI_ENV: str = ""

    # Evon endpoint (no hard-coded private endpoints as default per H13)
    EVON_BASE_URL: str = ""
    HF_TOKEN: str = ""
    EVON_MODEL: str = ""
    EVON_KEEPALIVE: bool = False

    # openai_compatible fallback endpoint
    OPENAI_COMPAT_BASE_URL: str = ""
    OPENAI_COMPAT_API_KEY: str = ""
    OPENAI_COMPAT_MODEL: str = ""

    # Reply style: "latin" | "devanagari"
    REPLY_STYLE: str = "latin"

    # Fast path flags: ENABLE_FAST_PATH primary, FORCE_FAST_PATH alias (H12)
    ENABLE_FAST_PATH: bool = True
    FORCE_FAST_PATH: bool | None = None

    # Approval token
    SYSSATHI_APPROVAL_TOKEN: str = ""

    # Opt-in local telemetry (§8)
    ENABLE_TELEMETRY: bool = False

    # Gnani speech APIs
    GNANI_API_KEY: str = ""
    PRISMA_MODE: str = "Code-mix"
    TIMBRE_VOICE: str = "Shivani"

    # Logging directory override (H14)
    SYSSATHI_LOG_DIR: str = ""

    @field_validator("ENABLE_FAST_PATH", mode="before")
    @classmethod
    def _validate_enable_fast_path(cls, v: Any) -> bool:
        if v == "" or v is None:
            return True
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes")
        return bool(v)

    @field_validator("FORCE_FAST_PATH", mode="before")
    @classmethod
    def _validate_force_fast_path(cls, v: Any) -> bool | None:
        if v == "" or v is None:
            return None
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes")
        return bool(v)

    @field_validator("EVON_KEEPALIVE", mode="before")
    @classmethod
    def _validate_evon_keepalive(cls, v: Any) -> bool:
        if v == "" or v is None:
            return False
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes")
        return bool(v)


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached Settings instance."""
    return Settings()


def clear_settings_cache() -> None:
    """Clear cached settings (primarily for testing)."""
    get_settings.cache_clear()


def get_llm_backend() -> str:
    """Return active LLM backend name, defaulting to mock in test environment."""
    backend = os.environ.get("SYSSATHI_LLM_BACKEND")
    if not backend:
        try:
            backend = get_settings().SYSSATHI_LLM_BACKEND
        except Exception:
            pass
    if backend:
        return backend.strip()
    if (
        os.environ.get("SYSSATHI_ENV") == "test"
        or "PYTEST_CURRENT_TEST" in os.environ
    ):
        return "mock"
    return "unset"


def get_logs_dir() -> Path:
    """Return log directory respecting SYSSATHI_LOG_DIR, repo root, or platformdirs (H14)."""
    env_dir = os.environ.get("SYSSATHI_LOG_DIR")
    if not env_dir:
        try:
            env_dir = get_settings().SYSSATHI_LOG_DIR
        except Exception:
            pass
    if env_dir:
        p = Path(env_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    proj_root = Path(__file__).resolve().parents[3]
    if (proj_root / "pyproject.toml").exists():
        p = proj_root / "logs"
        p.mkdir(parents=True, exist_ok=True)
        return p

    import platformdirs
    p = Path(platformdirs.user_log_dir("syssathi"))
    p.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------------------
# Keyterms & keyword definitions
# ---------------------------------------------------------------------------

KEYTERMS_LIST: list[str] = [
    "Chrome",
    "Teams",
    "Spotify",
    "OneDrive",
    "Edge",
    "Zoom",
]

SLOWNESS_KEYWORDS: list[str] = [
    "slow",
    "hang",
    "lag",
    "laggy",
    "dheema",
    "dhima",
    "atak",
    "freeze",
    "slow chal",
]


# ---------------------------------------------------------------------------
# Dynamic module attributes for backward compatibility with existing imports
# ---------------------------------------------------------------------------

def __getattr__(name: str) -> Any:
    if name == "LLM_BACKEND":
        return get_llm_backend()
    if name == "LOGS_DIR":
        return get_logs_dir()
    if name in ("ENABLE_FAST_PATH", "FORCE_FAST_PATH"):
        env_val = os.environ.get("ENABLE_FAST_PATH") or os.environ.get("FORCE_FAST_PATH")
        if env_val is not None:
            return env_val.lower() in ("true", "1", "yes")
        s = get_settings()
        if s.FORCE_FAST_PATH is not None:
            return s.FORCE_FAST_PATH
        return s.ENABLE_FAST_PATH

    # Check os.environ first (e.g. for monkeypatched env in tests)
    env_override = os.environ.get(name)
    s = get_settings()
    if hasattr(s, name):
        if env_override is not None:
            field_val = getattr(s, name)
            if isinstance(field_val, bool):
                return env_override.lower() in ("true", "1", "yes")
            return env_override
        return getattr(s, name)

    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
