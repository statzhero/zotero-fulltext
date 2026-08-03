"""zotero-fulltext package."""

from importlib.metadata import PackageNotFoundError, version

__all__ = ["__version__"]

try:
    __version__ = version("zotero-fulltext")
except PackageNotFoundError:  # pragma: no cover - source checkout without install
    __version__ = "0.0.0"
