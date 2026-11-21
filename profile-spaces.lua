-- profile-spaces.lua — one Mission Control space per Chrome profile.
--
-- How it works:
--  * Watches for new Chrome windows whose title contains a known profile
--    name (Chrome puts "<Profile>" in every window title).
--  * Lazily creates a macOS space for that profile (16/display OS cap —
--    extra profiles just stay on the main desktop) and moves the window.
--  * Ctrl+Alt+P opens a chooser of all profiles; picking one jumps to its
--    space, opening a window if none exists.
--
-- Space order in Mission Control is not nameable via public API — the
-- project spaces appear as Desktop 2..N. The chooser is the fast way in.
--
-- Config: none needed. The map is built from Chrome's Local State at load,
-- so every registered profile is covered automatically. Chrome must have
-- been started once for the names to appear.

local M = {}

local function loadMap()
  local path = os.getenv("HOME") .. "/Library/Application Support/Google/Chrome/Local State"
  local st = hs.json.read(path)
  local out = {}
  if st and st.profile and st.profile.info_cache then
    for dir, info in pairs(st.profile.info_cache) do
      -- strip the parenthesised suffix so title matching stays specific
      local name = (info.name or dir):gsub("%s*%b()$", "")
      -- prefer longer names first so "Claude Personal 2" wins over "Claude Personal"
      table.insert(out, { name = name, dir = dir, len = #name })
    end
  end
  table.sort(out, function(a, b) return a.len > b.len end)
  return out
end

M.map = loadMap()

M.followNewWindows = false   -- true = also switch your view when a window gets parked
M.maxSpaces = 14             -- OS cap is 16/display; leave headroom

local assigned = {}          -- profile name -> space id

local function screens()
  return hs.screen.allScreens()
end

local function allSpaceIds()
  local out = {}
  for _, scr in ipairs(screens()) do
    for _, s in ipairs(hs.spaces.spacesForScreen(scr) or {}) do out[s] = scr end
  end
  return out
end

local function spaceExists(id)
  return allSpaceIds()[id] ~= nil
end

local function newSpaceId(scr)
  local before = allSpaceIds()
  if not hs.spaces.addSpaceToScreen(scr, true) then return nil end
  for _ = 1, 40 do
    hs.timer.usleep(100000)
    for s in pairs(allSpaceIds()) do
      if not before[s] then return s end
    end
  end
  return nil
end

-- `scr` is only used the first time a profile needs a space; after that all
-- its windows converge on the same space regardless of display.
local function ensureSpace(name, scr)
  if assigned[name] and spaceExists(assigned[name]) then return assigned[name] end
  scr = scr or hs.screen.mainScreen()
  if #(hs.spaces.spacesForScreen(scr) or {}) >= M.maxSpaces then return nil end
  local id = newSpaceId(scr)
  if id then assigned[name] = id end
  return id
end

local function matchProfile(title)
  for _, p in ipairs(M.map) do
    if title:find("(" .. p.name .. ")", 1, true) or title:find(" - " .. p.name .. " ", 1, true) then
      return p
    end
  end
  -- fallback: profile name anywhere in title
  for _, p in ipairs(M.map) do
    if title:find(p.name, 1, true) then return p end
  end
end

-- Park a window on its profile's space. Returns the space id or nil.
function M.park(win)
  if not win then return nil end
  local app = win:application()
  if not app or app:bundleID() ~= "com.google.Chrome" then return nil end
  local title = win:title() or ""
  local p = matchProfile(title)
  if not p then return nil end
  local sid = ensureSpace(p.name, win:screen())
  if not sid then return nil end
  hs.spaces.moveWindowToSpace(win:id(), sid)
  if M.followNewWindows then hs.spaces.gotoSpace(sid) end
  return sid
end

-- Jump to a profile: focus its window on its space, or open a new one.
function M.jump(name)
  local p
  for _, e in ipairs(M.map) do if e.name == name then p = e end end
  if not p then hs.alert("no profile named " .. name); return end
  local app = hs.application.get("com.google.Chrome")
  if app then
    for _, w in ipairs(app:allWindows()) do
      local t = w:title() or ""
      if t:find(p.name, 1, true) then
        local sid = ensureSpace(p.name, w:screen())
        if sid then
          hs.spaces.moveWindowToSpace(w:id(), sid)
          hs.spaces.gotoSpace(sid)
        end
        w:focus()
        return
      end
    end
  end
  local sid = ensureSpace(p.name)
  hs.execute(string.format('open -na "Google Chrome" --args --profile-directory="%s"', p.dir))
  hs.timer.doAfter(2.5, function()
    local a = hs.application.get("com.google.Chrome")
    if a then
      for _, w in ipairs(a:allWindows()) do
        if (w:title() or ""):find(p.name, 1, true) then
          if sid then hs.spaces.moveWindowToSpace(w:id(), sid); hs.spaces.gotoSpace(sid) end
          w:focus(); return
        end
      end
    end
  end)
end

-- Chooser hotkey.
M.chooser = nil
function M.showChooser()
  if not M.chooser then
    M.chooser = hs.chooser.new(function(sel)
      if sel then M.jump(sel.prof) end
    end)
    M.chooser:choices(function()
      local out = {}
      for _, p in ipairs(M.map) do
        table.insert(out, { text = p.name, subText = p.dir, prof = p.name })
      end
      return out
    end)
    M.chooser:searchSubText(true)
  end
  M.chooser:show()
end

hs.hotkey.bind({ "ctrl", "alt" }, "p", function() M.showChooser() end)

-- Watch new Chrome windows.
M.wf = hs.window.filter.new("Google Chrome")
M.wf:subscribe(hs.window.filter.windowCreated, function(win)
  hs.timer.doAfter(1.0, function() if win then M.park(win) end end)
end)

return M
