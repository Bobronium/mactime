from __future__ import annotations

import dataclasses
import logging
import sys
from abc import ABC
from abc import abstractmethod
from argparse import ArgumentParser, Namespace
from argparse import RawDescriptionHelpFormatter
from argparse import SUPPRESS
from collections.abc import Iterable
from contextlib import contextmanager
from dataclasses import Field
from dataclasses import dataclass
from dataclasses import field
from inspect import cleandoc
from typing import Any
from typing import Literal
from typing import Type, TypeVar
from mactime.errors import ArgumentsError
from mactime.errors import MacTimeError


T = TypeVar("T", bound="Command")


def no_default(name: str):
    # allows field names to have pseudo default fields
    # which allows to inherit dataclasses with defaults
    def ensure_not_called():
        raise TypeError(
            f"dataclass __init__() missing at least 1 required keyword-only argument: {name!r}"
        )

    return ensure_not_called


class HelpfulParser(ArgumentParser):
    def error(self, message: str):
        print(f"{self.prog}: error: {message}\n", file=sys.stderr)
        self.print_help(file=sys.stderr)
        sys.exit(2)


@contextmanager
def handle_cli_exception(command: "Command"):
    try:
        yield
    except Exception as e:
        if not command.is_cli or command.verbose:
            raise

        if isinstance(e, MacTimeError):
            message = str(e)
            return_code = e.exit_code
        else:
            message = f"Unexpected error {e.__class__}: {str(e)}"
            return_code = 1

        sys.stderr.write(message)
        sys.exit(return_code)


def arg(
    *flags: str,
    default: Any = dataclasses.MISSING,
    field_default: Any = dataclasses.MISSING,  # if wasn't populated from argparse.Namespace
    field_default_factory: Any = dataclasses.MISSING,
    action: str | None = None,
    nargs: str | int | Literal["?", "*", "+"] | None = None,
    choices: Iterable[str] | None = None,
    suppress: bool = False,
    help: str,
) -> Any:
    metadata = {
        "help": help if not suppress else SUPPRESS,
        "argument": list(flags) if flags else None,
    }

    if action is not None:
        metadata["action"] = action
    if nargs is not None:
        metadata["nargs"] = nargs
    if choices is not None:
        # Convert to list to fix type compatibility
        metadata["choices"] = (
            list(choices) if not isinstance(choices, list) else choices
        )

    if default is not dataclasses.MISSING:
        metadata["default"] = default

    if field_default is not dataclasses.MISSING:
        # Convert to appropriate type for assignment compatibility
        if isinstance(field_default, (str, type(None))):
            default = field_default
        else:
            default = str(field_default)

    kwargs = {}
    if sys.version_info >= (3, 10):
        kwargs["kw_only"] = True
        if (
            field_default_factory is not dataclasses.MISSING
            and field_default_factory.__name__ == no_default("...").__name__
        ):
            field_default_factory = dataclasses.MISSING

    return field(
        default=default,
        default_factory=field_default_factory,
        metadata=metadata,
        **kwargs,
    )


@dataclass
class Command(ABC):
    """Base class for all CLI commands."""

    verbose: int = arg(
        "-v",
        "--verbose",
        action="count",
        default=0,
        field_default=None,
        help="Increase output verbosity",
    )

    @property
    def is_cli(self):
        return self.verbose is not None

    def __post_init__(self) -> None:
        if self.verbose is None:
            return None

        log_levels = {
            0: logging.WARNING,
            1: logging.INFO,  # -v
            2: logging.DEBUG,  # -vv
            3: logging.DEBUG - 5,  # -vvv (could add even more detailed debugging)
        }

        # Get the requested log level, defaulting to the most verbose if count is too high
        level = log_levels.get(self.verbose, logging.DEBUG)
        if level is not None:
            logging.basicConfig(
                level=level,
                format="%(message)s"
                if self.verbose <= 1
                else "%(levelname)s [%(filename)s:%(lineno)d]: %(message)s",
            )

    @abstractmethod
    def __call__(self) -> int:
        raise NotImplementedError

    @classmethod
    def run(cls, argv: list[str] | None = None) -> int:
        parser = HelpfulParser()
        namespace = parser.parse_args(argv)
        cls.populate_arguments(parser)

        try:
            command = cls.from_namespace(namespace)
        except ArgumentsError as e:
            parser.error(str(e))

        with handle_cli_exception(command):
            command()

        return 0

    @classmethod
    def from_namespace(cls: Type[T], namespace: Namespace) -> T:
        fields = cls.__dataclass_fields__
        values = {
            name: value for name, value in namespace.__dict__.items() if name in fields
        }
        return cls(**values)  # add custom validation in __post_init__

    @classmethod
    def populate_arguments(cls, parser: ArgumentParser) -> None:
        """
        :param parser: subcommand parser instance to set arguments for
        """

        fields: dict[str, Field] = cls.__dataclass_fields__.copy()

        # Not using typing.get_type_hints() to avoid forward refs evaluation
        # allowing to use Python 3.10 syntax in annotations
        annotations: dict[str, object] = {}
        for cls in reversed(cls.__mro__):
            annotations.update(getattr(cls, "__annotations__", {}).copy())

        for field_name, annotation in annotations.items():
            try:
                field_info = fields.pop(field_name)
            except KeyError:
                continue

            metadata = field_info.metadata

            if not field_info.init:  # pragma: no cover
                if metadata:
                    raise TypeError(
                        f"{field_name} on {cls} has argument metadata but has is no-init."
                    )
                continue

            if not metadata:
                if (
                    field_info.default is dataclasses.MISSING
                    and field_info.default_factory is dataclasses.MISSING
                ):  # pragma: no cover
                    raise TypeError(
                        f"{field_name} on {cls} is missing argument metadata and default value."
                    )
                continue

            kwargs = {"help": metadata["help"]}

            if str(annotation) == "bool" and "action" not in metadata:
                kwargs["action"] = "store_true"
            elif "action" in metadata:
                kwargs["action"] = metadata["action"]

            if metadata.get("default") is not None:
                kwargs["default"] = metadata["default"]
            if "nargs" in metadata:
                kwargs["nargs"] = metadata["nargs"]
            if "choices" in metadata:
                kwargs["choices"] = metadata["choices"]

            if flags := metadata.get("argument"):
                first, *rest = flags
                if not rest and len(first) == 2:
                    flags.append("--" + field_name.replace("_", "-"))
                args = flags
                if "choices" not in kwargs and kwargs.get("action") not in {
                    "store_true",
                    "count",
                }:
                    kwargs["metavar"] = f"<{field_name}>"
            else:
                args = (field_name,)
            try:
                parser.add_argument(*args, **kwargs)
            except Exception as e:  # pragma: no cover
                raise TypeError(f"Failed to populate arguments for {cls}") from e

        if fields:  # pragma: no cover
            raise TypeError(f"{list(fields)} on {cls.__name__} must have annotations")


class CLI(ABC):
    """Base class for CLI applications."""

    @classmethod
    def run(cls, argv: list[str] | None = None) -> int:
        parser, subparsers = cls.create_parser()
        namespace = parser.parse_args(argv)
        command_cls: Command = getattr(cls, namespace.command)
        try:
            command = command_cls.from_namespace(namespace)
        except ArgumentsError as e:
            # ugly and brittle, but I just want this to work at the moment.
            # less brittle strategy would be assign a classvar on each command
            subparsers[namespace.command].error(str(e))

        with handle_cli_exception(command):
            command()

        return 0

    @classmethod
    def create_parser(
        cls, command: str | None = None
    ) -> tuple[HelpfulParser, dict[str, HelpfulParser]]:
        parser = HelpfulParser(
            description=cls.__doc__ and cleandoc(cls.__doc__).split("\n")[0],
        )

        subparsers_map = {}
        subparsers = parser.add_subparsers(
            parser_class=HelpfulParser,
            dest="command",
            required=True,
            title="commands",
        )

        for name, attr in cls.__dict__.items():
            if not isinstance(attr, type) or not issubclass(attr, Command):
                continue

            command_cls = attr
            doc = cleandoc(command_cls.__doc__ or "")
            help_text, *desc_lines = doc.splitlines(True)
            subparsers_map[name] = subparser = subparsers.add_parser(
                name,
                help=help_text,
                description=doc,
                formatter_class=RawDescriptionHelpFormatter,
            )
            command_cls.populate_arguments(subparser)
            # mypy fix: Using setattr to avoid attribute error
            setattr(command_cls, "_active_parser", subparser)

        return parser, subparsers_map
