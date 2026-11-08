"""Errors shared by interruptible NUP operations."""


class OperationCancelled(Exception):
    """Raised when a user cancels a pack or extraction operation."""
