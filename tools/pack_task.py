#!/usr/bin/env python3
"""Create a zip containing only model-facing files for a task."""
from __future__ import annotations
import argparse
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

parser = argparse.ArgumentParser()
parser.add_argument("task")
parser.add_argument("output_zip")
args = parser.parse_args()

task_dir = ROOT / "tasks" / args.task
public_dir = task_dir / "public"
if not public_dir.exists():
    raise SystemExit(f"Unknown task: {args.task}")

with tempfile.TemporaryDirectory() as td:
    staging = Path(td) / args.task
    shutil.copytree(public_dir, staging)
    shutil.copy2(ROOT / "SYSTEM_PROMPT.md", staging / "SYSTEM_PROMPT.md")
    base = str(Path(args.output_zip).with_suffix(""))
    archive = shutil.make_archive(base, "zip", staging)
    final = Path(args.output_zip)
    if archive != str(final):
        Path(archive).replace(final)
    print(final)
