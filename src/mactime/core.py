from __future__ import annotations

import ctypes
import operator
import subprocess

from ctypes import (
    POINTER,
    Structure,
    byref,
    c_long,
    c_uint16,
    c_uint32,
    create_string_buffer,
    sizeof,
)
from datetime import datetime
from decimal import Decimal
from functools import reduce
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

from mactime.constants import ATTR_BIT_MAP_COUNT
from mactime.constants import ATTR_CMN_RETURNED_ATTRS
from mactime.constants import ATTR_TO_NAME_MAP
from mactime.constants import EPOCH
from mactime.constants import FSOPT_NOFOLLOW
from mactime.constants import NAME_TO_ATTR_MAP
from mactime.constants import NANOSECONDS_IN_SECOND
from mactime.constants import PathType

from mactime.errors import FSOperationError
from mactime.logger import logger


if TYPE_CHECKING:
    from collections.abc import Iterable
    from typing import Any, Never, Self, Unpack


class AttrList(Structure):
    _fields_ = [
        ("bitmapcount", c_uint16),
        ("reserved", c_uint16),
        ("commonattr", c_uint32),
        ("volattr", c_uint32),
        ("dirattr", c_uint32),
        ("fileattr", c_uint32),
        ("forkattr", c_uint32),
    ]


libc = ctypes.CDLL("libc.dylib", use_errno=True)
for func in libc.setattrlist, libc.getattrlist:
    func.argtypes = [
        ctypes.c_char_p,
        POINTER(AttrList),
        ctypes.c_void_p,
        ctypes.c_size_t,
        c_uint32,
    ]
    func.restype = ctypes.c_int


class TimeSpecAttrs(TypedDict):
    created: datetime
    modified: datetime
    changed: datetime
    added: datetime
    accessed: datetime
    backed_up: datetime


class TimeAttrs(TimeSpecAttrs):
    opened: datetime


class TimeSpecArgs(TypedDict, total=False):
    created: datetime
    modified: datetime
    changed: datetime
    added: datetime
    accessed: datetime
    backed_up: datetime


class BaseStructure(Structure):
    @classmethod
    def from_python(cls, value: Any) -> Never:
        raise NotImplementedError

    def to_python(self) -> Any:
        raise NotImplementedError

    def __repr__(self) -> str:
        fields = ", ".join(
            f"{k}={getattr(self, k)!r}" for k, _ in self.__class__._fields_
        )
        return f"{self.__class__.__name__}({fields})"


class Timespec(BaseStructure):
    _fields_ = [("tv_sec", c_long), ("tv_nsec", c_long)]

    @classmethod
    def from_python(cls, value: datetime) -> Self:
        timestamp = Decimal(value.timestamp())
        sec = int(timestamp)
        nsec = int((timestamp - sec) * NANOSECONDS_IN_SECOND)
        return Timespec(tv_sec=sec, tv_nsec=nsec)

    def to_python(self) -> datetime:
        return datetime.fromtimestamp(
            self.tv_sec + float(self.tv_nsec / NANOSECONDS_IN_SECOND)
        )


class TimespecRequest(BaseStructure):
    _fields_ = [("time", Timespec)]


class BulkTimespecRequest(BaseStructure):
    _fields_ = [("times", TimespecRequest * len(ATTR_TO_NAME_MAP))]


def format_options(iterable: Iterable[str]) -> str:
    return "{" + ",".join(iterable) + "}"


def set_timespec_attrs(
    path: PathType, attr_map: dict[int, Timespec], no_follow: bool = False
) -> None:
    path = str(path)
    attr_list = AttrList()
    attr_list.bitmapcount = ATTR_BIT_MAP_COUNT
    attr_list.commonattr = 0

    req = BulkTimespecRequest()
    for i, (attr, timespec) in enumerate(sorted(attr_map.items(), key=lambda a: a[0])):
        attr_list.commonattr |= attr
        req.times[i].time = timespec

    ret = libc.setattrlist(
        path.encode("utf-8"),
        byref(attr_list),
        byref(req),
        sizeof(req),
        FSOPT_NOFOLLOW if no_follow else 0,
    )

    FSOperationError.check_call(ret, path, "calling setattrlist")

    logger.debug(
        "Successfully set attributes (bitmap: 0x%08x) for %s",
        attr_list.commonattr,
        path,
    )


def modify_macos_times(
    file: PathType, no_follow: bool = False, **kwargs: Unpack[TimeSpecArgs]
) -> None:
    """Modify macOS file date attributes for the given file."""
    attr_map = {}
    for name, value in kwargs.items():
        timespec = Timespec.from_python(value)
        attr = NAME_TO_ATTR_MAP[name]
        logger.info("Will attempt to set '%s' to '%s' on '%s'", name, value, file)
        attr_map[attr] = timespec

    if attr_map:
        set_timespec_attrs(file, attr_map, no_follow=no_follow)

    (
        logger.debug(
            "Successfully modified attributes for %s: %s",
            file,
            attr_map,
        ),
    )


def get_last_opened_dates(paths: list[PathType]) -> dict[PathType, datetime]:
    """
    Uses mdls to get the last opened dates for all files in the given paths.
    mdls outputs dates in the same order as provided arguments and stops if encounters an error.
    this function skips errors and calls itself again until all paths are exhausted.
    """
    null_marker = "(null)"
    cmd = [
        "mdls",
        "-name",
        "kMDItemLastUsedDate",
        "-nullMarker",
        null_marker,
    ]
    logger.debug("Calling `%s %s`", " ".join(cmd), f"<{len(paths)} files...>")
    cmd.extend(map(str, paths))
    result = subprocess.run(
        cmd,
        capture_output=True,
    )
    logger.debug("Done, sorry if mdls was slow.")
    output = result.stdout.decode().strip()
    if not output:  # cannot do much here
        return dict.fromkeys(paths, EPOCH)

    def get_datetime(value: str) -> datetime:
        if value == null_marker:
            return EPOCH
        return datetime.fromisoformat(value).replace(tzinfo=None)

    encountered_error = False
    opened = {}
    for i, (path, line) in enumerate(zip(paths, output.splitlines())):
        if encountered_error:
            raise RuntimeError(
                f"Unexpected output from mdls after error {encountered_error} {line}"
            )
        if not line.startswith("kMDItemLastUsedDate"):
            encountered_error = line
            if not line.strip(".").endswith(str(path)):
                raise RuntimeError(f"Unexpected output from mdls: {line} ({path})")
            logger.warning(
                "Encountered error while getting Date Last Opened for %s via mdls: %s. Defaulting to epoch.",
                path,
                line,
            )
            opened[path] = EPOCH
            opened.update(get_last_opened_dates(paths[i + 1 :]))
        else:
            opened[path] = get_datetime(line.replace("kMDItemLastUsedDate = ", ""))

    if len(opened) != len(paths):
        opened = dict.fromkeys(paths[: len(opened)], EPOCH)

    return opened


def get_timespec_attrs(path: PathType, no_follow: bool = False) -> TimeSpecAttrs:
    file_bytes = str(path).encode("utf-8")
    attr_list = AttrList()
    attr_list.bitmapcount = ATTR_BIT_MAP_COUNT
    attr_list.commonattr = (
        reduce(operator.or_, ATTR_TO_NAME_MAP) | ATTR_CMN_RETURNED_ATTRS
    )

    # Allocate a buffer sufficiently large for the expected data.
    header_size = 4 + (ATTR_BIT_MAP_COUNT * 4)
    buf_size = header_size + sizeof(Timespec) * len(ATTR_TO_NAME_MAP)
    buf = create_string_buffer(buf_size)
    ret = libc.getattrlist(
        file_bytes, byref(attr_list), buf, buf_size, FSOPT_NOFOLLOW if no_follow else 0
    )

    FSOperationError.check_call(ret, path, "calling getattrlist")

    length = int.from_bytes(buf.raw[0:4], byteorder="little")
    result: dict[str, datetime] = {}
    offset = header_size
    value_size = sizeof(Timespec)
    for const, name in ATTR_TO_NAME_MAP.items():
        if offset + value_size > length:
            raise FSOperationError(
                str(path),
                "reading data from getattrlist",
                0,
                message=f"Not enough data returned for attribute {name}",
            )
        value = ctypes.cast(ctypes.byref(buf, offset), POINTER(Timespec)).contents
        result[name] = value.to_python()
        offset += value_size

    return result


def resolve_paths(
    paths: list[str],
    recursive: bool = False,
    include_root: bool = False,
    files_only: bool = False,
):
    if not recursive:
        yield from paths
        return

    for path in paths:
        path = Path(path)
        if path.is_dir():
            if include_root:
                yield path

            for item in path.rglob("*"):
                if item.is_file() or (item.is_dir() and not files_only):
                    yield item
        else:
            yield path


def set_path_times(
    file: PathType,
    to_set: dict[str, datetime],
    from_another_attributes: dict[str, str] | None = None,
    no_follow: bool = False,
) -> None:
    if from_another_attributes:
        attrs = get_timespec_attrs(file, no_follow=no_follow)
        to_set.update(
            {name: attrs[source] for name, source in from_another_attributes.items()},
        )
    modify_macos_times(file, no_follow=no_follow, **to_set)
