"""Dependency-free command-line interface for explicit local operations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .analysis import aggregate_authors, analyze_posts, build_model_handoff
from .canonical import pretty_bytes
from .errors import XFIError
from .render import atomic_write, private_json, private_markdown, sanitize
from .store import Store
from .validation import load_and_validate_envelope


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_envelope(path: Path) -> dict:
    return load_and_validate_envelope(path.read_bytes(), repository_root() / "schemas" / "v1")


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
                result = {"status": "PRIVATE_REPORT_CREATED", "path": str(args.output.resolve())}
        elif args.command == "sanitize":
            clean = sanitize(json.loads(args.source.read_text(encoding="utf-8")))
            atomic_write(args.output, pretty_bytes(clean))
            result = {"status": "SANITIZED_EXPORT_CREATED", "path": str(args.output.resolve()), "content_digest": clean["content_digest"]}
        else:
            with Store(args.database) as store:
                packet = build_model_handoff(store.list_posts(args.session), args.format)
            atomic_write(args.output, pretty_bytes(packet))
            result = {"status": "CAPABILITY_FREE_HANDOFF_CREATED", "path": str(args.output.resolve())}
        print(json.dumps(result, sort_keys=True))
        return 0
    except (XFIError, OSError, ValueError, KeyError, TypeError) as error:
        code = getattr(error, "code", "INVALID_LOCAL_INPUT")
        print(json.dumps({"status": "ERROR", "code": code}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(run())
