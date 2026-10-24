# Model run protocol

1. Start with a pristine workspace.
2. Use the repository system prompt and public task prompt verbatim.
3. Configure endpoint, credentials, and model in `.env`.
4. Keep tool definitions, time budget and tool-call budget fixed across the models being compared.
5. Disable browser/web access in the direct-model track.
6. Do not manually patch the workspace.
7. Freeze the workspace when the model finishes or reaches a limit.
8. Run hidden tests only in the external evaluator process.
9. Save transcript and result JSON.
10. Mark runs with API, gateway or evaluator failures as invalid/infrastructure failures rather than model scores.
