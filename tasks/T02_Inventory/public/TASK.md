# T02 — Inventory Service

Implement a reusable Luau `InventoryService` for stackable items.

## Required API

```lua
InventoryService.new(definitions, maxSlots)
InventoryService:AddItem(itemId, amount)
InventoryService:RemoveItem(itemId, amount)
InventoryService:GetItemCount(itemId)
InventoryService:GetUsedSlots()
InventoryService:GetMaxSlots()
InventoryService:HasItem(itemId, amount?)
InventoryService:Clear()
```

`definitions` is a table keyed by item ID. Each definition contains a positive integer `maxStack`.

## Behavioral requirements

1. Unknown item IDs are rejected.
2. Amounts must be positive integers.
3. Items stack up to their `maxStack`.
4. `AddItem` may fill multiple slots when needed.
5. `maxSlots` limits the total number of occupied item slots.
6. Adding an item that cannot fully fit must not partially add items.
7. `RemoveItem` cannot reduce a count below zero.
8. Removing more than the current count fails without changing the inventory.
9. `GetUsedSlots()` returns the number of occupied stacks, not total item count.
10. `HasItem(itemId)` is true only when count is greater than zero.
11. The service must keep its own state and must not mutate the supplied `definitions` table.
12. Do not use Roblox-specific global state for inventory data.

The hidden evaluator tests stacking boundaries, atomic failure, invalid input, slot exhaustion, and state isolation.
