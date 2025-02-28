# MacTime (aka WhenWhat or ww)

A Python tool for manipulating macOS file date attributes.

## The Story

I've been organizing my files lately and noticed that there's no easy way to set the "Date Added"
attribute to files in a folder. So I decided to write a library that makes it easy and accessible
through both Python and CLI.

One of the weird goals when writing this project was to not have any dependencies and to be
compatible with Python 3.9+, allowing it to run with macOS' built-in Python.

The code is a mixture of Claude work and mine.

## Features

- View and modify macOS file date attributes
- No dependencies required
- Supports Python 3.9+ (works with macOS built-in Python)
- Multiple command aliases: `mactime`, `whenwhat`, or `ww`
- Batch operations with recursive directory support
- Fast.

## Supported Date Attributes

MacTime supports viewing and modifying the following macOS file date attributes:

| Attribute | Shorthand | Description                | Writable                          |
|-----------|-----------|----------------------------|-----------------------------------|
| created   | c         |  Date Created             | ✅                                 |
| modified  | m         |  Date Modified            | ✅                                 |
| accessed  | a         | Last accessed date         | ✅                                 |
| added     | d         |  Date Added               | ✅                                 |
| changed   | g         | Last attribute change date | ⚠️ Always set to current time     |
| backed_up | b         | Last Backup Date           | ⚠️ Not affected by writings       |
| opened    | o         |  Date Last Opened         | ❌ Read-only (stored in Spotlight) |

## Installation

### UV

```bash
uv tool install mactime
```

### pipx

```bash
pipx install mactime
```

### Pure Python

```shell
bash <(curl -fSL https://raw.githubusercontent.com/Bobronium/mactime/refs/heads/main/install.sh)
```


### pip

```bash
pip install mactime
```

Or simply clone and install from the repository:

```bash
cd mactime
pip install -e .
```

## Command-Line Usage

### Get File Attributes

View date attributes for a file:

```bash
mactime get /tmp/files -ri --order-by added --reversed --format finder
```

```shell
┌──────────────────┬──────────────────┬──────────────────┬──────────────────┬──────────────────┐
│ Name             │ Date Created     │ Date Modified    │ Date Last Opened │ Date Added       │
├──────────────────┼──────────────────┼──────────────────┼──────────────────┼──────────────────┤
│ /tmp/files       │ Today at 22:15   │ Today at 22:16   │ --               │ Today at 22:15   │
│ /tmp/files/1.txt │ Today at 22:16   │ Today at 22:16   │ --               │ Today at 22:16   │
│ /tmp/files/2.txt │ Today at 22:16   │ Today at 22:16   │ --               │ Today at 22:16   │
│ /tmp/files/3.txt │ Today at 22:16   │ Today at 22:16   │ --               │ Today at 22:16   │
└──────────────────┴──────────────────┴──────────────────┴──────────────────┴──────────────────┘
```

Get a specific attribute:

```bash
mactime get /tmp/files/1.txt modified
# Or using shorthand
mactime get /tmp/files/1.txt m
```

### Set File Attributes

Set a specific date attribute:

```bash
# Set modification time to a specific date
mactime set file.txt -m "2023-06-15T14:30:00"

# Set creation date to now
mactime set file.txt -c now

# Set added date to yesterday
mactime set file.txt -d yesterday

# Reset to epoch (Jan 1, 1970)
mactime set file.txt -d epoch
```

Copy values from another attribute:

```bash
# Set creation date to match modification date
mactime set file.txt -c m
```

### Set Multiple Files at Once

```bash
# Set all files in a directory
mactime set *.txt -m "2023-06-15T14:30:00"

# Recursively process all files in directories
mactime set ./documents -r -m "2023-06-15T14:30:00"
```

### Transfer Attributes

Copy attributes from one file to another:

```bash
# Transfer modification date
mactime transfer source.txt target.txt -m

# Transfer all attributes
mactime transfer source.txt target.txt --all

# Transfer to multiple targets
mactime transfer source.txt target1.txt target2.txt -m

# Transfer recursively to files in a directory
mactime transfer source.txt ./dir -r --all
```

### Reset Attributes

Reset attributes to epoch (Jan 1, 1970):

```bash
# Reset modification and creation times
mactime reset file.txt -m -c

# Reset all attributes
mactime reset file.txt --all

# Reset all files in a directory recursively
mactime reset ./dir -r --all
```

## Python API Usage

```python
from mactime.core import get_timespec_attrs, set_path_times, modify_macos_times
from datetime import datetime


# Get all attributes
attrs = get_timespec_attrs("file.txt")
print(f"Created: {attrs['created']}")
print(f"Modified: {attrs['modified']}")
print(f"Added: {attrs['added']}")

# Set specific attributes
modify_macos_times(
    "file.txt",
    created=datetime(2023, 6, 15, 14, 30, 0),
    modified=datetime.now()
)

# Set added date to match creation date
attrs = get_timespec_attrs("file.txt")
set_path_times("file.txt", to_set={}, from_another_attributes={"added": "created"})

# Process multiple files
from mactime.core import resolve_paths


modified = datetime.now()
for file in resolve_paths(["./documents"], recursive=True, include_root=True):
    modify_macos_times(file, modified=modified)
```

## Limitations

- **macOS Only**: This tool uses macOS-specific system calls and will not work on other operating
  systems.
- **Some Attributes Are Read-Only**:
    - `opened` is stored in Spotlight index and cannot be modified.
    - `backed_up` is ignored by the system calls.
    - `changed` is always updated to the current time when attributes are modified.
- **System Permissions**: Modifying some file attributes may require elevated permissions.

## How It Works

MacTime uses the low-level `setattrlist` and `getattrlist` C functions via Python's `ctypes` library
to interact directly with the macOS file system. This approach avoids dependencies and provides
direct access to file metadata that is not accessible through standard Python libraries.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

Distributed under the MIT License. See `LICENSE` for more information.

## Acknowledgements

This project was inspired
by [a Stack Overflow discussion](https://apple.stackexchange.com/questions/40941/how-to-set-date-added-metadata-in-mac-os-x-10-7-lion)
about manipulating macOS file attributes.

## Behavior Notes

### Creation Time Auto-Adjustment

When setting the modification time (`-m`) without explicitly setting the creation time (`-c`) and
new modification time is before current creation time, both will be set to new modification time:

```bash
# This will set both modification AND creation time to "2023-06-15T14:30:00"
# if the current creation time is newer than this date
mactime set file.txt -m "2023-06-15T14:30:00"

# This preserves the original creation time regardless of dates
mactime set file.txt -m "2023-06-15T14:30:00" -c c
```

To preserve the original creation time when setting the modification time, explicitly reference the
current creation time with `-c c`.
