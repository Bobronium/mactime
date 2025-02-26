import json
import sys
import pytest
from datetime import datetime, timedelta
from pathlib import Path
import os
import subprocess

from mactime.cli import MacTime
from mactime.constants import OPENED_NAME
from mactime.core import TimeSpecAttrs
from mactime.core import get_last_opened_dates
from mactime.core import get_timespec_attrs
from mactime.errors import PathNotFoundError
from mactime.utils import get_finder_view


def datetime_close_to(dt1: datetime, dt2: datetime, tolerance_seconds: int = 2) -> bool:
    """Check if two datetimes are within tolerance of each other."""
    return abs(dt1 - dt2) <= timedelta(seconds=tolerance_seconds)


def compare_attrs(before: TimeSpecAttrs, after: dict, expected_changes: dict) -> None:
    """Compare file attributes before and after modification."""
    # Handle changed attribute separately as it always updates
    before_changed = before.pop("changed")
    after_changed = after.pop("changed")
    assert datetime_close_to(before_changed, after_changed)

    # Verify expected changes
    for attr, expected in expected_changes.items():
        actual = after.pop(attr)
        assert actual != before.pop(attr), f"{attr} was already set to expected value"
        assert actual == expected, f"{attr} was not set to expected value"
        before[attr] = after[attr] = expected  # just to get the whole picture

    assert after.pop("backed_up") == before.pop("backed_up")  # always unchanged
    assert after == before, "Unexpected attribute changes"


@pytest.fixture
def run_mactime(capsys):
    """Fixture to run mactime command directly with output capture."""

    def _run_mactime(args):
        assert capsys._is_started
        cmd = ["mactime"] + args
        # return subprocess.run(cmd, capture_output=True, check=False)
        try:
            returncode = MacTime.run(args)
            captured = capsys.readouterr()
            return subprocess.CompletedProcess(
                cmd, returncode, stdout=captured.out, stderr=captured.err
            )
        except SystemExit as e:
            captured = capsys.readouterr()
            return subprocess.CompletedProcess(
                cmd, e.code, stdout=captured.out, stderr=captured.err
            )
        finally:
            with capsys.disabled():
                print(captured.out)
                print(captured.err, file=sys.stderr)

    yield _run_mactime


@pytest.fixture
def temp_file(tmp_path):
    """Create a temporary file for testing."""
    file_path = tmp_path / "test.txt"
    with open(file_path, "w") as f:
        f.write("test content")
    return file_path


@pytest.fixture
def temp_dir_with_files(tmp_path):
    """Create a temporary directory with multiple files for testing."""
    dir_path = tmp_path / "test_dir"
    dir_path.mkdir()

    # Create files in root
    (dir_path / "file1.txt").write_text("content1")
    (dir_path / "file2.txt").write_text("content2")

    # Create subdirectory with files
    subdir = dir_path / "subdir"
    subdir.mkdir()
    (subdir / "file3.txt").write_text("content3")
    return dir_path


@pytest.fixture
def symlink_file(temp_file):
    """Create a symlink to a temporary file."""
    link_path = Path(str(temp_file) + "_link")
    os.symlink(temp_file, link_path)
    yield link_path
    if link_path.exists():
        link_path.unlink()


class TestMactimeGet:
    def test_get_all_attributes(self, temp_file, run_mactime):
        """Test getting all attributes of a file."""
        result = run_mactime(["get", str(temp_file)])
        assert result.returncode == 0

        attrs = get_timespec_attrs(temp_file)
        attrs[OPENED_NAME] = next(iter(get_last_opened_dates([temp_file]).values()))
        assert result.stdout.strip() == get_finder_view({str(temp_file): attrs}).strip()

    def test_get_all_attributes_json(self, temp_file, run_mactime):
        """Test getting all attributes of a file."""
        opened = get_last_opened_dates([temp_file])
        result = run_mactime(["get", str(temp_file), "-F", "json"])
        assert result.returncode == 0

        attrs = get_timespec_attrs(temp_file)
        attrs[OPENED_NAME] = next(iter(get_last_opened_dates([temp_file]).values()))

        assert json.loads(result.stdout.strip()) == {
            str(temp_file): json.loads(json.dumps(attrs, default=datetime.isoformat))
        }

    def test_get_specific_attribute(self, temp_file, run_mactime):
        """Test getting a specific attribute using full name."""
        attrs_before = get_timespec_attrs(temp_file)
        result = run_mactime(["get", str(temp_file), "-N", "modified"])
        assert result.returncode == 0

        result_time = datetime.fromisoformat(result.stdout.strip())
        assert result_time == attrs_before["modified"]

    def test_get_shorthand_attribute(self, temp_file, run_mactime):
        """Test getting an attribute using shorthand notation."""
        attrs_before = get_timespec_attrs(temp_file)
        result = run_mactime(["get", str(temp_file), "-N", "m"])
        assert result.returncode == 0

        result_time = datetime.fromisoformat(result.stdout.strip())
        assert result_time == attrs_before["modified"]


class TestMactimeSet:
    def test_set_modification_time(self, temp_file, run_mactime):
        """Test setting modification time."""
        target_time = datetime.now()

        attrs_before = get_timespec_attrs(temp_file)
        assert attrs_before["modified"] != target_time

        result = run_mactime(["set", str(temp_file), "-m", target_time.isoformat()])
        assert result.returncode == 0

        attrs_after = get_timespec_attrs(temp_file)
        compare_attrs(attrs_before, attrs_after, {"modified": target_time})

    def test_set_multiple_attributes(self, temp_file, run_mactime):
        """Test setting multiple attributes at once."""
        mod_time = datetime.now()
        create_time = datetime.now() + timedelta(seconds=1)  # Must be after mod_time

        attrs_before = get_timespec_attrs(temp_file)

        result = run_mactime(
            [
                "set",
                str(temp_file),
                "-m",
                mod_time.isoformat(),
                "-c",
                create_time.isoformat(),
            ]
        )
        assert result.returncode == 0

        attrs_after = get_timespec_attrs(temp_file)

        expected = {"modified": mod_time, "created": create_time}
        compare_attrs(attrs_before, attrs_after, expected)

    def test_set_attribute_from_another(self, temp_file, run_mactime):
        """Test setting an attribute using another as source."""
        attrs_before = get_timespec_attrs(temp_file)

        result = run_mactime(["set", str(temp_file), "-c", "m"])
        assert result.returncode == 0

        attrs_after = get_timespec_attrs(temp_file)
        compare_attrs(attrs_before, attrs_after, {"created": attrs_before["modified"]})

    def test_set_recursive(self, temp_dir_with_files, run_mactime):
        """Test setting attributes recursively."""
        target_time = datetime.now()

        result = run_mactime(
            ["set", "-r", str(temp_dir_with_files), "-m", target_time.isoformat()]
        )
        assert result.returncode == 0

        # Check all files in directory
        for path in temp_dir_with_files.rglob("*.txt"):
            attrs_after = get_timespec_attrs(path)
            assert attrs_after["modified"] == target_time

    def test_set_invalid_time(self, temp_file, run_mactime):
        """Test setting invalid time format."""
        result = run_mactime(["set", str(temp_file), "-m", "invalid_time"])
        assert result.returncode != 0

    def test_symlink_follow_vs_no_follow(self, symlink_file, temp_file, run_mactime):
        """Test symlink behavior with and without -n/--no-follow."""
        target_time = datetime.now()

        # Set time on target through symlink (following)
        result = run_mactime(["set", str(symlink_file), "-m", target_time.isoformat()])
        assert result.returncode == 0

        # Verify target was modified but symlink wasn't
        target_attrs = get_timespec_attrs(temp_file)
        link_attrs = get_timespec_attrs(symlink_file, no_follow=True)
        assert target_attrs["modified"] == target_time
        assert link_attrs["modified"] != target_time

        # Now set different time on symlink itself (no follow)
        link_time = datetime.now() + timedelta(hours=1)
        result = run_mactime(
            ["set", "-n", str(symlink_file), "-m", link_time.isoformat()]
        )
        assert result.returncode == 0

        # Verify only symlink was modified
        target_attrs_after = get_timespec_attrs(temp_file)
        link_attrs_after = get_timespec_attrs(symlink_file, no_follow=True)
        assert target_attrs_after == target_attrs  # Target unchanged
        assert link_attrs_after["modified"] == link_time  # Link modified

    def test_symlink_recursive(self, temp_dir_with_files, temp_file, run_mactime):
        """Test that recursive operations handle symlinks correctly."""
        # Create a symlink in the test directory
        test_link = Path(temp_dir_with_files) / "test_link"
        os.symlink(temp_file, test_link)

        target_time = datetime.now()

        # Test recursive set without -n (should follow links)
        result = run_mactime(
            ["set", "-r", str(temp_dir_with_files), "-m", target_time.isoformat()]
        )
        assert result.returncode == 0

        # Verify target was modified through symlink
        target_attrs = get_timespec_attrs(temp_file)
        assert target_attrs["modified"] == target_time

        # Test recursive set with -n
        new_time = datetime.now() + timedelta(hours=1)
        result = run_mactime(
            ["set", "-r", "-n", str(temp_dir_with_files), "-m", new_time.isoformat()]
        )
        assert result.returncode == 0

        # Verify symlink was modified but not target
        link_attrs = get_timespec_attrs(test_link, no_follow=True)
        target_attrs_after = get_timespec_attrs(temp_file)
        assert link_attrs["modified"] == new_time
        assert target_attrs_after == target_attrs  # Target unchanged


class TestMactimeTransfer:
    def test_match_single_attribute(self, temp_file, tmp_path, run_mactime):
        """Test matchring a single attribute between files."""
        source = tmp_path / "source.txt"
        source.write_text("source content")

        source_attrs = get_timespec_attrs(source)
        target_attrs_before = get_timespec_attrs(temp_file)

        result = run_mactime(["match", str(source), str(temp_file), "-m"])
        assert result.returncode == 0

        target_attrs_after = get_timespec_attrs(temp_file)
        compare_attrs(
            target_attrs_before,
            target_attrs_after,
            {"modified": source_attrs["modified"]},
        )

    def test_match_multiple_attributes(self, temp_file, tmp_path, run_mactime):
        """Test matchring multiple attributes."""
        source = tmp_path / "source.txt"
        source.write_text("source content")

        source_attrs = get_timespec_attrs(source)
        target_attrs_before = get_timespec_attrs(temp_file)

        result = run_mactime(["match", str(source), str(temp_file), "-m", "-c", "-a"])
        assert result.returncode == 0

        target_attrs_after = get_timespec_attrs(temp_file)
        expected = {
            "modified": source_attrs["modified"],
            "created": source_attrs["created"],
            "accessed": source_attrs["accessed"],
        }
        compare_attrs(target_attrs_before, target_attrs_after, expected)

    def test_match_recursive(self, temp_dir_with_files, temp_file, run_mactime):
        """Test matchring attributes recursively."""
        source_attrs = get_timespec_attrs(temp_file)

        source_attrs.pop("changed")

        result = run_mactime(
            ["match", "-r", str(temp_file), str(temp_dir_with_files), "--all"]
        )
        assert result.returncode == 0

        for path in temp_dir_with_files.rglob("*.txt"):
            attrs = get_timespec_attrs(path)
            attrs.pop("changed")
            assert attrs == source_attrs


class TestErrorHandling:
    def test_path_not_found_error(self, tmp_path, run_mactime):
        """Test error handling when path doesn't exist."""
        nonexistent_path = tmp_path / "does_not_exist.txt"

        # Get attributes of non-existent file
        result = run_mactime(["get", str(nonexistent_path)])
        assert result.returncode == PathNotFoundError.exit_code
        assert "Path not found" in result.stderr

        # Set attributes on non-existent file
        result = run_mactime(
            ["set", str(nonexistent_path), "-m", "2024-01-01T12:00:00"]
        )
        assert result.returncode == PathNotFoundError.exit_code
        assert "Path not found" in result.stderr

    def test_invalid_command(self, run_mactime):
        """Test handling of invalid command."""
        result = run_mactime(["invalid_command"])
        assert result.returncode != 0

    @pytest.mark.parametrize("command", ["get", "set", "match"])
    def test_help_commands(self, run_mactime, command):
        """Test help output for all commands."""
        result = run_mactime([command, "-h"])
        assert result.returncode == 0
        assert "usage:" in result.stdout
