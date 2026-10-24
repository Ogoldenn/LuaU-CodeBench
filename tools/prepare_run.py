#!/usr/bin/env python3
"""Create a pristine model-facing workspace for one Luau CodeBench task.

Usage:
  python tools/prepare_run.py T01_Cooldown /tmp/run-workspace

Hidden evaluator files are never copied.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("task", help="Task directory name, e.g. T01_Cooldown")
    parser.add_argument("output", help="Empty or non-existent output directory")
    args = parser.parse_args()

    task_dir = ROOT / "tasks" / args.task
    public_dir = task_dir / "public"
    output = Path(args.output).resolve()

    if not task_dir.exists():
        raise SystemExit(f"Unknown task: {args.task}")
    if output.exists():
        if any(output.iterdir()):
            raise SystemExit(f"Output directory is not empty: {output}")
    else:
        output.mkdir(parents=True)

    shutil.copytree(public_dir, output, dirs_exist_ok=True)

    manifest = json.loads((task_dir / "task.json").read_text(encoding="utf-8"))
    manifest.pop("hidden", None)
    (output / ".benchmark_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    system_prompt = (ROOT / "SYSTEM_PROMPT.md").read_text(encoding="utf-8")
    (output / "SYSTEM_PROMPT.md").write_text(system_prompt, encoding="utf-8")

    print(f"Prepared model workspace: {output}")
    print("Hidden evaluator files were not copied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
