# Configuration and model menu

## One `.env` for every provider

Copy `.env.example` to `.env` and configure:

```dotenv
LUAUBENCH_PROVIDER=my-gateway
LUAUBENCH_BASE_URL=https://provider.example/v1
LUAUBENCH_API_KEY=your-api-key
LUAUBENCH_MODEL=model-id
LUAUBENCH_AUTH_HEADER=Authorization
LUAUBENCH_AUTH_PREFIX=Bearer
LUAUBENCH_HTTP_BACKEND=auto
LUAUBENCH_PRIVATE_TESTS_DIR=private-evaluator/tasks
```

`LUAUBENCH_PROVIDER` is a label used for result folders and metadata. It does not select a special adapter. All connection settings are universal.

The API key is stored as plaintext in `.env`; keep the file private. `.gitignore` excludes it.

## Interactive CLI

```powershell
python tools/luaubench.py menu
```

Menu actions:

1. Configure API settings in `.env`.
2. Call `GET <base-url>/models` and choose a model, or type the exact ID if listing is unavailable.
3. Check basic completion and tool calling.
4. Run T01.

## Scriptable commands

```powershell
python tools/luaubench.py list-models
python tools/luaubench.py select-model
python tools/luaubench.py check-api
python tools/luaubench.py run-model T01_Cooldown
```

CLI flags override `.env`; shell environment variables take precedence over values loaded from `.env`.

Base URL should usually end in `/v1`, not `/v1/chat/completions`.
