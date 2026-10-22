"""
MINI BATTLE ROYALE - a turn-based survival game built with Streamlit.

Everything lives in this single file: game rules, enemy AI, rendering (inline
SVG) and the Streamlit interface.  Each player action (move, shoot, reload,
hold) is one "turn" = one second of match time.  After every turn the enemy
bots act and the safe-zone clock advances, so the simulation is consistent and
reliable on Streamlit's rerun model.

Run with:  streamlit run app.py
"""

import html
import math
import random
import time

import streamlit as st

st.set_page_config(page_title="Mini Battle Royale", page_icon="🎯", layout="wide")

# ----------------------------------------------------------------------------
# CONSTANTS
# ----------------------------------------------------------------------------
GRID = 30                  # arena is GRID x GRID cells
CELL = 20                  # pixels per cell in the SVG
SIZE = GRID * CELL
ZC = GRID / 2.0            # centre of the safe zone (in cell units)
DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))

PLAYER_MAX_HP = 100
HEALTH_PACK_HEAL = 25

# Safe zone: radius of each phase, turns before the next shrink, damage per turn
ZONE_RADII = [20.0, 16.0, 12.0, 9.0, 6.0, 3.5]
PHASE_TICKS = [16, 14, 12, 10, 10, 0]
ZONE_DAMAGE = [3, 4, 5, 6, 8, 10]
FINAL_PHASE = len(ZONE_RADII) - 1

SCORE_KILL = 100
SCORE_PHASE = 50
SCORE_PACK = 10
SCORE_WIN = 500

WEAPONS = {
    "Pistol": dict(damage=20, range=9, mag=10, cooldown=1, reserve=20, ammo_box=10,
                   accuracy=0.92, falloff=False, color="#cfd4d8", tag="PI"),
    "Assault Rifle": dict(damage=26, range=13, mag=30, cooldown=1, reserve=30, ammo_box=30,
                          accuracy=0.88, falloff=False, color="#6fa8dc", tag="AR"),
    "Shotgun": dict(damage=70, range=6, mag=6, cooldown=2, reserve=12, ammo_box=6,
                    accuracy=0.95, falloff=True, color="#e69138", tag="SG"),
    "Sniper Rifle": dict(damage=80, range=28, mag=5, cooldown=3, reserve=10, ammo_box=5,
                         accuracy=1.0, falloff=False, color="#b57edc", tag="SR"),
}

STATE_COLORS = {
    "roaming": "#8c3b3b",
    "chasing": "#d9822b",
    "attacking": "#e03a3a",
    "escaping": "#8e44ad",
}


# ----------------------------------------------------------------------------
# SMALL HELPERS
# ----------------------------------------------------------------------------
def in_bounds(x, y):
    return 0 <= x < GRID and 0 <= y < GRID


def zone_dist(x, y):
    """Distance from the centre of cell (x, y) to the centre of the arena."""
    return math.hypot(x + 0.5 - ZC, y + 0.5 - ZC)


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def line_cells(x0, y0, x1, y1):
    """Bresenham line between two cells (inclusive)."""
    cells = []
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    while True:
        cells.append((x0, y0))
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy
    return cells


def has_los(g, a, b):
    """True if no obstacle lies between cells a and b."""
    for c in line_cells(a[0], a[1], b[0], b[1])[1:-1]:
        if c in g["obstacles"]:
            return False
    return True


def log(g, text, kind="info"):
    g["log"].append((g["tick"], text, kind))
    if len(g["log"]) > 80:
        del g["log"][:-80]


def is_free(g, x, y):
    """A cell is free if it is inside the arena, has no obstacle and nobody on it."""
    if not in_bounds(x, y) or (x, y) in g["obstacles"]:
        return False
    p = g["player"]
    if p is not None and p["x"] == x and p["y"] == y:
        return False
    for b in g["bots"]:
        if b["alive"] and b["x"] == x and b["y"] == y:
            return False
    return True


def loot_at(g, x, y):
    for item in g["loot"]:
        if item["x"] == x and item["y"] == y:
            return item
    return None


def find_cell(g, rng, accept, tries=800):
    """Random free cell satisfying accept(x, y); falls back to any free cell."""
    for _ in range(tries):
        x, y = rng.randint(0, GRID - 1), rng.randint(0, GRID - 1)
        if is_free(g, x, y) and accept(x, y):
            return x, y
    for y in range(GRID):
        for x in range(GRID):
            if is_free(g, x, y):
                return x, y
    return None


def max_reserve(name):
    return WEAPONS[name]["mag"] * 6


# ----------------------------------------------------------------------------
# MATCH CREATION
# ----------------------------------------------------------------------------
def generate_obstacles(rng):
    obs = {}
    for _ in range(7):                       # wall segments
        length = rng.randint(3, 6)
        horizontal = rng.random() < 0.5
        x, y = rng.randint(1, GRID - 2), rng.randint(1, GRID - 2)
        for i in range(length):
            cx, cy = (x + i, y) if horizontal else (x, y + i)
            if in_bounds(cx, cy) and (cx, cy) not in obs:
                obs[(cx, cy)] = "wall"
    for kind, count in (("rock", 14), ("tree", 34)):
        placed = 0
        while placed < count:
            c = (rng.randint(0, GRID - 1), rng.randint(0, GRID - 1))
            if c not in obs:
                obs[c] = kind
                placed += 1
    return obs


def new_game(bot_count=8, status="menu"):
    """Create a brand-new match.  Only called on first load, Start and Restart."""
    rng = random.Random(time.time_ns())
    g = {
        "rng": rng,
        "status": status,            # menu / playing / paused / won / lost
        "tick": 0,
        "start_time": time.time() if status == "playing" else None,
        "end_time": None,
        "player": None,
        "bots": [],
        "obstacles": generate_obstacles(rng),
        "loot": [],
        "inv": {"Pistol": {"mag": WEAPONS["Pistol"]["mag"], "reserve": WEAPONS["Pistol"]["reserve"]}},
        "weapon": "Pistol",
        "cd": {"Pistol": 0, "Assault Rifle": 0, "Shotgun": 0, "Sniper Rifle": 0},
        "phase": 0,
        "zone_radius": ZONE_RADII[0],
        "zone_timer": PHASE_TICKS[0],
        "final_ticks": 0,
        "score": 0,
        "kills": 0,
        "damage_dealt": 0,
        "damage_taken": 0,
        "shots": 0,
        "hits": 0,
        "phases_survived": 0,
        "packs": 0,
        "tracers": [],
        "log": [],
        "result": None,
        "killed_by": None,
    }

    # player
    cell = find_cell(g, rng, lambda x, y: 7 <= zone_dist(x, y) <= 12)
    g["player"] = {"x": cell[0], "y": cell[1], "hp": PLAYER_MAX_HP, "max_hp": PLAYER_MAX_HP}
    pp = (cell[0], cell[1])

    # enemy bots
    for i in range(bot_count):
        def accept(x, y):
            if zone_dist(x, y) > 17 or dist((x, y), pp) < 8:
                return False
            return all(dist((x, y), (o["x"], o["y"])) >= 3 for o in g["bots"])
        c = find_cell(g, rng, accept)
        hp = rng.randint(50, 70)
        g["bots"].append({
            "id": i + 1, "x": c[0], "y": c[1], "hp": hp, "max_hp": hp,
            "speed": round(rng.uniform(0.7, 1.1), 2),
            "detect": rng.randint(8, 11),
            "attack_range": rng.randint(4, 7),
            "damage": rng.randint(7, 11),
            "cooldown": rng.randint(2, 3),
            "cd": rng.randint(0, 2),
            "alive": True, "state": "roaming", "alert": 0, "acc": 0.0,
        })

    # loot
    def no_loot(x, y):
        return loot_at(g, x, y) is None and zone_dist(x, y) <= 18

    def add_loot(kind, accept_fn, name=None):
        c = find_cell(g, rng, accept_fn)
        if c is not None:
            g["loot"].append({"x": c[0], "y": c[1], "kind": kind, "name": name})

    add_loot("weapon", lambda x, y: no_loot(x, y) and 3 <= dist((x, y), pp) <= 7, "Assault Rifle")
    add_loot("ammo", lambda x, y: no_loot(x, y) and 2 <= dist((x, y), pp) <= 6)
    add_loot("health", lambda x, y: no_loot(x, y) and 3 <= dist((x, y), pp) <= 8)
    for name in ("Assault Rifle", "Shotgun", "Shotgun", "Sniper Rifle"):
        add_loot("weapon", no_loot, name)
    for _ in range(7):
        add_loot("ammo", no_loot)
    for _ in range(5):
        add_loot("health", no_loot)

    log(g, "Welcome to the arena. Press START GAME to begin." if status == "menu"
        else "Match started. Survive and eliminate every bot!", "info")
    return g


# ----------------------------------------------------------------------------
# COMBAT HELPERS
# ----------------------------------------------------------------------------
def player_hit_chance(spec, d):
    return max(0.45, min(1.0, spec["accuracy"] - 0.35 * d / spec["range"]))


def weapon_damage(spec, d):
    dmg = spec["damage"]
    if spec["falloff"]:                      # shotgun loses power with distance
        span = max(1.0, spec["range"] - 2)
        t = max(0.0, min(1.0, (d - 2) / span))
        dmg = dmg * (1 - 0.55 * t)
    return int(round(dmg))


def choose_target(g, aim_id):
    alive = [b for b in g["bots"] if b["alive"]]
    if not alive:
        return None
    p = g["player"]
    spec = WEAPONS[g["weapon"]]
    pp = (p["x"], p["y"])
    if aim_id != -1:
        for b in alive:
            if b["id"] == aim_id:
                return b
    valid = [b for b in alive
             if dist(pp, (b["x"], b["y"])) <= spec["range"] and has_los(g, pp, (b["x"], b["y"]))]
    pool = valid or alive
    return min(pool, key=lambda b: dist(pp, (b["x"], b["y"])))


def damage_bot(g, b, dmg, by_player=True):
    """Apply damage to a bot; handles elimination, score and loot drops."""
    dealt = min(dmg, b["hp"])
    b["hp"] -= dealt
    b["alert"] = 8
    if by_player:
        g["damage_dealt"] += dealt
    if b["hp"] <= 0:
        b["hp"] = 0
        b["alive"] = False
        b["state"] = "eliminated"
        if by_player:
            g["kills"] += 1
            g["score"] += SCORE_KILL
            log(g, f"Bot #{b['id']} eliminated! +{SCORE_KILL} points", "good")
            if loot_at(g, b["x"], b["y"]) is None:
                roll = g["rng"].random()
                if roll < 0.30:
                    g["loot"].append({"x": b["x"], "y": b["y"], "kind": "health", "name": None})
                elif roll < 0.75:
                    g["loot"].append({"x": b["x"], "y": b["y"], "kind": "ammo", "name": None})
    else:
        pass
    return dealt


def pickup_loot(g):
    p = g["player"]
    item = loot_at(g, p["x"], p["y"])
    if item is None:
        return
    kind = item["kind"]
    if kind == "health":
        if p["hp"] >= p["max_hp"]:
            log(g, "Health is already full - health pack left on the ground.", "info")
            return
        before = p["hp"]
        p["hp"] = min(p["max_hp"], p["hp"] + HEALTH_PACK_HEAL)
        g["score"] += SCORE_PACK
        g["packs"] += 1
        log(g, f"Health pack: +{p['hp'] - before} HP, +{SCORE_PACK} points", "good")
    elif kind == "ammo":
        for w, inv in g["inv"].items():
            inv["reserve"] = min(max_reserve(w), inv["reserve"] + WEAPONS[w]["ammo_box"])
        log(g, "Ammo box collected: reserve ammo added to all your weapons.", "good")
    elif kind == "weapon":
        name = item["name"]
        spec = WEAPONS[name]
        if name in g["inv"]:
            inv = g["inv"][name]
            inv["reserve"] = min(max_reserve(name), inv["reserve"] + spec["reserve"])
            log(g, f"{name} ammo collected.", "good")
        else:
            g["inv"][name] = {"mag": spec["mag"], "reserve": spec["reserve"]}
            log(g, f"Picked up a {name}! Select it in the weapon list.", "good")
    g["loot"].remove(item)


# ----------------------------------------------------------------------------
# ENEMY AI
# ----------------------------------------------------------------------------
def effective_radius(g):
    """Radius bots try to stay inside (anticipates a shrink that is about to happen)."""
    r = g["zone_radius"]
    if g["phase"] < FINAL_PHASE and g["zone_timer"] <= 3:
        r = ZONE_RADII[g["phase"] + 1]
    return r


def bot_move(g, b, mode, safe_r):
    rng = g["rng"]
    p = g["player"]
    pp = (p["x"], p["y"])
    cands = [(b["x"] + dx, b["y"] + dy) for dx, dy in DIRS if is_free(g, b["x"] + dx, b["y"] + dy)]
    if not cands:
        return
    here_z = zone_dist(b["x"], b["y"])
    if mode == "escape":
        cands.sort(key=lambda c: zone_dist(c[0], c[1]))
        choice = cands[0] if zone_dist(*cands[0]) < here_z else rng.choice(cands)
    else:
        safe = [c for c in cands if zone_dist(c[0], c[1]) <= safe_r - 0.5]
        if not safe:
            return
        if mode == "chase":
            safe.sort(key=lambda c: dist(c, pp))
            here_d = dist((b["x"], b["y"]), pp)
            choice = safe[0] if dist(safe[0], pp) < here_d else rng.choice(safe)
        else:  # roam
            if here_z > 0.6 * safe_r and rng.random() < 0.5:
                safe.sort(key=lambda c: zone_dist(c[0], c[1]))
                choice = safe[0]
            else:
                choice = rng.choice(safe)
    b["x"], b["y"] = choice


def bot_turn(g, b):
    rng = g["rng"]
    p = g["player"]
    if b["cd"] > 0:
        b["cd"] -= 1
    if b["alert"] > 0:
        b["alert"] -= 1
    bpos = (b["x"], b["y"])
    ppos = (p["x"], p["y"])
    d = dist(bpos, ppos)
    safe_r = effective_radius(g)
    zd = zone_dist(b["x"], b["y"])
    detect = b["detect"] + (6 if b["alert"] > 0 else 0)

    if zd > safe_r - 0.5:
        b["state"] = "escaping"
    elif d <= b["attack_range"] and has_los(g, bpos, ppos):
        b["state"] = "attacking"
    elif d <= detect:
        b["state"] = "chasing"
    else:
        b["state"] = "roaming"

    if b["state"] == "attacking":
        if b["cd"] <= 0:
            b["cd"] = b["cooldown"]
            g["tracers"].append((b["x"], b["y"], p["x"], p["y"], "#ff6b6b"))
            chance = max(0.2, min(0.8, 0.85 - 0.08 * d))
            if rng.random() < chance:
                dmg = min(b["damage"], p["hp"])
                p["hp"] -= dmg
                g["damage_taken"] += dmg
                log(g, f"Bot #{b['id']} hit you for {dmg} damage!", "bad")
                if p["hp"] <= 0:
                    p["hp"] = 0
                    g["killed_by"] = f"Bot #{b['id']}"
            else:
                log(g, f"Bot #{b['id']} fired and missed.", "info")
        return

    b["acc"] += b["speed"]
    steps = int(b["acc"])
    b["acc"] -= steps
    for _ in range(steps):
        if b["state"] == "escaping":
            bot_move(g, b, "escape", safe_r)
        elif b["state"] == "chasing":
            bot_move(g, b, "chase", safe_r)
        elif rng.random() > 0.3:
            bot_move(g, b, "roam", safe_r)


# ----------------------------------------------------------------------------
# TURN ENGINE
# ----------------------------------------------------------------------------
def zone_damage(g):
    extra = g["final_ticks"] // 6 if g["phase"] == FINAL_PHASE else 0
    return ZONE_DAMAGE[g["phase"]] + extra


def end_turn(g):
    """Everything that happens after a player action: bots act, zone ticks, rules checked."""
    g["tick"] += 1
    p = g["player"]

    for b in g["bots"]:
        if b["alive"] and p["hp"] > 0:
            bot_turn(g, b)

    for w in g["cd"]:
        g["cd"][w] = max(0, g["cd"][w] - 1)

    advanced = False
    if g["phase"] < FINAL_PHASE:
        g["zone_timer"] -= 1
        if g["zone_timer"] <= 0:
            g["phase"] += 1
            g["zone_radius"] = ZONE_RADII[g["phase"]]
            g["zone_timer"] = PHASE_TICKS[g["phase"]]
            advanced = True
            log(g, f"ZONE SHRINK! Phase {g['phase'] + 1}/{len(ZONE_RADII)} - "
                   f"safe radius is now {g['zone_radius']:.1f}.", "warn")
    else:
        g["final_ticks"] += 1

    dmg = zone_damage(g)
    if p["hp"] > 0 and zone_dist(p["x"], p["y"]) > g["zone_radius"]:
        taken = min(dmg, p["hp"])
        p["hp"] -= taken
        g["damage_taken"] += taken
        log(g, f"You are outside the safe zone! -{taken} HP", "bad")
        if p["hp"] <= 0 and g["killed_by"] is None:
            g["killed_by"] = "the storm"
    for b in g["bots"]:
        if b["alive"] and zone_dist(b["x"], b["y"]) > g["zone_radius"]:
            b["hp"] = max(0, b["hp"] - dmg)
            if b["hp"] <= 0:
                b["alive"] = False
                b["state"] = "eliminated"
                log(g, f"Bot #{b['id']} was consumed by the storm.", "info")

    if advanced and p["hp"] > 0:
        g["score"] += SCORE_PHASE
        g["phases_survived"] += 1
        log(g, f"Survived a safe-zone phase: +{SCORE_PHASE} points", "good")

    if p["hp"] <= 0:
        p["hp"] = 0
        g["status"] = "lost"
        g["result"] = "DEFEAT"
        g["end_time"] = time.time()
        log(g, f"You were eliminated by {g['killed_by'] or 'the storm'}.", "bad")
    elif not any(b["alive"] for b in g["bots"]):
        g["status"] = "won"
        g["result"] = "VICTORY"
        g["score"] += SCORE_WIN
        g["end_time"] = time.time()
        log(g, f"LAST SURVIVOR! Match won: +{SCORE_WIN} bonus points", "good")


def begin_action(g):
    g["tracers"] = []


# ----------------------------------------------------------------------------
# CALLBACKS (run before the script reruns, so the page always shows fresh state)
# ----------------------------------------------------------------------------
def G():
    return st.session_state["game"]


def cb_start():
    g = G()
    count = st.session_state.get("bot_count", 8)
    if g["status"] == "menu" and len(g["bots"]) == count:
        g["status"] = "playing"
        g["start_time"] = time.time()
        log(g, "Match started. Survive and eliminate every bot!", "info")
    else:
        st.session_state["game"] = new_game(count, "playing")
    st.session_state["aim_sel"] = -1


def cb_restart():
    st.session_state["game"] = new_game(st.session_state.get("bot_count", 8), "playing")
    st.session_state["aim_sel"] = -1


def cb_pause():
    g = G()
    if g["status"] == "playing":
        g["status"] = "paused"
    elif g["status"] == "paused":
        g["status"] = "playing"


def cb_move(dx, dy):
    g = G()
    if g["status"] != "playing":
        return
    begin_action(g)
    p = g["player"]
    nx, ny = p["x"] + dx, p["y"] + dy
    if not in_bounds(nx, ny):
        log(g, "You cannot leave the arena.", "warn")
        return
    if (nx, ny) in g["obstacles"]:
        log(g, "That way is blocked by cover.", "warn")
        return
    if not is_free(g, nx, ny):
        log(g, "An enemy is standing there.", "warn")
        return
    p["x"], p["y"] = nx, ny
    pickup_loot(g)
    end_turn(g)


def cb_wait():
    g = G()
    if g["status"] != "playing":
        return
    begin_action(g)
    end_turn(g)


def cb_reload():
    g = G()
    if g["status"] != "playing":
        return
    begin_action(g)
    w = g["weapon"]
    inv = g["inv"][w]
    cap = WEAPONS[w]["mag"]
    if inv["mag"] >= cap:
        log(g, f"{w} magazine is already full.", "warn")
        return
    if inv["reserve"] <= 0:
        log(g, f"No reserve ammo for {w}. Find an ammo box!", "warn")
        return
    take = min(cap - inv["mag"], inv["reserve"])
    inv["mag"] += take
    inv["reserve"] -= take
    log(g, f"Reloaded {w}: +{take} rounds.", "info")
    end_turn(g)


def cb_weapon():
    g = G()
    if g["status"] != "playing":
        return
    new = st.session_state.get("weapon_sel")
    if new in g["inv"] and new != g["weapon"]:
        g["weapon"] = new
        log(g, f"Switched to {new}.", "info")


def cb_shoot():
    g = G()
    if g["status"] != "playing":
        return
    begin_action(g)
    rng = g["rng"]
    p = g["player"]
    w = g["weapon"]
    spec = WEAPONS[w]
    inv = g["inv"][w]
    if g["cd"][w] > 0:
        log(g, f"{w} is cooling down ({g['cd'][w]} more turn(s)). Use HOLD to wait.", "warn")
        return
    if inv["mag"] <= 0:
        log(g, f"{w} magazine is empty - reload!", "warn")
        return
    target = choose_target(g, st.session_state.get("aim_sel", -1))
    if target is None:
        log(g, "No enemies left to shoot.", "warn")
        return
    pp = (p["x"], p["y"])
    tp = (target["x"], target["y"])
    d = dist(pp, tp)
    if d > spec["range"]:
        log(g, f"Bot #{target['id']} is out of range ({d:.1f} tiles, {w} reaches {spec['range']}).", "warn")
        return
    if not has_los(g, pp, tp):
        log(g, f"Cover blocks your shot at Bot #{target['id']}. Reposition!", "warn")
        return

    inv["mag"] -= 1
    g["shots"] += 1
    g["cd"][w] = spec["cooldown"]
    g["tracers"].append((p["x"], p["y"], target["x"], target["y"], "#ffe066"))
    if rng.random() < player_hit_chance(spec, d):
        dmg = weapon_damage(spec, d)
        before_alive = target["alive"]
        dealt = damage_bot(g, target, dmg, True)
        g["hits"] += 1
        if before_alive and target["alive"]:
            log(g, f"Hit Bot #{target['id']} with {w}: -{dealt} HP ({target['hp']} left).", "good")
    else:
        log(g, f"Your shot at Bot #{target['id']} missed.", "info")
    end_turn(g)


# ----------------------------------------------------------------------------
# RENDERING
# ----------------------------------------------------------------------------
def e(text):
    return html.escape(str(text))


def md(markup):
    st.markdown(markup, unsafe_allow_html=True)


def px(v):
    return (v + 0.5) * CELL


def hp_color(pct):
    return "#4caf50" if pct > 60 else "#f0ad4e" if pct > 30 else "#e74c3c"


def bar_html(label, value, maximum, color, text):
    pct = 0 if maximum <= 0 else max(0, min(100, 100.0 * value / maximum))
    return (f'<div class="mbr-bar-label"><span>{e(label)}</span><span>{e(text)}</span></div>'
            f'<div class="mbr-bar"><div class="mbr-bar-fill" style="width:{pct:.0f}%;background:{color}"></div></div>')


def render_arena(g, aim_id):
    cx = cy = ZC * CELL
    zr = g["zone_radius"] * CELL
    s = [f'<svg viewBox="0 0 {SIZE} {SIZE}" xmlns="http://www.w3.org/2000/svg" '
         f'style="width:100%;max-width:680px;height:auto;display:block;margin:0 auto;'
         f'border:2px solid #4b5a3a;border-radius:8px;background:#18211a">']
    s.append('<defs><pattern id="mbrgrid" width="20" height="20" patternUnits="userSpaceOnUse">'
             '<path d="M20 0H0V20" fill="none" stroke="#223020" stroke-width="1"/></pattern></defs>')
    s.append(f'<rect width="{SIZE}" height="{SIZE}" fill="url(#mbrgrid)"/>')

    # danger area outside the safe zone
    s.append(f'<path fill-rule="evenodd" fill="rgba(220,50,40,0.28)" '
             f'd="M0 0H{SIZE}V{SIZE}H0Z M{cx - zr:.1f} {cy:.1f}a{zr:.1f} {zr:.1f} 0 1 0 {2 * zr:.1f} 0'
             f'a{zr:.1f} {zr:.1f} 0 1 0 {-2 * zr:.1f} 0Z"/>')
    s.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{zr:.1f}" fill="none" stroke="#ff5544" stroke-width="3"/>')
    if g["phase"] < FINAL_PHASE:
        nr = ZONE_RADII[g["phase"] + 1] * CELL
        s.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{nr:.1f}" fill="none" stroke="#f1c40f" '
                 f'stroke-width="2" stroke-dasharray="8 6" opacity="0.85"/>')

    # obstacles
    for (x, y), kind in g["obstacles"].items():
        X, Y = x * CELL, y * CELL
        if kind == "tree":
            s.append(f'<circle cx="{X + 10}" cy="{Y + 10}" r="8.5" fill="#2e5d2a" stroke="#1b3a19"/>'
                     f'<circle cx="{X + 10}" cy="{Y + 10}" r="4" fill="#3f7a39"/>')
        elif kind == "rock":
            s.append(f'<polygon points="{X + 3},{Y + 15} {X + 5},{Y + 6} {X + 12},{Y + 3} {X + 17},{Y + 9} '
                     f'{X + 16},{Y + 16}" fill="#7b8087" stroke="#4a4e52" stroke-width="1.5"/>')
        else:
            s.append(f'<rect x="{X}" y="{Y}" width="{CELL}" height="{CELL}" fill="#6b5a45" stroke="#3d3226"/>'
                     f'<path d="M{X} {Y + 10}H{X + 20}M{X + 10} {Y}V{Y + 10}M{X + 5} {Y + 10}V{Y + 20}M{X + 15} {Y + 10}V{Y + 20}" '
                     f'stroke="#3d3226" stroke-width="1" fill="none"/>')

    # loot
    for it in g["loot"]:
        X, Y = it["x"] * CELL, it["y"] * CELL
        if it["kind"] == "health":
            s.append(f'<rect x="{X + 3}" y="{Y + 3}" width="14" height="14" rx="3" fill="#f4f4f4" stroke="#c0392b" stroke-width="1.5"/>'
                     f'<path d="M{X + 10} {Y + 6}V{Y + 14}M{X + 6} {Y + 10}H{X + 14}" stroke="#c0392b" stroke-width="3"/>')
        elif it["kind"] == "ammo":
            s.append(f'<rect x="{X + 3}" y="{Y + 4}" width="14" height="12" rx="2" fill="#b8901f" stroke="#6e5410"/>'
                     f'<rect x="{X + 6}" y="{Y + 6}" width="2" height="8" fill="#f5e6a8"/>'
                     f'<rect x="{X + 9}" y="{Y + 6}" width="2" height="8" fill="#f5e6a8"/>'
                     f'<rect x="{X + 12}" y="{Y + 6}" width="2" height="8" fill="#f5e6a8"/>')
        else:
            spec = WEAPONS[it["name"]]
            s.append(f'<rect x="{X + 1}" y="{Y + 4}" width="18" height="12" rx="3" fill="{spec["color"]}" stroke="#111"/>'
                     f'<text x="{X + 10}" y="{Y + 13.5}" text-anchor="middle" font-size="8" font-weight="bold" '
                     f'font-family="Courier New, monospace" fill="#111">{spec["tag"]}</text>')

    # weapon range ring
    p = g["player"]
    if g["status"] in ("playing", "paused"):
        rr = WEAPONS[g["weapon"]]["range"] * CELL
        s.append(f'<circle cx="{px(p["x"]):.1f}" cy="{px(p["y"]):.1f}" r="{rr:.1f}" fill="none" '
                 f'stroke="rgba(255,255,255,0.22)" stroke-width="1" stroke-dasharray="3 5"/>')

    # tracers
    for (x0, y0, x1, y1, col) in g["tracers"]:
        s.append(f'<line x1="{px(x0):.1f}" y1="{px(y0):.1f}" x2="{px(x1):.1f}" y2="{px(y1):.1f}" '
                 f'stroke="{col}" stroke-width="2.5" opacity="0.9"/>')

    # target reticle
    if g["status"] == "playing":
        t = choose_target(g, aim_id)
        if t is not None:
            s.append(f'<circle cx="{px(t["x"]):.1f}" cy="{px(t["y"]):.1f}" r="13" fill="none" stroke="#ffe066" '
                     f'stroke-width="2" stroke-dasharray="4 3"/>')

    # bots
    for b in g["bots"]:
        if not b["alive"]:
            continue
        X, Y = px(b["x"]), px(b["y"])
        col = STATE_COLORS.get(b["state"], "#8c3b3b")
        pct = 100.0 * b["hp"] / b["max_hp"]
        s.append(f'<g><title>Bot #{b["id"]} - {e(b["state"])} - HP {b["hp"]}/{b["max_hp"]}</title>'
                 f'<circle cx="{X:.1f}" cy="{Y:.1f}" r="8" fill="{col}" stroke="#000" stroke-width="1.5"/>'
                 f'<text x="{X:.1f}" y="{Y + 3.5:.1f}" text-anchor="middle" font-size="10" font-weight="bold" '
                 f'font-family="Courier New, monospace" fill="#fff">{b["id"]}</text>'
                 f'<rect x="{X - 8:.1f}" y="{Y - 14:.1f}" width="16" height="3" fill="#222"/>'
                 f'<rect x="{X - 8:.1f}" y="{Y - 14:.1f}" width="{16 * pct / 100:.1f}" height="3" fill="{hp_color(pct)}"/></g>')

    # player
    X, Y = px(p["x"]), px(p["y"])
    pct = 100.0 * p["hp"] / p["max_hp"]
    s.append(f'<g><title>YOU - HP {p["hp"]}/{p["max_hp"]}</title>'
             f'<circle cx="{X:.1f}" cy="{Y:.1f}" r="9" fill="#3fa7ff" stroke="#fff" stroke-width="2"/>'
             f'<circle cx="{X:.1f}" cy="{Y:.1f}" r="3" fill="#0b3d66"/>'
             f'<rect x="{X - 9:.1f}" y="{Y - 16:.1f}" width="18" height="3.5" fill="#222"/>'
             f'<rect x="{X - 9:.1f}" y="{Y - 16:.1f}" width="{18 * pct / 100:.1f}" height="3.5" fill="{hp_color(pct)}"/></g>')

    # status overlays
    overlay = None
    if g["status"] == "menu":
        overlay = ("READY", "Press START GAME", 0.45)
    elif g["status"] == "paused":
        overlay = ("PAUSED", "Press RESUME to continue", 0.55)
    elif g["status"] == "won":
        overlay = ("VICTORY", "You are the last survivor!", 0.5)
    elif g["status"] == "lost":
        overlay = ("ELIMINATED", "Better luck next match", 0.5)
    if overlay:
        s.append(f'<rect width="{SIZE}" height="{SIZE}" fill="rgba(0,0,0,{overlay[2]})"/>'
                 f'<text x="{SIZE / 2}" y="{SIZE / 2 - 5}" text-anchor="middle" font-size="46" font-weight="bold" '
                 f'font-family="Courier New, monospace" fill="#c3b091">{overlay[0]}</text>'
                 f'<text x="{SIZE / 2}" y="{SIZE / 2 + 28}" text-anchor="middle" font-size="16" '
                 f'font-family="Courier New, monospace" fill="#e2e6cf">{overlay[1]}</text>')
    s.append('</svg>')
    return "".join(s)


def render_status(g):
    p = g["player"]
    w = g["weapon"]
    inv = g["inv"][w]
    spec = WEAPONS[w]
    pct = 100.0 * p["hp"] / p["max_hp"]
    alive = sum(1 for b in g["bots"] if b["alive"])
    cells = [("ENEMIES LEFT", alive), ("KILLS", g["kills"]), ("SCORE", g["score"]),
             ("DAMAGE DEALT", g["damage_dealt"]), ("SURVIVAL", f"{g['tick']}s"),
             ("WEAPON", w)]
    grid = "".join(f'<div class="mbr-cell"><span>{e(k)}</span><b>{e(v)}</b></div>' for k, v in cells)
    cd = g["cd"][w]
    cd_txt = "READY" if cd <= 0 else f"COOLDOWN {cd}"
    md('<div class="mbr-panel"><div class="mbr-h">PLAYER STATUS</div>'
       + bar_html("HEALTH", p["hp"], p["max_hp"], hp_color(pct), f"{p['hp']} / {p['max_hp']}")
       + bar_html("AMMO (" + cd_txt + ")", inv["mag"], spec["mag"], "#d4a017",
                  f"{inv['mag']} / {spec['mag']}  |  reserve {inv['reserve']}")
       + f'<div class="mbr-grid">{grid}</div></div>')


def render_zone(g):
    p = g["player"]
    zd = zone_dist(p["x"], p["y"])
    inside = zd <= g["zone_radius"]
    if g["phase"] < FINAL_PHASE:
        timer = f"{g['zone_timer']}s"
        nxt = f"{ZONE_RADII[g['phase'] + 1]:.1f}"
        timer_cls = "mbr-danger" if g["zone_timer"] <= 3 else ""
    else:
        timer, nxt, timer_cls = "FINAL", "-", "mbr-danger"
    status = ('<span class="mbr-ok">INSIDE SAFE ZONE</span>' if inside else
              f'<span class="mbr-danger">OUTSIDE ZONE - {zone_damage(g)} damage per turn!</span>')
    cells = [("PHASE", f"{g['phase'] + 1} / {len(ZONE_RADII)}"),
             ("SAFE RADIUS", f"{g['zone_radius']:.1f}"),
             ("NEXT SHRINK IN", f'<span class="{timer_cls}">{timer}</span>'),
             ("NEXT RADIUS", nxt)]
    grid = "".join(f'<div class="mbr-cell"><span>{k}</span><b>{v}</b></div>' for k, v in cells)
    md(f'<div class="mbr-panel"><div class="mbr-h">SAFE ZONE</div>{status}'
       f'<div class="mbr-grid mbr-grid4">{grid}</div></div>')


def render_intel(g):
    p = g["player"]
    pp = (p["x"], p["y"])
    alive = sorted((b for b in g["bots"] if b["alive"]), key=lambda b: dist(pp, (b["x"], b["y"])))
    rows = []
    for b in alive[:10]:
        pct = 100.0 * b["hp"] / b["max_hp"]
        col = STATE_COLORS.get(b["state"], "#8c3b3b")
        rows.append(f'<tr><td>#{b["id"]}</td><td>{dist(pp, (b["x"], b["y"])):.1f}</td>'
                    f'<td><div class="mbr-mini"><div style="width:{pct:.0f}%;background:{hp_color(pct)}"></div></div> {b["hp"]}</td>'
                    f'<td><span class="mbr-chip" style="background:{col}">{e(b["state"])}</span></td></tr>')
    body = "".join(rows) if rows else '<tr><td colspan="4">No enemies remaining</td></tr>'
    md('<div class="mbr-panel"><div class="mbr-h">ENEMY INTEL (nearest first)</div>'
       '<table class="mbr-table"><tr><th>Bot</th><th>Dist</th><th>HP</th><th>State</th></tr>'
       + body + '</table></div>')


def render_log(g):
    colors = {"good": "#7bd88f", "bad": "#ff7b7b", "warn": "#f0c36a", "info": "#b9c2a6"}
    rows = "".join(f'<div style="color:{colors.get(k, "#b9c2a6")}"><span class="mbr-t">T{t:03d}</span> {e(txt)}</div>'
                   for (t, txt, k) in reversed(g["log"][-10:]))
    md(f'<div class="mbr-panel"><div class="mbr-h">COMBAT LOG</div>{rows}</div>')


def render_results(g):
    won = g["status"] == "won"
    title = "VICTORY" if won else "GAME OVER"
    sub = ("You are the last survivor on the battlefield!" if won
           else f"You were eliminated by {e(g['killed_by'] or 'the storm')}.")
    elapsed = (g["end_time"] or time.time()) - (g["start_time"] or time.time())
    acc = 100.0 * g["hits"] / g["shots"] if g["shots"] else 0.0
    alive = sum(1 for b in g["bots"] if b["alive"])
    breakdown = (f"Kills {g['kills']} x {SCORE_KILL} = {g['kills'] * SCORE_KILL} | "
                 f"Phases {g['phases_survived']} x {SCORE_PHASE} = {g['phases_survived'] * SCORE_PHASE} | "
                 f"Health packs {g['packs']} x {SCORE_PACK} = {g['packs'] * SCORE_PACK} | "
                 f"Win bonus {SCORE_WIN if won else 0}")
    cells = [("MATCH RESULT", g["result"]), ("FINAL SCORE", g["score"]), ("KILLS", g["kills"]),
             ("ENEMIES REMAINING", alive), ("DAMAGE DEALT", g["damage_dealt"]),
             ("DAMAGE TAKEN", g["damage_taken"]), ("SURVIVAL TIME", f"{g['tick']} turns ({g['tick']}s)"),
             ("ZONE PHASES SURVIVED", g["phases_survived"]), ("ACCURACY", f"{acc:.0f}% ({g['hits']}/{g['shots']})"),
             ("REAL TIME PLAYED", f"{int(elapsed // 60)}m {int(elapsed % 60)}s")]
    grid = "".join(f'<div class="mbr-cell"><span>{e(k)}</span><b>{e(v)}</b></div>' for k, v in cells)
    cls = "mbr-win" if won else "mbr-lose"
    md(f'<div class="mbr-panel {cls}"><div class="mbr-result-title">{title}</div>'
       f'<div class="mbr-result-sub">{sub}</div><div class="mbr-grid mbr-grid5">{grid}</div>'
       f'<div class="mbr-breakdown">{e(breakdown)}</div></div>')


CSS = """
<style>
.stApp { background: radial-gradient(circle at 20% 0%, #1a2216 0%, #0b0f0a 70%); }
[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 1.2rem; max-width: 1250px; }
.mbr-title { font-family: 'Courier New', monospace; letter-spacing: 8px; text-align: center; color: #c3b091;
  margin: 0; padding: 0; font-size: 2.4rem; text-shadow: 0 0 12px rgba(195,176,145,0.35); }
.mbr-sub { text-align: center; color: #8a9a5b; font-family: 'Courier New', monospace; margin-bottom: 14px; font-size: 0.9rem; }
[data-testid="stWidgetLabel"] p, [data-testid="stRadio"] label p { color: #d8dcc8 !important; }
div.stButton > button { width: 100%; background: #2b3523; color: #e2e6cf; border: 1px solid #5b6b45;
  border-radius: 6px; font-weight: 700; }
div.stButton > button:hover:not(:disabled) { border-color: #c3b091; color: #fff; background: #3a472f; }
div.stButton > button:disabled { opacity: 0.35; }
.mbr-panel { background: #141b12; border: 1px solid #3b4a2f; border-radius: 8px; padding: 10px 14px;
  margin-bottom: 10px; color: #d8dcc8; font-size: 0.88rem; }
.mbr-h { font-family: 'Courier New', monospace; letter-spacing: 3px; color: #8a9a5b; font-weight: bold;
  margin-bottom: 8px; font-size: 0.8rem; }
.mbr-bar-label { display: flex; justify-content: space-between; font-size: 0.78rem; color: #b9c2a6; margin-top: 4px; }
.mbr-bar { background: #0a0e09; border: 1px solid #2c3823; border-radius: 4px; height: 14px; overflow: hidden; }
.mbr-bar-fill { height: 100%; transition: width 0.2s; }
.mbr-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin-top: 10px; }
.mbr-grid4 { grid-template-columns: repeat(2, 1fr); }
.mbr-grid5 { grid-template-columns: repeat(5, 1fr); }
.mbr-cell { background: #0f150d; border: 1px solid #2c3823; border-radius: 6px; padding: 5px 8px; }
.mbr-cell span { display: block; font-size: 0.62rem; letter-spacing: 1px; color: #7d8b63; }
.mbr-cell b { font-size: 1.05rem; color: #e8ecd6; font-family: 'Courier New', monospace; }
.mbr-ok { color: #7bd88f; font-weight: bold; }
.mbr-danger { color: #ff6b5e; font-weight: bold; }
.mbr-table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
.mbr-table th { text-align: left; color: #7d8b63; font-weight: normal; border-bottom: 1px solid #2c3823; }
.mbr-table td { padding: 2px 4px; color: #d8dcc8; }
.mbr-mini { display: inline-block; width: 46px; height: 7px; background: #222; vertical-align: middle; }
.mbr-mini div { height: 100%; }
.mbr-chip { border-radius: 10px; padding: 1px 8px; font-size: 0.7rem; color: #fff; }
.mbr-t { color: #6c7a55; font-family: 'Courier New', monospace; }
.mbr-win { border-color: #7bd88f; box-shadow: 0 0 18px rgba(123,216,143,0.25); }
.mbr-lose { border-color: #e74c3c; box-shadow: 0 0 18px rgba(231,76,60,0.25); }
.mbr-result-title { font-family: 'Courier New', monospace; font-size: 2.2rem; letter-spacing: 6px;
  text-align: center; color: #c3b091; font-weight: bold; }
.mbr-result-sub { text-align: center; color: #b9c2a6; margin-bottom: 6px; }
.mbr-breakdown { text-align: center; color: #8a9a5b; font-size: 0.78rem; margin-top: 10px; }
.mbr-legend { text-align: center; color: #7d8b63; font-size: 0.75rem; margin: 6px 0 10px 0; }
@media (max-width: 900px) { .mbr-grid5 { grid-template-columns: repeat(2, 1fr); } }
</style>
"""


# ----------------------------------------------------------------------------
# MAIN APP
# ----------------------------------------------------------------------------
if "game" not in st.session_state:
    st.session_state["game"] = new_game(8, "menu")
g = st.session_state["game"]

# keep the pre-game arena in sync with the enemy-count slider
if g["status"] == "menu" and len(g["bots"]) != st.session_state.get("bot_count", 8):
    st.session_state["game"] = new_game(st.session_state.get("bot_count", 8), "menu")
    g = st.session_state["game"]

# keep widget values consistent with the game state (before the widgets are created)
alive_ids = sorted(b["id"] for b in g["bots"] if b["alive"])
aim_options = [-1] + alive_ids
if st.session_state.get("aim_sel", -1) not in aim_options:
    st.session_state["aim_sel"] = -1
st.session_state["weapon_sel"] = g["weapon"]
aim_id = st.session_state.get("aim_sel", -1)
playing = g["status"] == "playing"

md(CSS)
md('<h1 class="mbr-title">MINI BATTLE ROYALE</h1>'
   '<div class="mbr-sub">Loot up. Stay in the zone. Be the last survivor.</div>')

top = st.columns([1, 1, 1, 2])
top[0].button("▶ START GAME", key="btn_start", on_click=cb_start, disabled=g["status"] != "menu")
top[1].button("▶ RESUME" if g["status"] == "paused" else "⏸ PAUSE GAME", key="btn_pause",
              on_click=cb_pause, disabled=g["status"] not in ("playing", "paused"))
top[2].button("🔄 RESTART GAME", key="btn_restart", on_click=cb_restart)
top[3].slider("Enemy bots (applies to the next match)", 8, 14, 8, key="bot_count")

if g["status"] in ("won", "lost"):
    render_results(g)
    st.button("🔁 PLAY AGAIN", key="btn_again", on_click=cb_restart)

left, right = st.columns([3, 2])

with left:
    md(render_arena(g, aim_id))
    md('<div class="mbr-legend">You = blue | Bots: dark red roaming, orange chasing, red attacking, purple escaping the zone | '
       'Red line = safe zone edge, yellow dashed = next zone | Faint ring = your weapon range</div>')
    render_log(g)

with right:
    render_status(g)
    render_zone(g)

    md('<div class="mbr-panel"><div class="mbr-h">WEAPONS &amp; AIM</div></div>')
    owned = list(g["inv"].keys())

    def fmt_weapon(w):
        inv = g["inv"][w]
        return f"{w}  [{inv['mag']}/{inv['reserve']}]"

    st.radio("Weapon", owned, key="weapon_sel", format_func=fmt_weapon,
             on_change=cb_weapon, disabled=not playing)

    def fmt_aim(i):
        if i == -1:
            return "Auto (nearest enemy in range)"
        b = next(b for b in g["bots"] if b["id"] == i)
        d = dist((g["player"]["x"], g["player"]["y"]), (b["x"], b["y"]))
        return f"Bot #{i} - {d:.1f} tiles - HP {b['hp']}"

    st.selectbox("Aim at", aim_options, key="aim_sel", format_func=fmt_aim, disabled=not playing)

    if playing:
        t = choose_target(g, aim_id)
        if t is not None:
            spec = WEAPONS[g["weapon"]]
            pp = (g["player"]["x"], g["player"]["y"])
            d = dist(pp, (t["x"], t["y"]))
            if d > spec["range"]:
                info = '<span class="mbr-danger">OUT OF RANGE</span>'
            elif not has_los(g, pp, (t["x"], t["y"])):
                info = '<span class="mbr-danger">BLOCKED BY COVER</span>'
            else:
                info = f'<span class="mbr-ok">CLEAR SHOT - hit chance ~{player_hit_chance(spec, d) * 100:.0f}%</span>'
            md(f'<div class="mbr-legend" style="text-align:left">Target Bot #{t["id"]} at {d:.1f} tiles: {info}</div>')

    md('<div class="mbr-panel"><div class="mbr-h">MOVEMENT &amp; COMBAT</div></div>')
    r1 = st.columns(3)
    r1[1].button("▲ UP", key="mv_up", on_click=cb_move, args=(0, -1), disabled=not playing)
    r2 = st.columns(3)
    r2[0].button("◀ LEFT", key="mv_left", on_click=cb_move, args=(-1, 0), disabled=not playing)
    r2[1].button("⏳ HOLD", key="mv_hold", on_click=cb_wait, disabled=not playing)
    r2[2].button("RIGHT ▶", key="mv_right", on_click=cb_move, args=(1, 0), disabled=not playing)
    r3 = st.columns(3)
    r3[1].button("▼ DOWN", key="mv_down", on_click=cb_move, args=(0, 1), disabled=not playing)
    r4 = st.columns(2)
    r4[0].button("🔫 SHOOT", key="act_shoot", on_click=cb_shoot, disabled=not playing)
    r4[1].button("🔄 RELOAD", key="act_reload", on_click=cb_reload, disabled=not playing)

    render_intel(g)
