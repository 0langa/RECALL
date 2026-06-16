#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python_bin="${PYTHON:-python}"
"$python_bin" "$root/scripts/build_plugin.py" --plugin-root "$root" "$@"
