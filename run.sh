#!/bin/bash
# Absolute path to the script folder
APP_DIR="$(dirname "$(readlink -f "$0")")"

# Activate the local virtual environment
source "$APP_DIR/.venv/bin/activate"

# Launch the PySide6 UI app
python "$APP_DIR/main.py" "$@"
