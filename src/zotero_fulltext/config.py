"""Configuration handling for zotero-fulltext."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from .errors import ConfigurationError


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer, got {raw!r}.") from exc


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


@dataclass
class Settings:
    """Runtime settings loaded from the environment."""

    api_base_url: str
    library_type: str
    library_id: str
    api_key: str | None
    cache_dir: Path
    index_refresh_min_interval_sec: int
    paragraph_cache_ttl_sec: int
    paragraph_cache_size: int
    default_search_limit: int
    default_fulltext_limit: int
    default_fulltext_context: int
    startup_sync: bool

    @classmethod
    def from_env(cls) -> "Settings":
        """Create settings from environment variables."""
        library_type = os.getenv("ZOTERO_LIBRARY_TYPE", "user").strip().lower() or "user"
        if library_type not in {"user", "group"}:
            raise ConfigurationError(
                "ZOTERO_LIBRARY_TYPE must be 'user' or 'group'."
            )

        library_id = (
            os.getenv("ZOTERO_LIBRARY_ID")
            or os.getenv("ZOTERO_USER_ID")
            or ("0" if library_type == "user" else "")
        ).strip()
        if not library_id:
            raise ConfigurationError(
                "ZOTERO_LIBRARY_ID is required for group libraries."
            )

        cache_dir = Path(
            os.getenv("ZOTERO_CACHE_DIR", "~/.cache/zotero-fulltext")
        ).expanduser()

        return cls(
            api_base_url=os.getenv("ZOTERO_API_BASE_URL", "http://127.0.0.1:23119/api").rstrip("/"),
            library_type=library_type,
            library_id=library_id,
            api_key=os.getenv("ZOTERO_API_KEY"),
            cache_dir=cache_dir,
            index_refresh_min_interval_sec=_env_int(
                "ZOTERO_INDEX_REFRESH_MIN_INTERVAL_SEC", 15
            ),
            paragraph_cache_ttl_sec=_env_int("ZOTERO_PARAGRAPH_CACHE_TTL_SEC", 7200),
            paragraph_cache_size=_env_int("ZOTERO_PARAGRAPH_CACHE_SIZE", 128),
            default_search_limit=_env_int("ZOTERO_DEFAULT_SEARCH_LIMIT", 10),
            default_fulltext_limit=_env_int("ZOTERO_DEFAULT_FULLTEXT_LIMIT", 80),
            default_fulltext_context=_env_int("ZOTERO_DEFAULT_FULLTEXT_CONTEXT", 1),
            startup_sync=_env_bool("ZOTERO_STARTUP_SYNC", True),
        )

    @property
    def metadata_path(self) -> Path:
        """Location of the persistent metadata index."""
        return self.cache_dir / "metadata-index.json"

    @property
    def library_prefix(self) -> str:
        """Prefix used for library API calls."""
        return f"{self.library_type}s/{self.library_id}"
