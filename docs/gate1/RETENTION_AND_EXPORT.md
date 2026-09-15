# Local Retention, Purge, Backup, and Export Contract

## Data classes and defaults

| Data | Default location and lifetime | User control | Purge behavior |
| --- | --- | --- | --- |
| Original recording | Original user-selected path; never copied by default | User owns and deletes it outside the product | Product forgets the path/reference; it does not delete the original unless a later explicit managed-copy feature is separately approved |
| Derived frames and crops | Private job-temporary directory | Diagnostic retention is an explicit opt-in with an expiry | Delete immediately after accepted import or failed/cancelled job; report failures without retaining content in logs |
| Unsaved extension queue | Extension local storage, at most 250 candidates or 30 minutes | Explicit export or discard | Clear on discard/stop; permission revocation asks before clearing an unsaved draft; no background retention after the decision |
| Imported private packet | Local analyzer database; no cloud-synced default path | Retained until explicit session purge | Transactionally delete all session-linked observations, posts without remaining observations, analyses, verification, recommendations, and provenance |
| Private report | User-selected local output | Explicit create and delete | Database purge does not silently delete separately exported files; UI must list known exports and explain this boundary |
| Sanitized export | User-selected local output only | Explicit create and delete | Independent artifact; source purge does not promise deletion of copies, backups, shares, or snapshots |
| Operational logs | Local, content-free, rolling 7 days; maximum 5 MiB | User can clear | Remove files and record no replacement content event |

The product must not choose iCloud, Drive, Dropbox, a network filesystem, remote database, crash reporter, analytics service, or telemetry sink by default. It must warn when a user-selected database or export path is detected on a synchronized/network provider.

## SQLite configuration

At database creation and every writable open, the implementation must verify:

- `PRAGMA foreign_keys=ON`;
- `PRAGMA secure_delete=ON`;
- `PRAGMA journal_mode=WAL` for normal local transactional work;
- a supported application ID, schema version, and migration checksum;
- the database is a product-created file on a local filesystem and is not an arbitrary imported SQLite file.

`secure_delete=ON` overwrites deleted database payload in ordinary pages, but it does not prove erasure from WAL files, free-list history created under a prior setting, OS snapshots, SSD remapping, backup files, synchronized copies, or exports. `VACUUM` rebuilds a database but still cannot promise cryptographic erasure from underlying storage. User-facing language must say “local purge completed under configured SQLite controls” rather than “securely/cryptographically erased.”

## Transactional session purge

`purge-session` is explicit and previews the session ID, observation/post counts, known exports, and backup caveats. On confirmation, it must:

1. close readers and pause writers;
2. begin an immediate transaction;
3. delete session-owned analyses, recommendations, verification, redaction records, provenance, relationships, media descriptors, observations, and session row in referential order or by reviewed cascades;
4. delete canonical posts/authors only when no remaining observation or recommendation references them;
5. commit and run `PRAGMA wal_checkpoint(TRUNCATE)`;
6. when configured and sufficient free disk exists, run `VACUUM`; otherwise report `VACUUM_NOT_RUN` without claiming full page compaction;
7. verify by querying the purged session ID and all prior child IDs; record only counts and result codes;
8. delete derived temporary files and rotate content-free logs.

Any failed transaction rolls back. A failed checkpoint, reference check, temporary-file delete, or configured vacuum produces `PURGE_INCOMPLETE` and exact non-sensitive remediation guidance. Repeating purge without changing the failed condition is not automatic.

## WAL and backup rules

Never copy a live `.sqlite`, `-wal`, or `-shm` file as a backup. Create consistent backups through SQLite's online backup API after a checkpoint or from a closed database, write to a new user-selected local path, verify `integrity_check`, record schema/application versions and SHA-256, and never overwrite an existing backup without explicit confirmation.

Purging the live database does not alter older backups. The product maintains a local backup inventory only for backups it created and clearly lists those paths during purge. It cannot discover every Time Machine snapshot, filesystem snapshot, manually copied database, cloud-provider version, or previously shared export.

Restoring a backup is a separate explicit action. Restore must validate the application ID, supported schema version matching current migrations, integrity, finite backup size (maximum 104,857,600 bytes / 100 MiB), and destination; it must never accept an arbitrary database as a shortcut around import validation.

## Export behavior

Private report and sanitized export are separate commands with distinct filenames and a visible sensitivity label. Export is never automatic and never uploads or shares. Filenames are generated from a session-scoped identifier and date, never captured text. Existing files are not overwritten silently.

Sanitized export follows the allowlist and redaction behavior in [Analysis Contracts](ANALYSIS_CONTRACTS.md). It always includes a redaction manifest, source schema version, sanitizer version, generation time reduced to date, deterministic content digest, and the warning that prose may contain contextual identity clues. Export fails before writing the final file; a temporary file is written in the destination directory, flushed, validated, then atomically renamed.

## Gate 2 tests required

Gate 2 must prove foreign-key cleanup, rollback on injected failure, WAL truncation, behavior with open readers, secure-delete setting on reopen, vacuum success and insufficient-space failure, orphan prevention, backup integrity, restored-backup isolation, temp cleanup, known-export listing, no secret echo, and sanitizer golden outputs. Tests use only synthetic databases in temporary local directories.
