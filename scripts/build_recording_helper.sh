#!/usr/bin/env bash
set -euo pipefail

repo_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
output_dir="${1:-$repo_root/build/native}"
architecture="$(uname -m)"
mkdir -p "$output_dir"
xcrun swiftc \
  -parse-as-library \
  -O \
  -target "${architecture}-apple-macosx13.0" \
  -framework AppKit \
  -framework AVFoundation \
  -framework CoreMedia \
  -framework CoreVideo \
  -framework Vision \
  "$repo_root/native/recording-helper/main.swift" \
  -o "$output_dir/xfi-recording-helper"
codesign --display --verbose=2 "$output_dir/xfi-recording-helper" >/dev/null 2>&1 || true
printf '%s\n' "$output_dir/xfi-recording-helper"
