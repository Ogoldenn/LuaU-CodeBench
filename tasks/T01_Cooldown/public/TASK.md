# T01 — Cooldown Manager

Implement a reusable Luau `CooldownService` module for per-key cooldowns.

## Required API

The module must export these functions:

```lua
CooldownService.new(clockFn?)
CooldownService:Start(key, duration)
CooldownService:IsOnCooldown(key)
CooldownService:GetRemaining(key)
CooldownService:Clear(key)
CooldownService:ClearAll()
```

`clockFn` is optional. When provided, it returns the current time in seconds and should be used by the service instead of directly reading the wall clock. This makes the service deterministic under tests.

## Behavioral requirements

1. A successful `Start(key, duration)` begins a cooldown for `key`.
2. `Start` must not restart an active cooldown for the same key.
3. `IsOnCooldown` is false before the cooldown starts and after it expires.
4. `GetRemaining` returns a non-negative number of seconds remaining, or `0` when no cooldown is active.
5. `Clear(key)` removes only the specified key.
6. `ClearAll()` removes all cooldowns.
7. Different keys are independent.
8. A duration of `0` or less must not create a persistent cooldown.
9. The implementation must not create a new background task/thread for every cooldown.
10. Do not modify files outside the supplied CodeBench module and its tests unless necessary.

## Acceptance criteria

The public tests must pass. The hidden evaluator will additionally test boundary times, multiple keys, clearing behavior, and repeated starts.
