"""Custom exceptions for zotero-fulltext."""


class ZoteroFulltextError(Exception):
    """Base exception for server errors."""

    code = "ZOTERO_FULLTEXT_ERROR"


class ConfigurationError(ZoteroFulltextError):
    """Invalid local configuration."""

    code = "CONFIGURATION_ERROR"


class ZoteroClientError(ZoteroFulltextError):
    """The Zotero API returned an unexpected response."""

    code = "ZOTERO_CLIENT_ERROR"


class ZoteroUnavailableError(ZoteroClientError):
    """The local Zotero API could not be reached."""

    code = "ZOTERO_UNAVAILABLE"


class ZoteroNotFoundError(ZoteroClientError):
    """The requested Zotero object does not exist."""

    code = "ZOTERO_NOT_FOUND"


class NoFulltextError(ZoteroClientError):
    """The attachment exists but Zotero has no indexed fulltext for it."""

    code = "NO_FULLTEXT_INDEX"
