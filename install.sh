#!/usr/bin/env bash

# Simple, effective mactime installer
# ----------------------------------

set -euo pipefail
IFS=$'\n\t'

# Output functions
log_color() {
    local color="$1"
    local message="$2"
    printf "\033[0;${color}m%s\033[0m\n" "$message"
}


green() { log_color "32" "$1"; }
blue() { if $VERBOSE; then log_color "34" "$1"; fi }
yellow() { if $VERBOSE; then log_color "33" "$1"; fi }
red() { log_color "31" "$1"; }

# Check dependencies
check_dependencies() {
  for cmd in git ln; do
    if ! command -v "$cmd" &> /dev/null; then
      red "Error: $cmd is required but not found. Please install it first."
      exit 1
    fi
  done
}

# Get source location and prepare main script path
setup_source_location() {
  # Get script location
  SCRIPT_PATH="$(realpath "$0")"
  SCRIPT_DIR="$(dirname "$SCRIPT_PATH")"

  # Determine source location
  if [ -f "$SCRIPT_DIR/main.py" ]; then
    # Local installation
    blue "Installing from local directory: $SCRIPT_DIR"
    MAIN_SCRIPT="$SCRIPT_DIR/main.py"
  else
    # Remote installation
    blue "Installing from GitHub..."
    mkdir -p ~/.local/src
    REPO_DIR="$HOME/.local/src/mactime"
    MAIN_SCRIPT="$REPO_DIR/main.py"

    if [ -d "$REPO_DIR" ]; then
      blue "Updating existing repository..."
      git -C "$REPO_DIR" fetch --quiet
      git -C "$REPO_DIR" reset --hard origin/main --quiet
    else
      blue "Cloning repository..."
      git clone --quiet https://github.com/Bobronium/mactime.git "$REPO_DIR"
    fi
  fi
}

# Create a symlink with backup protection
create_symlink() {
  local src="$1"
  local dest="$2"

  if [ ! -e "$src" ]; then
    red "Error: Source file $src does not exist!"
    return 1
  fi

  if [ -L "$dest" ]; then
    rm "$dest"
  elif [ -e "$dest" ]; then
    yellow "Note: Creating backup of existing file: ${dest}.bak"
    mv "$dest" "${dest}.bak"
  fi

  ln -s "$src" "$dest"
  blue "Created symlink: $dest -> $src"
}

# Setup symlinks
setup_symlinks() {
  blue "Creating symlinks..."
  create_symlink "$MAIN_SCRIPT" "$BIN_DIR/mactime"
  create_symlink "$MAIN_SCRIPT" "$BIN_DIR/whenwhat"
  create_symlink "$MAIN_SCRIPT" "$BIN_DIR/ww"
}

# Ensure PATH contains ~/.local/bin
setup_path() {
  if ! echo "$PATH" | tr ':' '\n' | grep -q "^$HOME/.local/bin$"; then
    yellow "Adding ~/.local/bin to your PATH..."

    # Determine which shell configs exist
    shell_configs=()
    [ -f "$HOME/.zshrc" ] && shell_configs+=("$HOME/.zshrc")
    [ -f "$HOME/.bashrc" ] && shell_configs+=("$HOME/.bashrc")

    if [ ${#shell_configs[@]} -gt 0 ]; then
      for config in "${shell_configs[@]}"; do
        if ! grep -q 'export PATH="$HOME/.local/bin:$PATH"' "$config"; then
          yellow "Updating $config..."
          echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$config"
        fi
      done
      export PATH="$HOME/.local/bin:$PATH"  # Update current session
    else
      yellow "No shell config files found. You'll need to add ~/.local/bin to your PATH manually."
    fi
  fi
}

# Verify installation
verify_installation() {
  if command -v mactime &> /dev/null || [[ -x "$BIN_DIR/mactime" && "$PATH" == *"$BIN_DIR"* ]]; then
    green "Installed 3 executables: mactime, whenwhat, ww"
  else
    yellow "Note: Start a new terminal session to use mactime."
  fi
}

# Main function
main() {
  # Create bin directory
  mkdir -p ~/.local/bin
  BIN_DIR="$HOME/.local/bin"

  VERBOSE=false
  while getopts ":v" opt; do
    case ${opt} in
      v ) VERBOSE=true ;;
      \? ) echo "Usage: $0 [-v]" >&2; exit 1 ;;
    esac
  done
  check_dependencies
  setup_source_location
  setup_symlinks
  setup_path
  verify_installation
}

# Execute main function
main "$@"
