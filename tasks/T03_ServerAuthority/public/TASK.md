# T03 — Server-Authoritative Ability Request

Implement a server-side ability request handler that safely processes a client request.

The starter project contains a `CombatService` module and a RemoteEvent named `AbilityRequest`.

## Gameplay contract

An ability request contains:

```text
abilityId: string
clientTarget: Instance?
clientDamage: number?
```

The client is untrusted.

The server owns the authoritative values:

- valid ability IDs;
- base damage for each ability;
- maximum attack range;
- cooldowns;
- whether the target is a valid humanoid target.

## Requirements

1. The client cannot choose the final damage amount.
2. The server must reject unknown abilities.
3. The server must reject non-humanoid targets.
4. The server must reject the attacking character as a target.
5. The server must reject targets outside the configured range.
6. The server must enforce an ability cooldown per player and ability ID.
7. A rejected request must not mutate target health.
8. The same player's cooldown must not block another player's request.
9. The handler must not trust a client-supplied range/damage/cooldown value.
10. Preserve the public `CombatService` API supplied in the starter.

The hidden evaluator fires real RemoteEvent requests from simulated clients and checks server-side outcomes.
