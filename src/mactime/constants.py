from __future__ import annotations

import os
from datetime import datetime
from datetime import timedelta
from decimal import Decimal
from typing import Final


MODIFIED_NAME: Final[str] = "modified"
CREATED_NAME: Final[str] = "created"
CHANGED_NAME: Final[str] = "changed"
ADDED_NAME: Final[str] = "added"
ACCESSED_NAME: Final[str] = "accessed"
BACKED_UP_NAME: Final[str] = "backed_up"
OPENED_NAME: Final[str] = "opened"

PathType = "str | os.PathLike"

NANOSECONDS_IN_SECOND = Decimal("1e9")


# Constants (from macOS attr/attribute headers)
# taken from https://docs.rs/libc/latest/aarch64-apple-ios/src/libc/unix/bsd/apple/mod.rs.html
ATTR_CMN_CRTIME = 0x00000200  # Finder's Date Created
ATTR_CMN_MODTIME = 0x00000400  # Finder's Date Modified & st_mtime
ATTR_CMN_CHGTIME = 0x00000800  # st_ctime (last attr modification time)
ATTR_CMN_ACCTIME = 0x00001000  # st_atime
ATTR_CMN_BKUPTIME = 0x00002000
ATTR_CMN_ADDEDTIME = 0x10000000  # Finder's Date Added
ATTR_CMN_RETURNED_ATTRS = 0x80000000
ATTR_BIT_MAP_COUNT = 5


FSOPT_NOFOLLOW = 0x1

NAME_TO_SHORTHAND = {
    MODIFIED_NAME: "m",
    CREATED_NAME: "c",
    CHANGED_NAME: "g",
    ADDED_NAME: "d",
    ACCESSED_NAME: "a",
    BACKED_UP_NAME: "b",
    OPENED_NAME: "o",
}
SHORTHAND_TO_NAME = {v: k for k, v in NAME_TO_SHORTHAND.items()}
ATTR_NAME_ARG_CHOICES = {**NAME_TO_SHORTHAND, **SHORTHAND_TO_NAME}
ATTR_TO_NAME_MAP = {
    ATTR_CMN_CRTIME: CREATED_NAME,
    ATTR_CMN_MODTIME: MODIFIED_NAME,
    ATTR_CMN_CHGTIME: CHANGED_NAME,
    ATTR_CMN_ACCTIME: ACCESSED_NAME,
    ATTR_CMN_BKUPTIME: BACKED_UP_NAME,
    ATTR_CMN_ADDEDTIME: ADDED_NAME,
}
assert sorted(ATTR_TO_NAME_MAP) == list(ATTR_TO_NAME_MAP), "Attrs must be ordered."

NAME_TO_ATTR_MAP: dict[str, int] = {
    name: attr for attr, name in ATTR_TO_NAME_MAP.items()
}
WRITABLE_NAMES = NAME_TO_ATTR_MAP.keys() - {OPENED_NAME, BACKED_UP_NAME, CHANGED_NAME}

EPOCH = datetime.fromtimestamp(0)
TIME_ALIASES = {
    "now": datetime.now,
    "yesterday": lambda: (datetime.now() - timedelta(days=1)).replace(
        microsecond=0, second=0, minute=0, hour=0
    ),
    "epoch": lambda: EPOCH,
}

FINDER_ATTRS = {
    CREATED_NAME: "Date Created",
    MODIFIED_NAME: "Date Modified",
    OPENED_NAME: "Date Last Opened",
    ADDED_NAME: "Date Added",
}
