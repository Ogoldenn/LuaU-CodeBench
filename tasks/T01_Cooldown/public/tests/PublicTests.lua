-- Public tests for T01. Standalone Luau CLI; no Roblox globals.
local CooldownService = require("../project/src/ReplicatedStorage/CodeBench/CooldownService")

local function test(name: string, fn: () -> ())
    local ok, err = pcall(fn)
    if not ok then
        error("[FAIL] " .. name .. ": " .. tostring(err), 0)
    end
    print("[PASS] " .. name)
end

test("starts and reports remaining", function()
    local now = 100
    local service = CooldownService.new(function() return now end)
    assert(service:IsOnCooldown("A") == false)
    assert(service:GetRemaining("A") == 0)
    assert(service:Start("A", 5) == true)
    assert(service:IsOnCooldown("A") == true)
    assert(service:GetRemaining("A") == 5)
end)

test("active start does not restart", function()
    local now = 100
    local service = CooldownService.new(function() return now end)
    assert(service:Start("A", 5) == true)
    assert(service:Start("A", 10) == false)
    assert(service:GetRemaining("A") == 5)
end)

test("expires at boundary", function()
    local now = 100
    local service = CooldownService.new(function() return now end)
    service:Start("A", 5)
    now = 104
    assert(service:GetRemaining("A") == 1)
    assert(service:IsOnCooldown("A") == true)
    now = 105
    assert(service:GetRemaining("A") == 0)
    assert(service:IsOnCooldown("A") == false)
end)

test("different keys are independent", function()
    local now = 100
    local service = CooldownService.new(function() return now end)
    assert(service:Start("A", 2) == true)
    assert(service:Start("B", 10) == true)
    now = 102
    assert(service:IsOnCooldown("A") == false)
    assert(service:IsOnCooldown("B") == true)
end)

test("clear only affects one key", function()
    local service = CooldownService.new(function() return 100 end)
    service:Start("A", 2)
    service:Start("B", 10)
    service:Clear("A")
    assert(service:IsOnCooldown("A") == false)
    assert(service:IsOnCooldown("B") == true)
end)

test("clear all removes everything", function()
    local service = CooldownService.new(function() return 100 end)
    service:Start("A", 2)
    service:Start("B", 10)
    service:ClearAll()
    assert(service:GetRemaining("A") == 0)
    assert(service:GetRemaining("B") == 0)
end)

test("non-positive durations do not persist", function()
    local service = CooldownService.new(function() return 100 end)
    assert(service:Start("C", 0) == false)
    assert(service:Start("D", -1) == false)
    assert(service:GetRemaining("C") == 0)
    assert(service:GetRemaining("D") == 0)
end)

print("T01 public tests passed")
