from __future__ import annotations

import ctypes
import errno
import os
from typing import Type, ClassVar


class MacTimeError(Exception):
    """Base exception class for mactime errors."""

    exit_code: ClassVar[int] = 1


class ArgumentsError(MacTimeError, ValueError):
    exit_code = 2


class NotEnoughArgumentsError(MacTimeError, ValueError):
    exit_code = 22


class FSOperationError(MacTimeError, OSError):
    """Base class for file operation errors."""

    _registry: ClassVar[dict[int, Type[FSOperationError]]] = {}
    error_codes: ClassVar[set[int]] = set()
    error_message: ClassVar[str] = "Unknown error"
    exit_code: ClassVar[int] = 22

    def __init__(
        self,
        path: str,
        operation: str,
        errno: int,
        message: str | None = None,
    ):
        self.path = path
        self.operation = operation
        self.errno = errno
        self.message = message or self.error_message
        super().__init__(f"{operation} on {path!r}: {self.message} (errno {errno!r})")

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()
        for code in cls.error_codes:
            FSOperationError._registry[code] = cls

    @classmethod
    def check_call(cls, ret: int, path: str | os.PathLike, operation: str) -> None:
        if ret == 0:
            return

        err = ctypes.get_errno()
        specific_error = cls._registry.get(err, FSOperationError)
        raise specific_error(path, operation, err)


class PathNotFoundError(FSOperationError):
    error_codes = {errno.ENOENT}
    error_message = "Path not found"
    exit_code = 2


class FSPermissionError(FSOperationError):
    error_codes = {errno.EACCES, errno.EPERM}
    error_message = "Permission denied"
    exit_code = 13


class InvalidAttributeError(FSOperationError):
    error_codes = {errno.EINVAL}
    error_message = "Invalid attribute or operation"
    exit_code = 22


class UnsupportedOperationError(FSOperationError):
    error_codes = {errno.ENOTSUP}
    error_message = "Operation not supported"
    exit_code = 45


class FileIOError(FSOperationError):
    error_codes = {errno.EIO}
    error_message = "I/O error occurred"
    exit_code = 5
