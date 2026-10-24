# T01 Runner — beginner guide

Think of the benchmark as a small exam runner:

1. Python creates a fresh copy of the public task.
2. The model receives the same system prompt and task description.
3. It uses the fixed tools to read and edit files and run public tests.
4. When the model finishes, the runner freezes that workspace.
5. The evaluator runs hidden tests from a separate local private bundle.
6. The runner saves the transcript and result JSON.

## Install and configure

- Install Python 3.11+.
- Install the official Luau CLI and ensure `luau` and optionally `luau-analyze` are on PATH.
- Copy `.env.example` to `.env` and fill in your provider URL, API key and model ID.
- Install the private evaluator bundle locally; see `PRIVATE_EVALUATOR.md`.

## Start

```powershell
python tools/luaubench.py doctor
python tools/luaubench.py menu
```

## What tools can the model use?

```text
list_files
read_file
search_files
write_file
run_public_tests
run_static_checks
finish
```

The model doesn't get direct access to the hidden tests through the runner tools.

## Run artifacts

```text
runs/T01_Cooldown/<provider-label>/<run-id>/
├── run.json
├── transcript.jsonl
├── result.json
└── workspace/
```

`transcript.jsonl` contains the assistant messages and tool calls. `result.json` contains scoring and telemetry. These local artifacts are ignored by Git.
