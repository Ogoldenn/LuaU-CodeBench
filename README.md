# Luau CodeBench v0.3.0

A reproducible benchmark for evaluating AI coding models on Luau tasks.

## What this project does

Luau CodeBench gives a model a fixed task, a clean starter project, a fixed system prompt, and a small tool interface. It records the model/tool transcript, runtime and token usage, then evaluates the resulting project.

The direct-model track uses any OpenAI-compatible Chat Completions API with tool calling. Provider-specific code is intentionally avoided: configure one URL, one API key, and one model ID.

## Quick start (Windows PowerShell)

1. Install Python 3.11+ and the official Luau CLI (`luau.exe` and optionally `luau-analyze.exe`).
2. Copy `.env.example` to `.env`.
3. Set `LUAUBENCH_BASE_URL`, `LUAUBENCH_API_KEY`, and `LUAUBENCH_MODEL` in `.env`.
4. Install the private evaluator pack locally. It must not be committed to the public repository. See [Private evaluator setup](docs/PRIVATE_EVALUATOR.md).
5. Run:

```powershell
python tools/luaubench.py doctor
python tools/luaubench.py menu
```

Once configured, scriptable commands are also available:

```powershell
python tools/luaubench.py list-models
python tools/luaubench.py check-api
python tools/luaubench.py run-model T01_Cooldown
```

The model catalog endpoint (`GET /models`) is optional. If your gateway does not expose it, type the exact model ID manually.

## Configuration

All connection settings live in the ignored `.env` file. A typical base URL ends in `/v1`; the runner appends `/chat/completions` and `/models`.

```dotenv
LUAUBENCH_PROVIDER=my-gateway
LUAUBENCH_BASE_URL=https://provider.example/v1
LUAUBENCH_API_KEY=your-key
LUAUBENCH_MODEL=model-id
LUAUBENCH_AUTH_HEADER=Authorization
LUAUBENCH_AUTH_PREFIX=Bearer
LUAUBENCH_HTTP_BACKEND=auto
LUAUBENCH_PRIVATE_TESTS_DIR=private-evaluator/tasks
```

Never commit `.env`. Do not paste API keys into issues, logs, or pull requests.

## Tasks and evaluator

Public task material lives in `tasks/<TASK>/public/`. Official hidden tests are distributed separately to the benchmark maintainer and live locally under `private-evaluator/tasks/<TASK>/HiddenTests.lua`. Hidden tests are not included in this public repository to reduce test leakage.

Current scope: T01 is the calibrated standalone Luau task. T02 and T03 are fixtures/prototypes; do not treat them as fully validated runtime benchmarks yet.

## Benchmark tracks

- **Direct model track**: API model + the fixed Luau CodeBench tool loop.
- **Agent/harness track**: a coding environment such as OpenCode + a model. Keep results separate because tool availability, prompts and agent loops differ.

## Output

A local run creates `runs/<TASK>/<provider-label>/<run-id>/` containing `run.json`, `transcript.jsonl`, `result.json` and the model workspace. Run outputs are ignored by Git by default.

## Reproducibility

Record benchmark version, task version, requested model ID, provider label, returned model IDs where available, temperature, tool calls, token usage, duration and evaluator outcomes. API gateways may route aliases internally; an API response cannot independently prove the underlying model weights.
