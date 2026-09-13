# Research Plan

## Decision

Select the smallest architecture that can support both safe recording analysis and a passive, local, no-API visible-post collector while minimizing X account risk and preserving report quality.

## Platforms to compare

| Candidate | Required questions |
| --- | --- |
| Screen-recording pipeline | Can FFmpeg, scene/change detection, OCR, and optional local vision extract complete posts efficiently without retaining unrelated screen content? |
| Passive WebExtension | Can exact-origin content scripts collect only visible post units as the user scrolls, deactivate with X tabs, and avoid cookies/private APIs/account mutation? |
| Automated browser collector | What account/Terms, fingerprinting, CAPTCHA, and maintenance risks arise even without stealth? |
| Private GraphQL/web clients | How often do endpoints break, what session material is required, and why should these be rejected or isolated? |
| Official X API | What current cost, feed coverage, ranking limitations, and policy benefits apply? |
| Native macOS/iOS app | Does a native shell add a concrete capability or only screen/accessibility permissions and packaging cost? |
| Hybrid | Is a local application plus passive extension justified for video processing, local database, and report generation? |

## Reuse research

Inspect upstream source, releases, maintenance, permissions, security policy, dependency tree, and license for candidates such as XClipper, XActions, Twikit, tweetkit-x, WXT, Plasmo, Playwright, FFmpeg, OpenCV, Apple Vision, Tesseract, PaddleOCR, PySceneDetect, SQLite libraries, and privacy/redaction tooling. Marketing claims and repository READMEs are discovery leads, not proof.

Projects centered on stealth, CAPTCHA bypass, account farming, proxy rotation, fingerprint evasion, mass engagement, or private-API abuse are rejection evidence rather than dependencies.

## Required outputs

1. Comprehensive cited platform and reuse report.
2. Exact reuse/license/maintenance matrix.
3. Recommended architecture and rejected alternatives.
4. Data-flow and automatic activation/deactivation proposal.
5. X policy/account-risk matrix with explicit residual risk.
6. Synthetic test strategy and real-account stop gate.
7. Completed ADR 0001.

