#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

for path in README.md LICENSE.md NOTICE SECURITY.md CONTRIBUTING.md \
  docs/PROJECT_CHARTER.md docs/ROADMAP.md \
  docs/research/RESEARCH_PLAN.md docs/research/EXISTING_CHAT_BASELINE.md \
  docs/research/platform-and-reuse-deep-dive.md docs/research/reuse-matrix.md \
  docs/research/x-account-and-policy-risk.md docs/research/report-methodology.md \
  docs/research/activation-data-flow-and-synthetic-tests.md \
  docs/adr/0001-platform-selection.md; do
  test -s "$repo_root/$path" || { echo "missing or empty: $path" >&2; exit 1; }
done

if find "$repo_root" -type f \
  \( -iname '*.mp4' -o -iname '*.mov' -o -iname '*.m4v' -o -iname '*.webm' \
     -o -iname '*.sqlite' -o -iname '*.sqlite3' -o -iname '*.db' \
     -o -iname '*.pem' -o -iname '*.key' -o -name '.env' \) \
  -not -path "$repo_root/.git/*" | grep -q .; then
  echo "private capture, database, or credential-like file found" >&2
  exit 1
fi

grep -Fq 'No production version is currently supported' "$repo_root/SECURITY.md"
grep -Fq 'Required Notice: Copyright © 2026 Rolando Carreon' "$repo_root/NOTICE"
python3 "$repo_root/tests/check_docs.py"
echo 'repository policy checks passed'
