-- Luau CodeBench T02 starter.
-- Implement the required API from TASK.md.

export type ItemDefinition = {
    maxStack: number,
}

local InventoryService = {}
InventoryService.__index = InventoryService

function InventoryService.new(definitions: {[string]: ItemDefinition}, maxSlots: number)
    -- TODO: implement
    error("TODO")
end

function InventoryService:AddItem(itemId: string, amount: number): boolean
    -- TODO: implement
    return false
end

function InventoryService:RemoveItem(itemId: string, amount: number): boolean
    -- TODO: implement
    return false
end

function InventoryService:GetItemCount(itemId: string): number
    -- TODO: implement
    return 0
end

function InventoryService:GetUsedSlots(): number
    -- TODO: implement
    return 0
end

function InventoryService:GetMaxSlots(): number
    -- TODO: implement
    return 0
end

function InventoryService:HasItem(itemId: string, amount: number?): boolean
    -- TODO: implement
    return false
end

function InventoryService:Clear()
    -- TODO: implement
end

return InventoryService
