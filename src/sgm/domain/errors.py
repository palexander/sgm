from __future__ import annotations


class SgmError(Exception):
    """Base domain error."""


class InfrastructureError(SgmError):
    """Raised when infrastructure is unavailable."""


class RepoRootError(SgmError):
    """Raised when the current directory is not a git repo root."""


class NotIndexedError(SgmError):
    """Raised when a path is missing from the graph."""


class FileNotFoundOnDiskError(SgmError):
    """Raised when a file is missing from disk."""


class SpecValidationError(SgmError):
    """Raised when a spec file is invalid."""


class EntityNotFoundError(SgmError):
    """Raised when a spec or proposal cannot be found."""

