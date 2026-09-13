# Gate 2 Private Package Boundary

The private production-MVP package is recording-only. It contains the local validator, SQLite store, analyzer, report/export code, Apple Vision helper source, and a deterministic projection of the frozen v1 schema set.

The packaged `session.schema.json` is mechanically narrowed to `synthetic_recording` and `user_supplied_recording`, both with `origin: null`. This restriction does not change the repository's immutable Gate 1 schema. It prevents the reserved-origin synthetic browser capability, test markers, harness script, fixture tree, and synthetic manifest from entering a production candidate.

The production extension proposal remains an unexecuted static inspection artifact and is not packaged. The runnable browser harness remains test-only and non-distributable outside this package. There is no live-origin permission, browser binary, remote code, network/model API, native messaging, localhost service, telemetry, signing, notarization, or release claim.
