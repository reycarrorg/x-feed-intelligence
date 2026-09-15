# Upstream Reuse and License Provenance

The Gate 3 extension is a selective hybrid, not a wholesale fork. Every adopted idea was reduced to the narrow capability needed for visible-card collection.

| Upstream | Exact reviewed version | License | What is used | What is excluded |
| --- | --- | --- | --- | --- |
| XClipper | 2.8.2, commit `3f7c6caa2e6f02bf37d140b989cbbdf4485275a5` | PolyForm Noncommercial 1.0.0 | Selected visible-DOM selector, author, timestamp, status-ID, and quoted-card parsing methods, adapted in `extension/lib/parser.ts` | Fast/Auto/Super modes, automatic navigation, private GraphQL interfaces, request/header interception, media download, and account actions |
| WXT | 0.21.4 | MIT | Build-time Manifest V3 scaffolding and packaging | Hosted services and runtime telemetry; none are used |
| Feed Cleaner | Reviewed repository behavior | Repository package metadata said MIT, but no complete root license file was present in the inspected revision | Explainable A–F preview and visible-reason concept only | No source copied |
| XRAI | Reviewed commit `36ec…` | MIT | Behavioral reference for local correction history, novelty, and model-health concepts | YouTube access, unlimited storage, localhost/Ollama coupling, cloud endpoint options, wildcard origin configuration, and LaunchAgent behavior |

XClipper's required notice is preserved in [the extension notices](../../extension/UPSTREAM_NOTICES.md) and [repository notices](../../THIRD_PARTY_NOTICES.md). The product's PolyForm Noncommercial license is compatible with the adapted XClipper code's same license family, but reuse does not grant commercial rights.

The extension dependency lock is committed. Installs suppress lifecycle scripts, and CI builds from exact direct versions. Transitive packages remain reviewable in `extension/pnpm-lock.yaml`; this evidence reduces drift but does not prove that every dependency is vulnerability-free.
