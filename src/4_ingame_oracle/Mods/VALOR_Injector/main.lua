--[[
  main.lua — VALOR in-game oracle entry (BG3 Script Extender, server context)

  Wire-up: from `ScriptExtender/Lua/BootstrapServer.lua` call:
    Ext.Require("main")   -- if this file is on the Lua require path, or use your mod’s relative path.

  Deposits logs under VALOR_CONFIG.logs_dir (default VALOR_Logs/) and polls VALOR_CONFIG.scripts_dir
  for .lua tests. Directory listing uses (in order) LuaFileSystem `lfs`, VALOR_queue.txt, or `dir /b` on Windows.
]]

VALOR = VALOR or {}

--- User-tunable paths and behaviour (absolute paths recommended for bridge tooling).
if type(VALOR_CONFIG) ~= "table" then
  VALOR_CONFIG = {}
end
local _cfg_defaults = {
  scripts_dir = "VALOR_Scripts",
  logs_dir = "VALOR_Logs",
  poll_interval_ms = 2000,
  debug = false,
  --- Milliseconds to wait after each Osi call inside VALOR.Execute (engine tick alignment).
  action_resolve_ms = 500,
  --- Numeric tolerance for VALOR.Execute.CheckAssertion.
  assertion_epsilon = 0.01,
}
for k, v in pairs(_cfg_defaults) do
  if VALOR_CONFIG[k] == nil then
    VALOR_CONFIG[k] = v
  end
end

VALOR._processed = VALOR._processed or {}

--- Load sibling modules (sandbox first; execute depends only on VALOR + Osi/Ext).
Ext.Require("sandbox")
Ext.Require("execute")

local function main_log_path()
  return VALOR_CONFIG.logs_dir .. "/main.log"
end

local function append_main_log(line)
  local path = main_log_path()
  local prev = Ext.IO.LoadFile(path) or ""
  Ext.IO.SaveFile(path, prev .. line .. "\n")
end

--- @param level string
--- @param msg string
function VALOR.Log(level, msg)
  local stamp = (Ext.Timer and Ext.Timer.ClockTime and Ext.Timer.ClockTime()) or ""
  local line = string.format("[%s] [%s] %s", stamp, level, msg)
  append_main_log(line)
  if VALOR_CONFIG.debug or level == "ERROR" or level == "WARN" then
    pcall(function()
      if Ext.Utils and Ext.Utils.Print then
        Ext.Utils.Print(line)
      elseif _P then
        _P(line)
      end
    end)
  end
end

local function simple_hash(s)
  local h = 5381
  for i = 1, #s do
    h = (h * 33 + s:byte(i)) % 4294967296
  end
  return tostring(h)
end

--- Collect .lua paths under scripts_dir (best-effort; no native directory iterator in Ext.IO).
local function list_lua_script_paths(scripts_dir)
  local paths = {}
  local seen = {}

  local function add(p)
    if not seen[p] then
      seen[p] = true
      paths[#paths + 1] = p
    end
  end

  local lfsOk, lfs = pcall(require, "lfs")
  if lfsOk and lfs and lfs.dir then
    pcall(function()
      for f in lfs.dir(scripts_dir) do
        if f ~= "." and f ~= ".." and f:match("%.lua$") then
          add(scripts_dir .. "/" .. f)
        end
      end
    end)
  end

  local manifest = Ext.IO.LoadFile(scripts_dir .. "/VALOR_queue.txt")
  if manifest then
    for line in manifest:gmatch("[^\r\n]+") do
      line = line:match("^%s*(.-)%s*$")
      if line ~= "" and not line:match("^#") then
        add(scripts_dir .. "/" .. line)
      end
    end
  end

  if #paths == 0 then
    pcall(function()
      local popen = io.popen
      if not popen then
        return
      end
      local winDir = scripts_dir:gsub("/", "\\")
      local p = popen('dir /b "' .. winDir .. '" 2>nul')
      if p then
        for line in p:lines() do
          if line:match("%.lua$") then
            add(scripts_dir .. "/" .. line)
          end
        end
        p:close()
      end
    end)
  end

  return paths
end

local function run_test_script(path)
  local body = Ext.IO.LoadFile(path)
  if not body then
    VALOR.Log("WARN", "Could not read script: " .. path)
    return
  end

  local digest = simple_hash(body)
  if VALOR._processed[path] == digest then
    if VALOR_CONFIG.debug then
      VALOR.Log("DEBUG", "Skip unchanged script: " .. path)
    end
    return
  end

  VALOR.Log("INFO", "Loading test script: " .. path)

  local chunk, loadErr = load(body, "@" .. path, "t", _G)
  if not chunk then
    VALOR.Log("ERROR", "load() failed for " .. path .. ": " .. tostring(loadErr))
    return
  end

  local ok, result = pcall(chunk)
  if not ok then
    VALOR.Log("ERROR", "pcall failed for " .. path .. ": " .. tostring(result))
    return
  end

  VALOR._processed[path] = digest
  VALOR.Log("INFO", "Script OK: " .. path)

  if type(result) == "table" and type(result.actions) == "table" then
    VALOR.Log("INFO", "Dispatching to VALOR.Execute (" .. tostring(#result.actions) .. " actions)")
    local exOk, exErr = pcall(VALOR.Execute, result)
    if not exOk then
      VALOR.Log("ERROR", "VALOR.Execute failed: " .. tostring(exErr))
    end
  elseif VALOR_CONFIG.debug then
    VALOR.Log("DEBUG", "Script returned no `actions` table; skipping VALOR.Execute")
  end
end

local function poll_once()
  local dir = VALOR_CONFIG.scripts_dir
  local paths = list_lua_script_paths(dir)
  if VALOR_CONFIG.debug then
    VALOR.Log("DEBUG", string.format("Poll: %d candidate script(s) in %s", #paths, dir))
  end
  for _, p in ipairs(paths) do
    local pollOk, err = pcall(run_test_script, p)
    if not pollOk then
      VALOR.Log("ERROR", "poll run_test_script error: " .. tostring(err))
    end
  end
end

local function schedule_poll_loop()
  local interval = VALOR_CONFIG.poll_interval_ms or 2000
  Ext.Timer.WaitFor(interval, function()
    local ok, err = pcall(poll_once)
    if not ok then
      VALOR.Log("ERROR", "poll_once crashed: " .. tostring(err))
    end
    schedule_poll_loop()
  end)
end

Ext.Events.SessionLoaded:Subscribe(function()
  VALOR._processed = {}
  VALOR.Log("INFO", "VALOR injector: session loaded; logs -> " .. main_log_path())
  VALOR.Log("INFO", "Watching scripts_dir=" .. tostring(VALOR_CONFIG.scripts_dir))
  schedule_poll_loop()
end)
