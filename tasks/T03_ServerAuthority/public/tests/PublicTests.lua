-- Public structural tests. Runtime security cases live in the hidden evaluator.

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local ServerScriptService = game:GetService("ServerScriptService")

assert(ReplicatedStorage.Remotes:FindFirstChild("AbilityRequest"))
local AbilityConfig = require(ReplicatedStorage.CodeBench.AbilityConfig)
local CombatService = require(ServerScriptService.CodeBench.CombatService)

assert(AbilityConfig.Slash.baseDamage == 20)
assert(AbilityConfig.Slash.range == 10)
assert(AbilityConfig.Slash.cooldown == 0.5)
assert(type(CombatService.new) == "function")
assert(type(CombatService.Start) == "function")
assert(type(CombatService.Stop) == "function")
assert(type(CombatService.HandleAbilityRequest) == "function")

print("T03 public tests passed")
