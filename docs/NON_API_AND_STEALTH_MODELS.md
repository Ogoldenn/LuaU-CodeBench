# Agent/harness track and stealth models

Some models are available only through a coding environment such as OpenCode. They can still be benchmarked, but those results belong to a separate **agent/harness track**.

For example, OpenCode can launch a non-interactive run with a selected model and JSON output. This measures the combination of model + OpenCode prompt + tools + agent loop, not the model in isolation.

## Safety and hidden-test isolation

Never run a shell-capable agent with access to the private evaluator path. Use a disposable VM/container or Windows Sandbox containing only the model-facing workspace. Keep hidden tests and scoring code outside that environment. Disable web search/fetch where feasible, and record OpenCode version, model ID, agent config, permissions, command and transcript.

## Separate result tables

- Direct model track: common Luau CodeBench runner/tool interface.
- Agent/harness track: e.g. OpenCode + Big Pickle.

Do not combine the scores without an explicit study of the different harnesses.
