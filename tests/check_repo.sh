#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

for path in README.md LICENSE.md NOTICE SECURITY.md CONTRIBUTING.md \
  docs/PROJECT_CHARTER.md docs/ROADMAP.md \
  docs/research/RESEARCH_PLAN.md docs/research/EXISTING_CHAT_BASELINE.md \
  docs/research/platform-and-reuse-deep-dive.md docs/research/reuse-matrix.md \
  docs/research/x-account-and-policy-risk.md docs/research/report-methodology.md \
  docs/research/activation-data-flow-and-synthetic-tests.md \
  docs/adr/0001-platform-selection.md THIRD_PARTY_NOTICES.md \
  docs/gate1/README.md docs/gate1/THREAT_MODEL.md \
  docs/gate1/ANALYSIS_CONTRACTS.md docs/gate1/RETENTION_AND_EXPORT.md \
  docs/gate1/EXTENSION_LIFECYCLE.md docs/gate1/MODEL_HANDOFF.md \
  docs/gate1/METRICS_AND_ORACLES.md docs/gate1/DEPENDENCY_AND_SBOM_PLAN.md \
  docs/gate1/GATE2_WORK_BREAKDOWN.md docs/gate1/REVIEW_RECORD.md \
  docs/gate1/POLICY_RECHECK.md \
  contracts/v1/manifest.proposal.json contracts/v1/manifest.synthetic-test-only.json \
  contracts/v1/browser-test-boundary.json contracts/v1/extension-lifecycle.json \
  schemas/v1/common.schema.json schemas/v1/session.schema.json \
  schemas/v1/observation.schema.json schemas/v1/canonical-post.schema.json \
  schemas/v1/analysis.schema.json schemas/v1/envelope.schema.json \
  schemas/v1/model-handoff.schema.json \
  fixtures/synthetic/v1/manifest.json fixtures/synthetic/v1/dedup-role-collisions.json \
  fixtures/gate2/shared-corpus.json DEPENDENCIES.lock.json sbom/cyclonedx.cdx.json \
  docs/gate2/README.md docs/gate2/PACKAGE_BOUNDARY.md \
  docs/gate2/SECURITY_PRIVACY_REVIEW.md docs/gate2/GATE3_RESIDUAL_RISK.md \
  src/xfi/validation.py src/xfi/store.py src/xfi/analysis.py src/xfi/render.py \
  src/xfi/recording.py src/xfi/browser.py \
  harness/synthetic/manifest.json harness/synthetic/synthetic-harness.js \
  native/recording-helper/main.swift native/harness-vm/main.swift \
  scripts/package_review.py scripts/measure_gate2.py \
  tests/gate1_acceptance.py tests/gate2_core.py tests/gate2_recording.py \
  tests/gate2_browser.py tests/gate2_integration.py tests/gate2_security.py; do
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
python3 "$repo_root/tests/gate1_acceptance.py"
PYTHONPATH="$repo_root/src" python3 "$repo_root/tests/gate2_core.py"
PYTHONPATH="$repo_root/src" python3 "$repo_root/tests/gate2_browser.py"
PYTHONPATH="$repo_root/src" python3 "$repo_root/tests/gate2_recording.py"
PYTHONPATH="$repo_root/src" python3 "$repo_root/tests/gate2_integration.py"
python3 "$repo_root/tests/gate2_security.py"
python3 "$repo_root/scripts/package_review.py" --check
echo 'repository policy and Gate 2 checks passed'
