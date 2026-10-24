# Luau CodeBench v0.3.0 specification

## Scope

The direct-model track measures a model's ability to implement a repository-level Luau task with a fixed tool loop.

## Controlled variables

- exact system prompt and task text;
- pristine public starter project;
- tool schemas and runner version;
- task/evaluator versions;
- time and tool-call limits;
- model settings where the API supports them;
- a hidden evaluator kept outside the model workspace.

## Provider configuration

The runner uses one OpenAI-compatible Chat Completions interface. The base URL, key, auth header/prefix and requested model ID are configured through `.env` or command-line overrides; no provider-specific preset is required.

## Run lifecycle

```text
clean public fixture
  -> model workspace
  -> model edits and public tests
  -> freeze workspace
  -> hidden evaluator in separate temp directory
  -> static analysis
  -> result.json
```

## Hidden test protection

Hidden tests live in the maintainer's private evaluator bundle and are copied into a temporary evaluator directory only after the model stops. They must never be copied into the model workspace or committed publicly.

## Repeated runs

Run each model/task pair at least three times for headline results. Report each run and median; don't treat one lucky run as definitive.

## Provenance

Save requested model ID, response model IDs where supplied, provider label, timestamp, runner/task versions, tools, token usage and duration. This records routing metadata, not cryptographic proof of the underlying weights.
