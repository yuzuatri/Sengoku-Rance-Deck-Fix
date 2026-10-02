#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -eu
project_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
    printf '%s\n' 'Python 3.9 or newer is required.' >&2
    if command -v kdialog >/dev/null 2>&1; then
        kdialog --error 'Python 3.9 or newer is required. No game files were changed.'
    fi
    exit 1
fi
exec python3 "$project_dir/patch.py" --gui "$@"
