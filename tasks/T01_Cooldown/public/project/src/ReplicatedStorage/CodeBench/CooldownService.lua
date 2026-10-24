-- Luau CodeBench T01 starter.
-- Implement the required API from TASK.md.

export type Clock = () -> number

local CooldownService = {}
CooldownService.__index = CooldownService

export type Service = {
    Start: (self: Service, key: string, duration: number) -> boolean,
    IsOnCooldown: (self: Service, key: string) -> boolean,
    GetRemaining: (self: Service, key: string) -> number,
    Clear: (self: Service, key: string) -> (),
    ClearAll: (self: Service) -> (),
}

function CooldownService.new(clockFn: Clock?): Service
    -- TODO: implement
    error("TODO")
end

function CooldownService:Start(key: string, duration: number): boolean
    -- TODO: implement
    return false
end

function CooldownService:IsOnCooldown(key: string): boolean
    -- TODO: implement
    return false
end

function CooldownService:GetRemaining(key: string): number
    -- TODO: implement
    return 0
end

function CooldownService:Clear(key: string)
    -- TODO: implement
end

function CooldownService:ClearAll()
    -- TODO: implement
end

return CooldownService
