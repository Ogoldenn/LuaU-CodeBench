# Scoring — T01 v0.1.0

Primary score (100 points):

- 60 points — hidden functional tests
- 20 points — task-specific invariants
- 10 points — public regression tests
- 10 points — static analysis

Telemetry reported alongside score:

- hidden/public tests passed;
- syntax/type analysis status;
- API/runtime errors;
- duration and provider retry time;
- tool calls and test runs;
- input/output token usage if returned by the gateway;
- changed files and line counts;
- human intervention flag.

A run must not receive an official score if the private evaluator is unavailable or the run stopped because of a provider/runner infrastructure failure.
