#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
dist="$root/dist"
archive="$dist/recall.zip"
temp="$dist/_package"

rm -rf "$temp"
mkdir -p "$temp" "$dist"
rm -f "$archive"

for item in .codex-plugin skills hooks scripts docs examples memory_config.template.json README.md CHANGELOG.md LICENSE; do
  if [ -e "$root/$item" ]; then
    cp -R "$root/$item" "$temp/"
  fi
done

find "$temp" \( -type d -name "__pycache__" -o -type f -name "*.pyc" \) -exec rm -rf {} +

(cd "$temp" && zip -qr "$archive" .)
rm -rf "$temp"
echo "Built $archive"
