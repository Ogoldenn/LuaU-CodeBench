local ReplicatedStorage = game:GetService("ReplicatedStorage")
local InventoryService = require(ReplicatedStorage.CodeBench.InventoryService)

local definitions = {
    Potion = { maxStack = 10 },
    Sword = { maxStack = 1 },
}

local inv = InventoryService.new(definitions, 3)
assert(inv:GetMaxSlots() == 3)
assert(inv:GetUsedSlots() == 0)
assert(inv:AddItem("Potion", 7))
assert(inv:GetItemCount("Potion") == 7)
assert(inv:GetUsedSlots() == 1)
assert(inv:AddItem("Potion", 5))
assert(inv:GetItemCount("Potion") == 12)
assert(inv:GetUsedSlots() == 2)
assert(inv:HasItem("Potion"))
assert(inv:HasItem("Potion", 12))
assert(not inv:HasItem("Potion", 13))
assert(inv:RemoveItem("Potion", 2))
assert(inv:GetItemCount("Potion") == 10)
assert(inv:RemoveItem("Potion", 10))
assert(inv:GetItemCount("Potion") == 0)
assert(inv:GetUsedSlots() == 0)
assert(not inv:AddItem("Unknown", 1))
assert(not inv:AddItem("Sword", 0))
print("T02 public tests passed")
