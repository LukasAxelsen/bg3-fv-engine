--[[
  execute.lua — VALOR action-sequence executor (BG3 Script Extender, server context)
  Runs scripted actions with pre/post snapshots and JSONL combat logging.
]]

VALOR = VALOR or {}
VALOR.Execute = VALOR.Execute or {}

--- Optional buffer for floating text / custom oracle hooks (filled by listeners you register elsewhere).
VALOR.Execute._engine_messages = VALOR.Execute._engine_messages or {}

function VALOR.Execute.PushEngineMessage(text)
  table.insert(VALOR.Execute._engine_messages, { t = Ext.Timer and Ext.Timer.ClockTime and Ext.Timer.ClockTime() or "", text = tostring(text) })
  -- Keep bounded
  while #VALOR.Execute._engine_messages > 200 do
    table.remove(VALOR.Execute._engine_messages, 1)
  end
end

function VALOR.Execute._flush_engine_messages()
  local out = VALOR.Execute._engine_messages
  VALOR.Execute._engine_messages = {}
  return out
end

function VALOR.Execute._log_path()
  local root = (VALOR_CONFIG and VALOR_CONFIG.logs_dir) or "VALOR_Logs"
  return root .. "/combat_log.json"
end

function VALOR.Execute._append_jsonl(record)
  local path = VALOR.Execute._log_path()
  local line = Ext.Json.Stringify(record) .. "\n"
  local prev = Ext.IO.LoadFile(path) or ""
  Ext.IO.SaveFile(path, prev .. line)
end

--- Capture HP, conditions (best-effort), position, AC for JSON-safe output.
function VALOR.Execute.Snapshot(entity_id)
  local snap = {
    entity = entity_id,
    hp = nil,
    max_hp = nil,
    ac = nil,
    position = nil,
    conditions = {},
  }

  pcall(function()
    local okHp, hp = pcall(Osi.GetHitpoints, entity_id)
    if okHp then
      snap.hp = hp
    end
    local okMax, mx = pcall(Osi.GetMaxHitpoints, entity_id)
    if okMax then
      snap.max_hp = mx
    end
    local okPos, x, y, z = pcall(Osi.GetPosition, entity_id)
    if okPos and x then
      snap.position = { x = x, y = y, z = z }
    end
  end)

  pcall(function()
    local e = Ext.Entity.Get(entity_id)
    if not e then
      return
    end
    -- AC / derived stats
    local stats = e.BaseStats or e.Stats or e.CharacterStats
    if stats then
      snap.ac = stats.AC or stats.ArmorClass or stats.ArmourClass
    end
    local health = e.Health
    if health then
      snap.hp = snap.hp or health.Hp or health.CurrentHP or health.CurrentHp
      snap.max_hp = snap.max_hp or health.MaxHp or health.MaxHP
    end
    local sc = e.StatusContainer or e.Statuses
    if sc and sc.Statuses then
      for _, st in pairs(sc.Statuses) do
        if type(st) == "table" and st.StatusId then
          table.insert(snap.conditions, { id = st.StatusId, stacks = st.StackCount or 1 })
        end
      end
    end
  end)

  return snap
end

--- Dispatch a single action to Osiris / helpers.
function VALOR.Execute.RunAction(action)
  if type(action) ~= "table" or not action.type then
    return false, "invalid action"
  end
  local t = action.type

  if t == "apply_status" then
    local ok, err = pcall(Osi.ApplyStatus, action.target, action.status, action.duration or -1.0, action.force or 1, action.source or action.target)
    return ok, err
  elseif t == "remove_status" then
    local ok, err = pcall(Osi.RemoveStatus, action.target, action.status, action.cause or "")
    return ok, err
  elseif t == "attack" then
    local ok, err = pcall(Osi.Attack, action.attacker, action.target, action.always_hit or 0)
    return ok, err
  elseif t == "use_spell" then
    -- Spell casting surface varies; common pattern is story-specific. Try generic spell roll if exposed.
    if Osi.UseSpell then
      return pcall(Osi.UseSpell, action.caster, action.spell, action.target)
    end
    return false, "Osi.UseSpell not available in this build"
  elseif t == "teleport_position" then
    local ok, err = pcall(
      Osi.TeleportToPosition,
      action.entity,
      action.x,
      action.y,
      action.z,
      action.event or "",
      action.teleport_linked or 0,
      action.teleport_party_followers or 0,
      action.teleport_summons or 0,
      action.leave_combat or 0,
      action.snap_to_ground or 1
    )
    return ok, err
  elseif t == "set_hitpoints" then
    return pcall(Osi.SetHitpoints, action.entity, action.hp, action.heal_types or "")
  elseif t == "enter_combat" then
    return pcall(Osi.EnterCombat, action.source, action.target)
  elseif t == "custom_osi" then
    local name = action.name
    local fn = name and Osi[name]
    if not fn then
      return false, "unknown Osi symbol: " .. tostring(name)
    end
    local u = table.unpack or unpack
    return pcall(fn, u(action.args or {}))
  elseif t == "lua" then
    if type(action.fn) ~= "function" then
      return false, "action.fn must be a function"
    end
    return pcall(action.fn, action)
  end

  return false, "unsupported action.type: " .. tostring(t)
end

--- Shallow-recursive assertion: every key in `expected` must match `actual` (numbers with epsilon).
function VALOR.Execute.CheckAssertion(expected, actual)
  if expected == nil then
    return true, nil
  end
  if type(expected) ~= "table" or type(actual) ~= "table" then
    return expected == actual, "type mismatch"
  end
  for k, ev in pairs(expected) do
    local av = actual[k]
    if type(ev) == "table" and type(av) == "table" then
      local ok, why = VALOR.Execute.CheckAssertion(ev, av)
      if not ok then
        return false, k .. "." .. (why or "mismatch")
      end
    elseif type(ev) == "number" and type(av) == "number" then
      local eps = (VALOR_CONFIG and VALOR_CONFIG.assertion_epsilon) or 0.01
      if math.abs(ev - av) > eps then
        return false, tostring(k)
      end
    else
      if ev ~= av then
        return false, tostring(k)
      end
    end
  end
  return true, nil
end

function VALOR.Execute._snapshot_targets(action)
  local ids = {}
  local function add(id)
    if id and id ~= "" then
      table.insert(ids, id)
    end
  end
  if action.target then
    add(action.target)
  end
  if action.attacker then
    add(action.attacker)
  end
  if action.caster then
    add(action.caster)
  end
  if action.entity then
    add(action.entity)
  end
  if action.source then
    add(action.source)
  end
  if action.snapshot_entities then
    for _, e in ipairs(action.snapshot_entities) do
      add(e)
    end
  end
  -- Deduplicate
  local seen = {}
  local out = {}
  for _, id in ipairs(ids) do
    if not seen[id] then
      seen[id] = true
      table.insert(out, id)
    end
  end
  return out
end

function VALOR.Execute._map_snapshots(entity_list)
  local m = {}
  for _, id in ipairs(entity_list) do
    m[id] = VALOR.Execute.Snapshot(id)
  end
  return m
end

--[[
  VALOR.Execute(script_data)

  script_data:
    actions — array of action tables (see RunAction)
    expected_states — optional array aligned with actions; each entry is a map entity_guid -> expected snapshot fragment
    resolve_ms — ms to wait after each action (default from VALOR_CONFIG.action_resolve_ms or 500)

  Completion is asynchronous (uses Ext.Timer.WaitFor between steps).
]]
function VALOR.Execute(script_data)
  script_data = script_data or {}
  local actions = script_data.actions or {}
  local expected_states = script_data.expected_states or {}
  local resolve_ms = script_data.resolve_ms or (VALOR_CONFIG and VALOR_CONFIG.action_resolve_ms) or 500
  local n = #actions
  local step = 1

  local function finish()
    if VALOR.Log then
      VALOR.Log("INFO", string.format("Execute: finished %d action(s)", n))
    end
  end

  local function run_step()
    if step > n then
      finish()
      return
    end

    local action = actions[step]
    local targets = VALOR.Execute._snapshot_targets(action)
    local pre_state = VALOR.Execute._map_snapshots(targets)

    local okRun, runErr = VALOR.Execute.RunAction(action)
    if not okRun and VALOR.Log then
      VALOR.Log("WARN", "RunAction failed at step " .. tostring(step) .. ": " .. tostring(runErr))
    end

    Ext.Timer.WaitFor(resolve_ms, function()
      local post_state = VALOR.Execute._map_snapshots(targets)
      local expected = expected_states[step]
      local assertions_passed = true
      if expected and type(expected) == "table" then
        for entityGuid, fragment in pairs(expected) do
          local actual = post_state[entityGuid]
          local pass, key = VALOR.Execute.CheckAssertion(fragment, actual or {})
          if not pass then
            assertions_passed = false
            if VALOR.Log then
              VALOR.Log("WARN", string.format("Assertion failed step %d entity %s (%s)", step, tostring(entityGuid), tostring(key)))
            end
          end
        end
      end

      local entry = {
        step_index = step,
        action = action,
        pre_state = pre_state,
        post_state = post_state,
        assertions_passed = assertions_passed,
        engine_messages = VALOR.Execute._flush_engine_messages(),
        run_ok = okRun,
        run_error = okRun and nil or tostring(runErr),
      }
      VALOR.Execute._append_jsonl(entry)

      step = step + 1
      run_step()
    end)
  end

  if VALOR.Log then
    VALOR.Log("INFO", "Execute: starting " .. tostring(n) .. " action(s)")
  end
  run_step()
end
