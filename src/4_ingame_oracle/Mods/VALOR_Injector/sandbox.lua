--[[
  sandbox.lua — VALOR test harness (BG3 Script Extender, server context)
  Builds a reproducible combat sandbox: spawn dummies, reset state, combat setup, cleanup.
]]

VALOR = VALOR or {}
VALOR.Sandbox = VALOR.Sandbox or {}

--- Tracks every entity created for this test run (GUID strings).
VALOR.Sandbox._entities = VALOR.Sandbox._entities or {}

--- Last resolved spawn anchor / origin (updated by Setup).
VALOR.Sandbox._origin = VALOR.Sandbox._origin or { x = 0, y = 0, z = 0 }

local function log_sandbox(level, msg)
  if VALOR.Log then
    VALOR.Log(level, "[Sandbox] " .. msg)
  end
end

--- Merge spawn origin from config: prefers explicit x,y,z, else anchor entity, else first party member.
--- @param config table|nil
local function resolve_origin(config)
  config = config or {}
  if config.origin_x and config.origin_y and config.origin_z then
    VALOR.Sandbox._origin.x = config.origin_x
    VALOR.Sandbox._origin.y = config.origin_y
    VALOR.Sandbox._origin.z = config.origin_z
    return
  end
  if config.anchor_entity then
    local ok, x, y, z = pcall(Osi.GetPosition, config.anchor_entity)
    if ok and x then
      VALOR.Sandbox._origin.x = x
      VALOR.Sandbox._origin.y = y
      VALOR.Sandbox._origin.z = z
      return
    end
  end
  -- Fallback: try to read a player character position (first user).
  local ok, ch = pcall(Osi.GetCurrentCharacter, 0)
  if ok and ch then
    local ok2, x, y, z = pcall(Osi.GetPosition, ch)
    if ok2 and x then
      VALOR.Sandbox._origin.x = x
      VALOR.Sandbox._origin.y = y
      VALOR.Sandbox._origin.z = z
    end
  end
end

--- Read numeric ability score from stats table or entity (best-effort).
local function apply_ability_overrides(entity, abilities)
  if not abilities or not entity then
    return
  end
  -- Many builds expose stats through Ext.Entity; exact component layout varies by patch.
  pcall(function()
    local e = Ext.Entity.Get(entity)
    if not e then
      return
    end
    local bs = e.BaseStats or e.Stats or e.CharacterStats
    if not bs then
      return
    end
    for name, value in pairs(abilities) do
      local key = name:sub(1, 1):upper() .. name:sub(2):lower()
      if bs[key] ~= nil then
        bs[key] = value
      elseif bs[name] ~= nil then
        bs[name] = value
      end
    end
  end)
end

--- Apply resistance / tag hints via statuses (engine-specific; extend as needed).
local function apply_resistance_hints(entity, resistances)
  if not resistances or not entity then
    return
  end
  for resType, _ in pairs(resistances) do
    -- Placeholder mapping: real tests should pass concrete status IDs understood by the story.
    local statusId = type(resType) == "string" and resType or nil
    if statusId then
      pcall(Osi.ApplyStatus, entity, statusId, -1.0, 1, entity)
    end
  end
end

--[[
  VALOR.Sandbox.Setup(config)

  config fields (all optional):
    origin_x, origin_y, origin_z — spawn grid origin
    anchor_entity — GUID to copy position from
    clear_entities_first — if true, run Cleanup() first
]]
function VALOR.Sandbox.Setup(config)
  config = config or {}
  if config.clear_entities_first then
    VALOR.Sandbox.Cleanup()
  end
  VALOR.Sandbox._entities = {}
  resolve_origin(config)
  log_sandbox("INFO", string.format("Origin set to (%.2f, %.2f, %.2f)", VALOR.Sandbox._origin.x, VALOR.Sandbox._origin.y, VALOR.Sandbox._origin.z))
  return true
end

--[[
  VALOR.Sandbox.SpawnDummy(stats)

  stats fields (optional unless noted):
    template — CHARACTERROOT template GUID (required for CreateAt)
    offset_x, offset_y, offset_z — relative to sandbox origin (defaults 0,0,1)
    hp, max_hp — passed to SetHitpoints / percentage helpers
    ac — stored only if entity stats cannot be edited (best-effort via boosts is test-specific)
    abilities — table like { str = 14, dex = 12, ... }
    resistances — table of status IDs or keys used as ApplyStatus hooks
    temporary — CreateAt temporary flag (default 1)
    play_spawn — CreateAt playSpawn (default 0)
]]
function VALOR.Sandbox.SpawnDummy(stats)
  stats = stats or {}
  local template = stats.template
  if not template or template == "" then
    log_sandbox("ERROR", "SpawnDummy: missing stats.template (CHARACTERROOT GUID)")
    return nil
  end

  local ox = (stats.offset_x or 0) + VALOR.Sandbox._origin.x
  local oy = (stats.offset_y or 0) + VALOR.Sandbox._origin.y
  local oz = (stats.offset_z or 1) + VALOR.Sandbox._origin.z
  local temporary = stats.temporary ~= nil and stats.temporary or 1
  local playSpawn = stats.play_spawn or 0
  local spawnEvent = stats.spawn_finish_event or ""

  local ok, created = pcall(Osi.CreateAt, template, ox, oy, oz, temporary, playSpawn, spawnEvent)
  if not ok or not created then
    log_sandbox("ERROR", "SpawnDummy: Osi.CreateAt failed: " .. tostring(created))
    return nil
  end

  table.insert(VALOR.Sandbox._entities, created)

  if stats.hp then
    pcall(Osi.SetHitpoints, created, stats.hp)
  elseif stats.max_hp then
    pcall(Osi.SetHitpoints, created, stats.max_hp)
  end

  apply_ability_overrides(created, stats.abilities)
  apply_resistance_hints(created, stats.resistances)

  -- AC is often derived; callers may assert via snapshots after applying homebrew boosts elsewhere.
  if stats.ac and VALOR_CONFIG and VALOR_CONFIG.debug then
    log_sandbox("DEBUG", "SpawnDummy: requested AC=" .. tostring(stats.ac) .. " (apply via boosts/statuses in your story if needed)")
  end

  return created
end

--- Strip harmful statuses and restore HP to max where queryable; refresh cooldowns; nudge action resources.
function VALOR.Sandbox.ResetState()
  for _, entity in ipairs(VALOR.Sandbox._entities) do
    pcall(Osi.RemoveHarmfulStatuses, entity)
    pcall(Osi.RemoveStatusesWithType, entity, "SG_Debuff", "")
    pcall(Osi.ResetCooldowns, entity)

    local okMax, maxHp = pcall(Osi.GetMaxHitpoints, entity)
    if okMax and maxHp then
      pcall(Osi.SetHitpoints, entity, maxHp)
    end

    -- Best-effort action economy top-up (resource names differ by class; guarded by pcall).
    local resources = { "ActionResource", "BonusActionResource", "MovementResource" }
    for _, res in ipairs(resources) do
      pcall(Osi.PartyIncreaseActionResourceValue, entity, res, 99)
    end
  end
end

--[[
  VALOR.Sandbox.SetupCombat(entities)

  Seeds combat by chaining EnterCombat along the provided GUID list.
  Deterministic full initiative ordering usually requires story / mod-specific hooks; this gives a stable entry.
]]
function VALOR.Sandbox.SetupCombat(entities)
  if not entities or #entities < 2 then
    log_sandbox("WARN", "SetupCombat: need at least two entity GUIDs")
    return false
  end
  for i = 1, #entities - 1 do
    local a, b = entities[i], entities[i + 1]
    pcall(Osi.EnterCombat, a, b)
  end
  return true
end

--- Remove tracked test entities (best-effort).
function VALOR.Sandbox.Cleanup()
  for _, entity in ipairs(VALOR.Sandbox._entities) do
    pcall(Osi.CombatKillFor, entity)
    pcall(Osi.RemoveSummons, entity, 1)
  end
  VALOR.Sandbox._entities = {}
end
