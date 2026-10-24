local ReplicatedStorage = game:GetService("ReplicatedStorage")
local ServerScriptService = game:GetService("ServerScriptService")

local AbilityConfig = require(ReplicatedStorage.CodeBench.AbilityConfig)
local CombatService = require(ServerScriptService.CodeBench.CombatService)

local service = CombatService.new({
    abilities = AbilityConfig,
    remote = ReplicatedStorage.Remotes.AbilityRequest,
})

service:Start()
