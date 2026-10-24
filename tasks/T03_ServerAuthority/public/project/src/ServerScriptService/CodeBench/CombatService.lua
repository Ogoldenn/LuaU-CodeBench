-- Luau CodeBench T03 starter.
-- Preserve the public API and implement server-authoritative validation.

local CombatService = {}
CombatService.__index = CombatService

function CombatService.new(config)
    -- TODO: implement
    error("TODO")
end

function CombatService:HandleAbilityRequest(player, abilityId, target, clientDamage)
    -- TODO: implement
    return false
end

function CombatService:Start()
    -- TODO: connect the RemoteEvent to HandleAbilityRequest
end

function CombatService:Stop()
    -- TODO: disconnect any connections
end

return CombatService
