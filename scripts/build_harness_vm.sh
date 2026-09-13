#!/usr/bin/env bash
set -euo pipefail

repo_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
output_dir="${1:-$repo_root/build/native}"
architecture="$(uname -m)"
mkdir -p "$output_dir"
xcrun swiftc -O -target "${architecture}-apple-macosx13.0" -framework JavaScriptCore "$repo_root/native/harness-vm/main.swift" -o "$output_dir/xfi-harness-vm"
printf '%s\n' "$output_dir/xfi-harness-vm"

