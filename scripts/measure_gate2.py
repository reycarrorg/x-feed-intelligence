#!/usr/bin/env python3
"""Measure Gate 2 local synthetic resource behavior without retaining media."""

from __future__ import annotations

import argparse
import json
import platform
import resource
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xfi.analysis import analyze_posts
from xfi.recording import ingest
from xfi.store import Store
from xfi.validation import load_and_validate_envelope


def summary(samples: list[float]) -> dict:
    return {"sample_count": len(samples), "mean": round(statistics.fmean(samples), 6), "max": round(max(samples), 6)}


def command_value(command: list[str]) -> str | None:
    try:
        return subprocess.run(command, check=True, capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def measure() -> dict:
    envelope = load_and_validate_envelope((ROOT / "fixtures/synthetic/v1/dom-session.json").read_bytes(), ROOT / "schemas/v1")
    idle = []
    for _ in range(10):
        cpu_start, wall_start = time.process_time(), time.perf_counter()
        time.sleep(0.05)
        idle.append((time.process_time() - cpu_start) / (time.perf_counter() - wall_start) * 100)
    core_wall, core_cpu = [], []
    tracemalloc.start()
    with tempfile.TemporaryDirectory() as temporary:
        for index in range(20):
            wall_start, cpu_start = time.perf_counter(), time.process_time()
            with Store(Path(temporary) / f"core-{index}.sqlite") as store:
                store.import_envelope(envelope)
                analyze_posts(store.list_posts(envelope["session"]["session_id"]))
            core_wall.append((time.perf_counter() - wall_start) * 1000)
            core_cpu.append((time.process_time() - cpu_start) * 1000)
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    native: dict = {"status": "PLATFORM_UNAVAILABLE", "browser_vm": None, "recording_ocr": None}
    if sys.platform == "darwin":
        recorder = ROOT / "build/native/xfi-recording-helper"
        vm = ROOT / "build/native/xfi-harness-vm"
        subprocess.run([str(ROOT / "scripts/build_recording_helper.sh"), str(recorder.parent)], check=True, capture_output=True)
        subprocess.run([str(ROOT / "scripts/build_harness_vm.sh"), str(vm.parent)], check=True, capture_output=True)
        browser_wall = []
        for _ in range(10):
            started = time.perf_counter()
            subprocess.run([str(vm), str(ROOT / "harness/synthetic/synthetic-harness.js")], check=True, capture_output=True)
            browser_wall.append((time.perf_counter() - started) * 1000)
        recording_wall = []
        with tempfile.TemporaryDirectory() as temporary:
            movie = Path(temporary) / "synthetic.mov"
            subprocess.run([str(recorder), "generate-synthetic", str(movie)], check=True, capture_output=True)
            for _ in range(3):
                started = time.perf_counter()
                ingest(movie, (0, 0, 1280, 720), helper=recorder, synthetic=True)
                recording_wall.append((time.perf_counter() - started) * 1000)
        native = {"status": "MEASURED", "browser_vm_wall_ms": summary(browser_wall), "recording_ocr_wall_ms": summary(recording_wall), "recording_frames_per_run": 5, "recording_worker_count": 1, "child_max_rss": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss, "max_rss_unit": "bytes"}
    return {
        "measurement_version": "gate2-resource-v1",
        "hardware_runtime": {"os": platform.platform(), "machine": platform.machine(), "processor": command_value(["sysctl", "-n", "machdep.cpu.brand_string"]) if sys.platform == "darwin" else platform.processor(), "physical_memory_bytes": int(command_value(["sysctl", "-n", "hw.memsize"]) or 0) if sys.platform == "darwin" else None, "python": platform.python_version(), "sqlite": sqlite3.sqlite_version},
        "fixture": {"dom_observations": len(envelope["observations"]), "core_iterations": 20},
        "idle_cpu_percent": summary(idle),
        "core_wall_ms": summary(core_wall),
        "core_cpu_ms": summary(core_cpu),
        "core_python_peak_bytes": peak,
        "process_max_rss": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "process_max_rss_unit": "bytes" if sys.platform == "darwin" else "KiB",
        "native": native,
        "limits": {"idle_mean_cpu_percent_max": 2.0, "recording_worker_count_max": 1, "candidate_count_max": 250},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = measure()
    if result["idle_cpu_percent"]["mean"] >= 2.0:
        raise SystemExit("idle CPU target exceeded")
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")
    return 0


if __name__ == "__main__": raise SystemExit(main())
