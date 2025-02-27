from __future__ import annotations

import json
import shutil
from datetime import datetime
from datetime import timedelta
from pathlib import Path

from mactime.constants import ADDED_NAME
from mactime.constants import EPOCH
from mactime.constants import FINDER_ATTRS
from mactime.constants import OPENED_NAME


from typing import List, Union, Tuple, Generator

RowData = List[Union[str, Tuple[str, str]]]
TableData = List[RowData]


def generate_pretty_table(
    headers: List[str], rows: TableData, min_width: int = 15, padding: int = 1
) -> Generator[str, None, None]:
    """
    Generate a pretty formatted table with headers and rows with continuous lines,
    adjusted for the current terminal size.

    Args:
        headers: List of header strings
        rows: List of rows, where each row contains either strings or tuples of
              (full_value, concise_value)
        min_width: Minimum width for each column
        padding: Number of spaces for padding in each cell

    Yields:
        Each line of the table as a string
    """
    terminal_width = shutil.get_terminal_size((120, 24)).columns

    def get_string_value(
        cell: Union[str, Tuple[str, str]], concise: bool = False
    ) -> str:
        if isinstance(cell, tuple) and len(cell) == 2:
            return str(cell[1]) if concise else str(cell[0])
        return str(cell)

    # Calculate initial column widths based on full-size content
    initial_widths = []
    for i in range(len(headers)):
        # Get maximum width needed for this column (header or data)
        header_width = len(headers[i])
        data_width = max(
            [len(get_string_value(row[i])) if i < len(row) else 0 for row in rows],
            default=0,
        )
        initial_widths.append(max(header_width, data_width, min_width) + padding * 2)

    # Calculate total table width including separators
    total_width = sum(initial_widths) + len(headers) + 1

    # If table is wider than terminal, first try using concise values
    if total_width > terminal_width:
        # Try using concise values for each column, from left to right
        for col_idx in range(len(headers)):
            # Only try columns that have tuple values
            has_concise_values = any(
                i < len(row) and isinstance(row[i], tuple)
                for row in rows
                if i == col_idx
            )

            if has_concise_values:
                # Calculate new width using concise values for this column
                concise_data_width = max(
                    [
                        len(get_string_value(row[col_idx], True))
                        if col_idx < len(row)
                        else 0
                        for row in rows
                    ],
                    default=0,
                )

                # Calculate width reduction
                new_col_width = (
                    max(concise_data_width, min_width, len(headers[col_idx]))
                    + padding * 2
                )
                width_reduction = initial_widths[col_idx] - new_col_width

                if width_reduction > 0:
                    initial_widths[col_idx] = new_col_width
                    total_width -= width_reduction

                    # If we've reduced enough, stop
                    if total_width <= terminal_width:
                        break

    # If still too wide, adjust column widths proportionally
    if total_width > terminal_width:
        # Calculate how much we need to reduce
        excess_width = total_width - terminal_width

        # Distribute the reduction proportionally, but ensure min_width is respected
        remaining_excess = excess_width
        flexible_columns = [i for i in range(len(initial_widths))]

        while remaining_excess > 0 and flexible_columns:
            # Calculate reduction per column
            total_flexible_remaining = sum(initial_widths[i] for i in flexible_columns)
            for i in flexible_columns[:]:
                # Calculate fair reduction for this column
                fair_reduction = (
                    int(
                        remaining_excess
                        * (initial_widths[i] / total_flexible_remaining)
                    )
                    + 1
                )

                # Make sure we don't go below min_width + padding*2
                max_reduction = max(0, initial_widths[i] - (min_width + padding * 2))
                actual_reduction = min(fair_reduction, max_reduction)

                if actual_reduction <= 0:
                    # This column can't be reduced further
                    flexible_columns.remove(i)
                else:
                    initial_widths[i] -= actual_reduction
                    remaining_excess -= actual_reduction

                if remaining_excess <= 0:
                    break

    col_widths = initial_widths

    # Determine which columns need concise values
    use_concise = [False] * len(headers)

    for i in range(len(headers)):
        data_full_width = max(
            [len(get_string_value(row[i])) if i < len(row) else 0 for row in rows],
            default=0,
        )
        # If the full width doesn't fit in the allocated space, use concise version
        if data_full_width > (col_widths[i] - padding * 2):
            use_concise[i] = True

    # Box drawing characters for continuous lines
    horizontal = "─"
    vertical = "│"
    top_left = "┌"
    top_right = "┐"
    bottom_left = "└"
    bottom_right = "┘"
    top_junction = "┬"
    bottom_junction = "┴"
    left_junction = "├"
    right_junction = "┤"
    cross_junction = "┼"

    # Function to truncate text while preserving beginning and end
    def truncate_text(text: str, max_length: int) -> str:
        if len(text) <= max_length:
            return text

        if max_length < 7:  # If extremely narrow, just use ellipsis
            return "..." if max_length >= 3 else ""

        # Divide space between beginning and end
        start_chars = (max_length - 3) // 2
        end_chars = max_length - 3 - start_chars
        return text[:start_chars] + "..." + text[-end_chars:]

    # Generate top border
    top_border = top_left
    for i, width in enumerate(col_widths):
        top_border += horizontal * width
        if i < len(col_widths) - 1:
            top_border += top_junction
    top_border += top_right
    yield top_border

    # Generate headers
    header_row = vertical
    for i, header in enumerate(headers):
        # Truncate header if too long
        display_header = truncate_text(header, col_widths[i] - padding * 2)
        header_row += (
            " " * padding + display_header.ljust(col_widths[i] - padding) + vertical
        )
    yield header_row

    # Generate header separator
    header_sep = left_junction
    for i, width in enumerate(col_widths):
        header_sep += horizontal * width
        if i < len(col_widths) - 1:
            header_sep += cross_junction
    header_sep += right_junction
    yield header_sep

    # Generate data rows
    for j, row in enumerate(rows):
        data_row = vertical
        for i in range(len(headers)):
            # Get appropriate value (concise or full)
            if i < len(row):
                cell_value = get_string_value(row[i], use_concise[i])
            else:
                cell_value = ""

            # Truncate cell value if still too long
            display_value = truncate_text(cell_value, col_widths[i] - padding * 2)

            data_row += (
                " " * padding + display_value.ljust(col_widths[i] - padding) + vertical
            )
        yield data_row

        # Generate row separator if not the last row
        if j < len(rows) - 1:
            row_sep = left_junction
            for i, width in enumerate(col_widths):
                row_sep += horizontal * width
                if i < len(col_widths) - 1:
                    row_sep += cross_junction
            row_sep += right_junction
            # yield row_sep (commented out as in original code)

    # Generate bottom border
    bottom_border = bottom_left
    for i, width in enumerate(col_widths):
        bottom_border += horizontal * width
        if i < len(col_widths) - 1:
            bottom_border += bottom_junction
    bottom_border += bottom_right
    yield bottom_border


def format_path(path: str) -> str:
    current_workdir = Path(".").absolute()
    try:
        return '"./' + str(Path(path).relative_to(current_workdir)) + '"'
    except ValueError:
        return str(path)


def get_finder_view(paths: dict[str, dict[str, datetime]]) -> str:
    headers = ["Name", *FINDER_ATTRS.values()]

    rows = []
    min_width = max(len(h) for h in headers)
    for path, dates in paths.items():
        row = [path]
        for key in FINDER_ATTRS:
            dt = dates[key]
            if dt == EPOCH and key in {ADDED_NAME, OPENED_NAME}:
                row.append("--")
            else:
                concise = finder_date(dt, concise=True)
                min_width = max(min_width, len(concise))
                row.append((finder_date(dt), concise))
        rows.append(row)
    return "\n".join(generate_pretty_table(headers, rows, min_width=min_width))


def finder_date(dt: datetime, *, concise: bool = False) -> str:
    """
    Format a datetime object to match the format in the screenshot.

    For today's dates: "Today at HH:MM"
    For yesterday's dates: "Yesterday at HH:MM"
    For other dates: "DD Month YYYY at HH:MM"
    """
    now = datetime.now()
    today = now.date()
    yesterday = today - timedelta(days=1)

    # TODO: account for i18n.

    if dt.date() == today:
        return f"Today at {dt.strftime('%H:%M')}"

    if dt.date() == yesterday:
        return f"Yesterday at {dt.strftime('%H:%M')}"

    if concise:
        return f"{dt.day:02}.{dt.month:02}.{dt.year} at {dt.strftime('%H:%M')}"
    return f"{dt.day} {dt.strftime('%B')} {dt.year} at {dt.strftime('%H:%M')}"


def get_yaml_view(paths: dict[str, dict[str, datetime]]) -> str:
    output = []

    for path, attributes in paths.items():
        # Quote the path using JSON for proper escaping
        path = str(path)
        quoted = json.dumps(path)
        needs_quotes = (
            not path
            or quoted[1:-1] != path
            or path.startswith(r"\:{}[],&*#?|<>=!%@`")
            or path.strip() != path
            or "\n" in path
        )
        if needs_quotes:
            path = quoted

        output.append(f"{path}:")
        for attr_name, attr_time in attributes.items():
            output.append(f"  {attr_name}: {attr_time.isoformat()}")

    return "\n".join(output)
