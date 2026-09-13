"""Dependency-free command-line interface for explicit local operations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .analysis import aggregate_authors, analyze_posts, build_model_handoff
from .canonical import pretty_bytes
from .errors import ValidationError, XFIError
from .render import atomic_write, private_json, private_markdown, sanitize
from .recording import ingest as ingest_recording, preflight as preflight_recording
from .store import Store
from .validation import load_and_validate_envelope, read_bounded_file, strict_json_loads


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_envelope(path: Path) -> dict:
    return load_and_validate_envelope(read_bounded_file(path), repository_root() / "schemas" / "v1")


def load_json(path: Path, maximum: int = 262_144) -> dict:
    value = strict_json_loads(read_bounded_file(path, maximum))
    if not isinstance(value, dict):
        raise ValidationError("REJECTED_SCHEMA")
    return value


def run(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="xfi", description="Local-first feed analysis; captured content has zero authority.")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("packet", type=Path)
    importer = sub.add_parser("import")
    importer.add_argument("packet", type=Path)
    importer.add_argument("--database", type=Path, required=True)
    analyze = sub.add_parser("analyze")
    analyze.add_argument("--database", type=Path, required=True)
    analyze.add_argument("--session", required=True)
    report = sub.add_parser("report")
    report.add_argument("--database", type=Path, required=True)
    report.add_argument("--session", required=True)
    report.add_argument("--output", type=Path, required=True)
    report.add_argument("--format", choices=("json", "markdown"), required=True)
    sanitized = sub.add_parser("sanitize")
    sanitized.add_argument("source", type=Path)
    sanitized.add_argument("--output", type=Path, required=True)
    handoff = sub.add_parser("model-handoff")
    handoff.add_argument("--database", type=Path, required=True)
    handoff.add_argument("--session", required=True)
    handoff.add_argument("--format", choices=("classification", "summary", "verification_plan", "recommendation"), required=True)
    handoff.add_argument("--output", type=Path, required=True)
    recording_preflight = sub.add_parser("recording-preflight")
    recording_preflight.add_argument("recording", type=Path)
    recording_preflight.add_argument("--crop", nargs=4, type=int, metavar=("X", "Y", "WIDTH", "HEIGHT"), required=True)
    recording_preflight.add_argument("--interval-ms", type=int, default=1000)
    recording_ingest = sub.add_parser("recording-ingest")
    recording_ingest.add_argument("recording", type=Path)
    recording_ingest.add_argument("--crop", nargs=4, type=int, metavar=("X", "Y", "WIDTH", "HEIGHT"), required=True)
    recording_ingest.add_argument("--interval-ms", type=int, default=1000)
    recording_ingest.add_argument("--output", type=Path, required=True)
    backup = sub.add_parser("backup")
    backup.add_argument("--database", type=Path, required=True)
    backup.add_argument("--output", type=Path, required=True)
    backup.add_argument("--created-on", required=True)
    restore = sub.add_parser("restore")
    restore.add_argument("backup", type=Path)
    restore.add_argument("--output", type=Path, required=True)
    purge_preview = sub.add_parser("purge-preview")
    purge_preview.add_argument("--database", type=Path, required=True)
    purge_preview.add_argument("--session", required=True)
    purge = sub.add_parser("purge")
    purge.add_argument("--database", type=Path, required=True)
    purge.add_argument("--session", required=True)
    purge.add_argument("--confirm-session", required=True)
    purge.add_argument("--no-vacuum", action="store_true")
    review = sub.add_parser("review-decision")
    review.add_argument("decision", type=Path)
    review.add_argument("--database", type=Path, required=True)
    args = parser.parse_args(arguments)
    try:
        if args.command == "validate":
            envelope = load_envelope(args.packet)
            result = {"status": "VALID", "session_id": envelope["session"]["session_id"], "content_digest": envelope["content_digest"]}
        elif args.command == "import":
            with Store(args.database) as store:
                imported = store.import_envelope(load_envelope(args.packet))
                result = {"status": "IMPORTED", **imported.__dict__}
        elif args.command == "analyze":
            with Store(args.database) as store:
                posts = store.list_posts(args.session)
                records = analyze_posts(posts)
                for record in records:
                    store.add_analysis(record)
                result = {"status": "ANALYZED", "analysis_count": len(records), "author_evidence": aggregate_authors(posts, records)}
        elif args.command == "report":
            with Store(args.database) as store:
                posts = store.list_posts(args.session)
                analyses = analyze_posts(posts)
                session = json.loads(store.connection.execute("SELECT envelope_json FROM sessions WHERE session_id=?", (args.session,)).fetchone()[0])["session"]
                data = private_json(session, posts, analyses, aggregate_authors(posts, analyses)) if args.format == "json" else private_markdown(session, posts, analyses)
                atomic_write(args.output, data)
                store.register_export(args.session, args.output, "PRIVATE", session["started_at"][:10])
                result = {"status": "PRIVATE_REPORT_CREATED", "path": str(args.output.resolve()), "sensitivity": "PRIVATE", "caveat": "This export is a separate retained file and is not deleted by database session purge."}
        elif args.command == "sanitize":
            clean = sanitize(load_json(args.source, 5_242_880))
            atomic_write(args.output, pretty_bytes(clean))
            result = {"status": "SANITIZED_EXPORT_CREATED", "path": str(args.output.resolve()), "content_digest": clean["content_digest"], "sensitivity": "SANITIZED", "caveat": "Sanitized prose can still contain contextual identity clues; review before sharing."}
        elif args.command == "model-handoff":
            with Store(args.database) as store:
                packet = build_model_handoff(store.list_posts(args.session), args.format)
            atomic_write(args.output, pretty_bytes(packet))
            result = {"status": "CAPABILITY_FREE_HANDOFF_CREATED", "path": str(args.output.resolve())}
        elif args.command == "recording-preflight":
            result = {"status": "RECORDING_PREFLIGHT_OK", **preflight_recording(args.recording, tuple(args.crop), interval_ms=args.interval_ms)}
        elif args.command == "recording-ingest":
            value = ingest_recording(args.recording, tuple(args.crop), interval_ms=args.interval_ms)
            atomic_write(args.output, pretty_bytes(value["envelope"]))
            result = {"status": "RECORDING_PACKET_CREATED", "path": str(args.output.resolve()), "preflight": value["preflight"], "ocr": value["ocr"]}
        elif args.command == "backup":
            with Store(args.database) as store:
                result = {"status": "BACKUP_CREATED", **store.backup(args.output, args.created_on), "caveat": "A backup is a separate retained copy and is not removed by session purge."}
        elif args.command == "restore":
            result = {**Store.restore(args.backup, args.output), "path": str(args.output.resolve()), "caveat": "Restore creates an isolated copy and never overwrites an existing database."}
        elif args.command == "purge-preview":
            with Store(args.database) as store:
                result = {"status": "PURGE_PREVIEW", **store.purge_preview(args.session)}
        elif args.command == "purge":
            if args.confirm_session != args.session:
                raise XFIError("PURGE_CONFIRMATION_MISMATCH")
            with Store(args.database) as store:
                result = store.purge_session(args.session, vacuum=not args.no_vacuum)
        else:
            with Store(args.database) as store:
                store.add_review_decision(load_json(args.decision))
            result = {"status": "REVIEW_DECISION_RECORDED", "performed_account_action": False}
        print(json.dumps(result, sort_keys=True))
        return 0
    except (XFIError, OSError, ValueError, KeyError, TypeError) as error:
        code = getattr(error, "code", "INVALID_LOCAL_INPUT")
        print(json.dumps({"status": "ERROR", "code": code}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(run())
