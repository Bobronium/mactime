from __future__ import annotations

import json
from abc import ABC
from collections.abc import Callable
from collections.abc import Iterable
from datetime import datetime
from typing import cast

from mactime._cli_interface import CLI
from mactime._cli_interface import Command
from mactime._cli_interface import no_default
from mactime.constants import ATTR_NAME_ARG_CHOICES
from mactime.constants import EPOCH
from mactime.constants import SHORTHAND_TO_NAME
from mactime.constants import NAME_TO_ATTR_MAP
from mactime.constants import TIME_ALIASES
from mactime.core import TimeAttrs
from mactime.constants import WRITABLE_NAMES
from mactime.errors import ArgumentsError
from mactime._cli_interface import arg
from mactime.core import format_options
from mactime.core import resolve_paths
from mactime.core import get_last_opened_dates
from mactime.core import get_timespec_attrs
from mactime.logger import logger
from mactime.core import set_path_times


from dataclasses import dataclass, field

from mactime.constants import OPENED_NAME
from mactime.constants import BACKED_UP_NAME
from mactime.constants import CHANGED_NAME
from mactime.utils import get_finder_view
from mactime.utils import get_yaml_view


DATE_LAST_OPENED_IS_READ_ONlY = (
    "Date Last Opened is not a file attribute. "
    "It's stored in Spotlight index. There's no discovered a way to modify it."
)


GET_FORMATTERS: dict[str, Callable[[dict[str, datetime]], str]] = {
    "finder": get_finder_view,
    "json": lambda v: json.dumps(v, ensure_ascii=False, default=datetime.isoformat),
    "yaml": get_yaml_view,
    "json-pretty": lambda d: json.dumps(
        d, default=datetime.isoformat, ensure_ascii=False, indent=2
    ),
}


@dataclass
class _GlobalArgs(Command, ABC):
    no_follow: bool = arg(
        "-n",
        default=False,
        help="Don't follow symlinks at the last component of the path. Output/modify attributes of symlink itself.",
    )


@dataclass
class _RecursiveArgs(_GlobalArgs, ABC):
    recursive: bool = arg(
        "-r",
        default=False,
        help="Recursively process files in subdirectories.",
    )
    include_root: bool = arg(
        "-i",
        default=False,
        help="Always process the root directories provided as arguments (only with -r). Root directories are excluded by default.",
    )
    files_only: bool = arg(
        "-f",
        default=False,
        help="Only process files, skip all non-root directories when recursing (only with -r). Nested directories are included by default.",
    )

    def __post_init__(self):
        super().__post_init__()
        if not self.recursive:
            if self.include_root:
                raise ArgumentsError(
                    "--include-root can only be used with -r/--recursive"
                )
            if self.files_only:
                raise ArgumentsError(
                    "--files-only can only be used with -r/--recursive"
                )
        else:
            if (
                super().no_follow
            ):  # PyCharm only understands this construction for some reason
                raise ArgumentsError("--no-follow cannot be used with -r/--recursive")


@dataclass
class GetCommand(_RecursiveArgs):
    """
    Get file attributes

    Examples:
      # Show all attributes
      mactime get file.txt

      # Show attributes for multiple files
      mactime get *.txt *.md

      # Show only modification time
      mactime get file.txt -N modified

      # Show specific attribute using shorthand
      mactime get file.txt -N m
    """

    file: list[str] = arg(
        nargs="+",
        field_default_factory=no_default("file"),
        help="File or directory to inspect",
    )
    name: str | None = arg(
        "-N",
        choices=ATTR_NAME_ARG_CHOICES,
        default=None,
        help="Name of the attribute to get. Only print it to stdout. Takes precedence over --format.",
    )
    format: str = arg(
        "-F",
        choices=GET_FORMATTERS,
        default="finder",
        help="Output format",
    )
    order_by: str = arg(
        "-O",
        choices=ATTR_NAME_ARG_CHOICES,
        default=None,
        help="Order by one of the attributes. Default order is descending by Date Added. Use -R/--reverse to change the order.",
    )
    reversed: bool = arg(
        "-R",
        default=False,
        help="Reverse output order.",
    )
    skip_opened: bool = arg(
        "-S",
        default=False,
        help="Skip reading Date Last Opened. Use if you don't need it and want to get a significant performance improvement.",
    )

    def __post_init__(self):
        super().__post_init__()
        if self.reversed and not self.order_by:
            raise ArgumentsError("Reversed can only be used with --order-by option.")

        name = self.name = SHORTHAND_TO_NAME.get(self.name, self.name)
        if name and (self.recursive or self.order_by):
            raise ArgumentsError(
                "--name cannot be used with --recursive or --order-by."
            )
        elif name == OPENED_NAME and self.skip_opened:
            raise ArgumentsError("--name opened used with --skip-opened is ambiguous.")

    def __call__(
        self,
    ) -> (
        dict[str, TimeAttrs] | dict[str, dict[str, datetime]]
    ):  # merely for autocomplete
        # This is ugly due to the last minute changes.
        # I'm willing to call it good enough and stop.
        if self.name is not None:
            name = self.name
            if name == OPENED_NAME:
                attrs = get_last_opened_dates(self.file)
            else:
                attrs = {
                    file: get_timespec_attrs(file, no_follow=self.no_follow)[name]
                    for file in self.file
                }

            if not self.is_cli:
                return {path: {name: value} for path, value in attrs.items()}
            else:
                for attr in attrs.values():
                    print(attr)

            return cast(dict[str, TimeAttrs], {})

        paths = {}
        files = list(
            resolve_paths(
                self.file,
                self.recursive,
                self.include_root,
                self.files_only,
            )
        )
        if self.skip_opened:
            opened = dict.fromkeys(files, EPOCH)
        else:
            opened = get_last_opened_dates(files)

        for file in files:
            paths[str(file)] = get_timespec_attrs(file, no_follow=self.no_follow)
            paths[str(file)][OPENED_NAME] = opened[file]

        if not self.is_cli:
            return paths

        if self.order_by is not None:
            order_by = SHORTHAND_TO_NAME.get(self.order_by, self.order_by)
            paths = dict(
                sorted(
                    paths.items(),
                    key=lambda x: x[1][order_by],
                    reverse=not self.reversed,
                )
            )

        formatter = GET_FORMATTERS[self.format]
        print(formatter(paths))

        return paths


@dataclass
class SetCommand(_RecursiveArgs):
    """
    Set file attributes

    Values for attributes can be either:
        - date in ISO 8601 format, e.g. 2024-02-21T10:00:00
        - another attribute as source (full name or a shorthand)
        - one of special values:
            - now
            - yesterday
            - epoch

    Examples:
      # Set modification time
      mactime set file.txt -m "2024-02-21T10:00:00"

      # Set created time to match modified time
      mactime set file.txt -c m

      # Set added time to now
      mactime set file.txt -d now

      # Set multiple attributes at once
      mactime set file.txt -m "2024-02-21T10:00" -c "2024-02-20T15:30"

      # Process all files in directory recursively
      mactime set ./dir -r -m "2024-02-21T10:00:00"
    """

    file: list[str] = arg(
        nargs="+",
        field_default_factory=no_default("file"),
        help="File or directory to modify",
    )
    to_set: dict[str, datetime] = field(default_factory=dict)
    from_another_attributes: dict[str, str] = field(default_factory=dict)
    from_opened: list[str] = field(default_factory=list)

    modified: datetime | str | None = arg(
        "-m",
        default=None,
        help="Allowed values described above.",
    )
    created: datetime | str | None = arg(
        "-c",
        default=None,
        help="Allowed values described above.",
    )
    accessed: datetime | str | None = arg(
        "-a",
        default=None,
        help="Allowed values described above.",
    )
    changed: datetime | str | None = arg(
        "-C",
        default=None,
        help="Allowed values described above.\n"
        "This attribute is updated to current system time whenever some attributes are changed.\n"
        "It's impossible to set an arbitrary value to this attribute.",
    )
    backed_up: datetime | str | None = arg(
        "-b",
        default=None,
        help="Allowed values described above. "
        "For some reason this attribute is not writable. `setettrlist` just ignores it.",
    )
    added: datetime | str | None = arg(
        "-d",
        default=None,
        help="Either date in ISO 8601 format or another attribute as source.",
    )
    opened: datetime | str | None = arg(
        "-o",
        default=None,
        help="Using this argument currently will result in error since there's no way to even attempt to change it.",
    )

    def __post_init__(self):
        super().__post_init__()

        if not any((self.to_set, self.from_another_attributes, self.from_opened)):
            self._prepare_args()

        if OPENED_NAME in self.to_set:
            raise ArgumentsError(DATE_LAST_OPENED_IS_READ_ONlY)
        if CHANGED_NAME in self.to_set or CHANGED_NAME in self.from_another_attributes:
            logger.warning(
                f"'{CHANGED_NAME}' argument will be set to current time, not '%s'",
                self.to_set.get(
                    CHANGED_NAME, self.from_another_attributes.get(CHANGED_NAME)
                ),
            )
        if (
            BACKED_UP_NAME in self.to_set
            or BACKED_UP_NAME in self.from_another_attributes
        ):
            logger.warning(f"'{BACKED_UP_NAME}' argument will be ignored")

    def _prepare_args(self):
        from_time_aliases = {}
        for name in NAME_TO_ATTR_MAP:
            if (value := getattr(self, name)) is None:
                continue

            if isinstance(value, datetime):
                self.to_set[name] = value
                continue
            elif (func := TIME_ALIASES.get(value)) is not None:
                # in case we have same time aliases for multiple attrs
                # we want to compute them only once
                if value in from_time_aliases:
                    self.to_set[name] = from_time_aliases[value]
                else:
                    self.to_set[name] = from_time_aliases[value] = func()

            elif value in NAME_TO_ATTR_MAP or value in SHORTHAND_TO_NAME:
                value = SHORTHAND_TO_NAME.get(value, value)
                if value == OPENED_NAME:
                    self.from_opened.append(name)
                else:
                    self.from_another_attributes[name] = SHORTHAND_TO_NAME.get(
                        value, value
                    )
            else:
                try:
                    self.to_set[name] = datetime.fromisoformat(value)
                except ValueError:
                    raise ArgumentsError(
                        f"'--{name}' must be a valid ISO 8601 date or one of {format_options(TIME_ALIASES)} or "
                        f"{format_options(ATTR_NAME_ARG_CHOICES)}"
                        f" not {value!r}"
                    )

    def __call__(self):
        files_generator = resolve_paths(
            self.file,
            self.recursive,
            self.include_root,
            self.files_only,
        )

        if self.from_opened:
            files = list(files_generator)  # only resolve paths if actually necessary
            opened = get_last_opened_dates(files)

            def get_opened_attrs(path: str) -> dict[str, datetime]:
                return dict.fromkeys(self.from_opened, opened[path])

        else:
            files = files_generator

            def get_opened_attrs(path: str) -> dict[str, datetime]:
                return {}

        for file in files:
            set_path_times(
                file,
                {**self.to_set, **get_opened_attrs(file)},
                self.from_another_attributes,
                no_follow=self.no_follow,
            )


@dataclass
class MatchCommand(_RecursiveArgs):
    """
    Transfer attributes from source file to target files

    Examples:
      # Transfer specific attributes
      mactime match source.txt target.txt -mc

      # Transfer all attributes
      mactime match source.txt target.txt --all

      # Transfer to multiple files
      mactime match source.txt target1.txt target2.txt -m

      # Transfer recursively to all files in directory
      mactime match source.txt ./dir -r --all
    """

    source: str = arg(
        help="Source path to copy attributes from",
        field_default_factory=no_default("source"),
    )
    target: list[str] = arg(
        nargs="+",
        help="Target path(s) to copy attributes to",
        field_default_factory=no_default("target"),
    )
    attrs: Iterable[str] = field(default=())
    all: bool = arg(
        "-A",
        default=False,
        help="Transfer all supported attributes",
    )
    modified: bool = arg(
        "-m",
        default=False,
        help="Transfer the modified attribute",
    )
    created: bool = arg(
        "-c",
        default=False,
        help="Transfer the created attribute",
    )
    accessed: bool = arg(
        "-a",
        default=False,
        help="Transfer the accessed attribute",
    )
    changed: bool = arg(
        "-C",
        default=False,
        help="Transfer the changed attribute",
    )
    backed_up: bool = arg(
        "-b",
        suppress=True,
        default=False,
        help="Transfer the backed_up attribute",
    )
    opened: bool = arg(
        "-o",
        suppress=True,
        default=False,
        help="Transfer the opened attribute",
    )
    added: bool = arg(
        "-d",
        suppress=True,
        default=False,
        help="Transfer the added attribute",
    )

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.attrs:  # set manually via MacTimes.match(file, target, attrs=("c", "d")
            return
        if self.all:
            self.attrs = WRITABLE_NAMES
        else:
            self.attrs = {n for n in NAME_TO_ATTR_MAP if getattr(self, n)}
            if not self.attrs:
                raise ArgumentsError(
                    "No attributes selected for match. Use --all or specify attributes"
                )

        if OPENED_NAME in self.attrs:
            raise ArgumentsError(DATE_LAST_OPENED_IS_READ_ONlY)

    def __call__(self):
        source_attrs = get_timespec_attrs(self.source)

        to_set = {}
        for name in self.attrs:
            value = source_attrs[name]
            logger.info(f"Will attempt to match '{name}={value}' from '{self.source}'")
            to_set[name] = value

        for path in resolve_paths(
            self.target,
            self.recursive,
            self.include_root,
            self.files_only,
        ):
            set_path_times(path, to_set, no_follow=self.no_follow)


class MacTime(CLI):
    """Take control over macOS files timestamps."""

    get = GetCommand
    set = SetCommand
    match = MatchCommand


def main():
    MacTime.run()
