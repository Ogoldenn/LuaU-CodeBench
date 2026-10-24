# Private evaluator setup

The public repository intentionally excludes hidden tests. The maintainer's evaluator bundle is supplied separately.

1. Extract the private evaluator bundle into the repository root. It should create:

```text
private-evaluator/
└── tasks/
    ├── T01_Cooldown/HiddenTests.lua
    ├── T02_Inventory/HiddenTests.lua
    └── T03_ServerAuthority/HiddenTests.lua
```

2. Ensure `.env` contains:

```dotenv
LUAUBENCH_PRIVATE_TESTS_DIR=private-evaluator/tasks
```

3. Confirm `private-evaluator/` is ignored:

```powershell
git check-ignore private-evaluator/tasks/T01_Cooldown/HiddenTests.lua
```

The runner refuses to begin a scored run if the private test for that task is missing. It does this before the first model API call, avoiding accidental API spend on an incomplete evaluator setup.

Do not put the private evaluator bundle in the public GitHub repository, a public release, or the model-facing workspace. For OpenCode/shell-capable agents, run in a disposable VM/container that cannot access the private evaluator path.
