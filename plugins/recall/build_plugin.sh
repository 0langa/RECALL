#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
dist="$root/dist"
archive="$dist/recall.zip"
temp="$dist/_package"
python_bin="${PYTHON:-python}"
validator="${HOME}/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py"

(cd "$root" && "$python_bin" -m unittest discover -s tests)
if [ -f "$validator" ]; then
  "$python_bin" "$validator" "$root"
else
  echo "Warning: plugin validator not found at $validator; skipping validator gate." >&2
fi
(cd "$root" && "$python_bin" ./scripts/smoke_recall.py --json)

rm -rf "$temp"
mkdir -p "$temp" "$dist"
rm -f "$archive"

for item in .codex-plugin assets skills hooks scripts docs examples memory_config.template.json README.md CHANGELOG.md LICENSE; do
  if [ -e "$root/$item" ]; then
    cp -R "$root/$item" "$temp/"
  fi
done

find "$temp" \( -type d -name "__pycache__" -o -type f -name "*.pyc" \) -exec rm -rf {} +

(cd "$temp" && zip -qr "$archive" .)
rm -rf "$temp"
"$python_bin" "$root/scripts/inspect_package.py" "$archive"
echo "Built $archive"
