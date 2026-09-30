"""
AI Witcher - bridge between The Witcher 3 and AI assistants.

Reads the latest state dump written by the modAIWitcher game mod
into scriptslog.txt and exposes it:
  * as an MCP server (Claude Desktop, Claude Code, any MCP client):
        python witcher_mcp.py
  * as plain text for any other AI (ChatGPT, local LLMs, ...):
        python witcher_mcp.py --print          # Markdown
        python witcher_mcp.py --json           # JSON
        python witcher_mcp.py --map            # map points (Markdown)
        python witcher_mcp.py --print --out state.md

Log path can be overridden with the W3_SCRIPTSLOG environment variable
or the --log argument.
"""
import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

TAIL_BYTES = 16 * 1024 * 1024  # the log can be huge, read only the tail
MARK = "AIW|"

QUEST_TYPES = {"0": "Сюжетный", "1": "Глава", "2": "Побочный",
               "3": "Заказ на чудовище", "4": "Поиск сокровищ"}
DIFFICULTY = {"1": "Просто история (?)", "2": "История и меч (?)",
              "3": "На кровавом пути (?)", "4": "На смерть! (?)"}
OBJ_STATUS = {"0": "неактивна", "1": "активна", "2": "выполнена", "3": "провалена"}

# map pin types that represent explorable content (the rest are services/transport)
EXPLORE_TYPES = {
    "PlaceOfPower": "Место силы", "BanditCamp": "Лагерь бандитов", "BanditCampfire": "Костёр бандитов",
    "MonsterNest": "Гнездо чудовищ", "MonsterDen": "Логово чудовища", "TreasureHuntMappin": "Сокровище",
    "SpoilsOfWar": "Трофеи войны", "Hideout": "Укрытие", "Refugees": "Беженцы",
    "InfestedVineyard": "Заражённый виноградник", "PlayerStash": "Тайник", "AbandonedSite": "Заброшенное место",
    "NotDiscoveredPOI": "Неисследованное место", "RoadSign": "Указатель", "Harbor": "Пристань",
    "KnightErrant": "Странствующий рыцарь", "ContrabandShip": "Контрабанда",
    "SmugglersCache": "Тайник контрабандистов", "DungeonCrawl": "Подземелье",
    "PointOfInterestMappin": "Интересное место", "GuardedTreasure": "Охраняемое сокровище",
    "MagicLamp": "Магическая лампа", "WitcherHouse": "Дом ведьмака",
}
SERVICE_TYPES = {
    "Shopkeeper": "Торговец", "Blacksmith": "Кузнец", "Armorer": "Бронник", "Herbalist": "Травник",
    "Alchemic": "Алхимик", "Innkeeper": "Трактирщик", "NoticeBoard": "Доска объявлений",
    "Enchanter": "Рунный мастер", "Hairdresser": "Цирюльник", "Prostitute": "Бордель",
    "Whetstone": "Точильный камень", "ArmorRepairTable": "Верстак бронника",
    "AlchemyTable": "Алхимический стол", "Cammerlengo": "Банк", "GwentPlayer": "Игрок в гвинт",
    "Boat": "Лодка", "Horse": "Лошадь", "Entrance": "Вход", "Herb": "Трава",
}

# pins that never become "cleared" (signposts, stash, quest markers) - hidden from to-do lists
PERMANENT_TYPES = {"RoadSign", "PlayerStash", "Harbor", "Herb", "ChapterQuest", "StoryQuest", "SideQuest",
                   "MonsterQuest", "TreasureQuest", "QuestGiverStory", "QuestGiverChapter", "QuestGiverSide"}

_LOG_OVERRIDE: str | None = None


# ---------------------------------------------------------------- log reading
def log_path() -> Path:
    custom = _LOG_OVERRIDE or os.environ.get("W3_SCRIPTSLOG")
    if custom:
        return Path(custom)
    docs = [
        Path.home() / "Documents",
        Path.home() / "OneDrive" / "Documents",
        Path.home() / "OneDrive" / "Документы",
    ]
    candidates = [d / "The Witcher 3" / n for d in docs for n in ("scriptslog.txt", "scriptlog.txt")]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


def decode(raw: bytes) -> str:
    if raw.startswith(b"\xff\xfe") or raw[1:200:2].count(0) > 50:
        return raw.decode("utf-16-le", errors="replace")
    for enc in ("utf-8", "cp1251"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", errors="replace")


def read_tail(path: Path) -> str:
    size = path.stat().st_size
    with open(path, "rb") as f:
        start = max(0, size - TAIL_BYTES)
        if start % 2:  # keep UTF-16 aligned
            start += 1
        f.seek(start)
        return decode(f.read())


def last_dump(text: str) -> list[list[str]] | None:
    lines = [ln[ln.index(MARK) + len(MARK):].strip() for ln in text.splitlines() if MARK in ln]
    end_idx = next((i for i in range(len(lines) - 1, -1, -1) if lines[i].startswith("END|")), None)
    if end_idx is None:
        return None
    stamp = lines[end_idx].split("|", 1)[1]
    for j in range(end_idx - 1, -1, -1):
        if lines[j] == f"BEGIN|{stamp}":
            return [ln.split("|") for ln in lines[j + 1:end_idx]]
    return None


# ---------------------------------------------------------------- parsing
def _num(v: str):
    try:
        f = float(v)
        return int(f) if f.is_integer() else round(f, 2)
    except ValueError:
        return v


def pin_label(t: str) -> str:
    return EXPLORE_TYPES.get(t) or SERVICE_TYPES.get(t) or t


def _is_hidden(p: dict) -> bool:
    return not p["known"] and not p["discovered"] and not p["disabled"]


def _is_open(p: dict) -> bool:
    return (p["known"] or p["discovered"]) and not p["disabled"]


def pin_status(p: dict) -> str:
    if p["disabled"]:
        return "зачищено"
    if p["discovered"]:
        return "посещено"
    if p["known"]:
        return "на карте"
    return "НЕ на карте"


def parse_dump(rows: list[list[str]]) -> dict:
    state = {"meta": {}, "character": {}, "stats": {}, "world": {}, "equipped": [], "skills": [],
             "tracked_quest": None, "quests": [], "done_quests": [], "failed_quests": [],
             "objectives": [], "highlighted_objective": None, "buffs": [],
             "alchemy_recipes": [], "crafting_schematics": [], "gwent": None,
             "map_pins": [], "inventory": [], "errors": []}
    for kind, *f in rows:
        if kind == "META" and len(f) >= 2:
            state["meta"][f[0]] = f[1]
        elif kind == "CHAR" and len(f) >= 2:
            state["character"][f[0]] = f[1]
        elif kind == "STAT" and len(f) >= 4:
            state["stats"][f[0]] = {"base": _num(f[1]), "mult": _num(f[2]), "add": _num(f[3])}
        elif kind == "WORLD" and len(f) >= 2:
            state["world"][f[0]] = f[1]
        elif kind == "EQUIP" and len(f) >= 3:
            e = {"slot": f[0], "name": f[1], "id": f[2]}
            if len(f) >= 6:
                e.update(level=_num(f[3]), durability=_num(f[4]), max_durability=_num(f[5]))
            state["equipped"].append(e)
        elif kind == "SKILL" and len(f) >= 2:
            state["skills"].append({"id": f[0], "level": _num(f[1])})
        elif kind == "TRACKED" and f:
            state["tracked_quest"] = f[0]
        elif kind in ("QUEST", "DONE", "FAILED") and len(f) >= 2:
            key = {"QUEST": "quests", "DONE": "done_quests", "FAILED": "failed_quests"}[kind]
            state[key].append({"type": QUEST_TYPES.get(f[0], f[0]), "title": f[1]})
        elif kind == "OBJ" and len(f) >= 2:
            state["objectives"].append({"status": OBJ_STATUS.get(f[0], f[0]), "title": f[1],
                                        "quest": f[2] if len(f) > 2 else ""})
        elif kind == "OBJHL" and f:
            state["highlighted_objective"] = f[0]
        elif kind == "BUFF" and len(f) >= 2:
            state["buffs"].append({"type": f[0], "seconds_left": _num(f[1])})
        elif kind == "RECIPE" and f:
            state["alchemy_recipes"].append(f[0])
        elif kind == "SCHEM" and f:
            state["crafting_schematics"].append(f[0])
        elif kind == "GWENT" and len(f) >= 2:
            state["gwent"] = {"owned": _num(f[0]), "total": _num(f[1])}
        elif kind == "PIN" and len(f) >= 8:
            state["map_pins"].append({
                "type": f[0], "tag": f[1], "known": f[2] == "1", "discovered": f[3] == "1",
                "disabled": f[4] == "1", "x": _num(f[5]), "y": _num(f[6]), "distance": _num(f[7]),
                "name": f[8] if len(f) > 8 else "",
            })
        elif kind == "ITEM" and len(f) >= 2:
            state["inventory"].append({"name": f[0], "count": _num(f[1]),
                                       "id": f[2] if len(f) > 2 else ""})
        elif kind == "ERROR":
            state["errors"].append("|".join(f))
    return state


# ---------------------------------------------------------------- formatting
def _pin_line(p: dict) -> str:
    name = f" «{p['name']}»" if p["name"] else ""
    return (f"- {pin_label(p['type'])}{name} — {p['distance']} м, ({p['x']}, {p['y']}), "
            f"{pin_status(p)} [{p['tag']}]")


def map_summary(s: dict, limit: int = 12) -> list[str]:
    pins = s["map_pins"]
    if not pins:
        return []
    out = [f"\n## Карта текущего мира ({len(pins)} точек)"]
    by_type = defaultdict(list)
    for p in pins:
        by_type[p["type"]].append(p)
    out.append("| Тип | Всего | Не найдено | Найдено, не зачищено | Зачищено |")
    out.append("| --- | --- | --- | --- | --- |")
    for t in sorted(by_type, key=lambda t: (t not in EXPLORE_TYPES, pin_label(t))):
        ps = by_type[t]
        out.append(f"| {pin_label(t)} (`{t}`) | {len(ps)} | {sum(_is_hidden(p) for p in ps)} | "
                   f"{sum(_is_open(p) for p in ps)} | {sum(p['disabled'] for p in ps)} |")
    explore = [p for p in pins if (p["type"] in EXPLORE_TYPES or p["type"] not in SERVICE_TYPES)
               and p["type"] not in PERMANENT_TYPES]
    hidden = sorted((p for p in explore if _is_hidden(p)), key=lambda p: p["distance"])
    todo = sorted((p for p in explore if _is_open(p)), key=lambda p: p["distance"])
    if hidden:
        out.append(f"\n### Ещё НЕ найдено — ближайшие {min(limit, len(hidden))} из {len(hidden)}")
        out += [_pin_line(p) for p in hidden[:limit]]
    if todo:
        out.append(f"\n### Найдено, но не зачищено — ближайшие {min(limit, len(todo))} из {len(todo)}")
        out += [_pin_line(p) for p in todo[:limit]]
    out.append("\n(Полный список точек — инструмент get_map_points.)")
    return out


def to_markdown(s: dict) -> str:
    out = ["# Состояние Геральта (The Witcher 3)"]
    if s["meta"]:
        out.append(f"_Версия мода: {s['meta'].get('version', '?')}_")
    if s["character"]:
        out.append("\n## Персонаж")
        for k, v in s["character"].items():
            if k == "difficulty":
                v = f"{v} — {DIFFICULTY.get(v, '?')}"
            out.append(f"- {k}: {v}")
    if s["stats"]:
        out.append("\n## Боевые характеристики (сырые значения: база / множитель / добавка)")
        out += [f"- {k}: {v['base']} / {v['mult']} / {v['add']}" for k, v in s["stats"].items()]
    if s["world"]:
        out.append("\n## Мир")
        out += [f"- {k}: {v}" for k, v in s["world"].items()]
    if s["equipped"]:
        out.append("\n## Надето")
        for e in s["equipped"]:
            extra = ""
            if "level" in e:
                extra = f", ур. {e['level']}, прочность {e['durability']}/{e['max_durability']}"
            out.append(f"- {e['name']} ({e['id']}{extra})")
    if s["skills"]:
        out.append("\n## Изученные навыки (внутреннее имя: уровень)")
        out += [f"- {k['id']}: {k['level']}" for k in s["skills"]]
    if s["tracked_quest"] or s["quests"]:
        out.append("\n## Квесты")
        if s["tracked_quest"]:
            out.append(f"- ОТСЛЕЖИВАЕТСЯ: {s['tracked_quest']}")
        out += [f"- [{q['type']}] {q['title']}" for q in s["quests"]]
    if s["objectives"] or s["highlighted_objective"]:
        out.append("\n## Текущие цели")
        if s["highlighted_objective"]:
            out.append(f"- ВЫДЕЛЕНА: {s['highlighted_objective']}")
        out += [f"- ({o['status']}) {o['title']}" + (f" — {o['quest']}" if o["quest"] else "")
                for o in s["objectives"]]
    if s["done_quests"]:
        out.append(f"\n## Завершённые квесты ({len(s['done_quests'])})")
        out += [f"- [{q['type']}] {q['title']}" for q in s["done_quests"]]
    if s["failed_quests"]:
        out.append(f"\n## Проваленные квесты ({len(s['failed_quests'])})")
        out += [f"- [{q['type']}] {q['title']}" for q in s["failed_quests"]]
    if s["buffs"]:
        out.append("\n## Активные эффекты")
        out += [f"- {b['type']}" + (f" — {b['seconds_left']} с" if isinstance(b['seconds_left'], (int, float)) and b['seconds_left'] > 0 else "")
                for b in s["buffs"]]
    if s["gwent"]:
        out.append(f"\n## Гвинт\n- карт в коллекции: {s['gwent']['owned']} из {s['gwent']['total']}")
    if s["alchemy_recipes"] or s["crafting_schematics"]:
        out.append(f"\n## Известные рецепты ({len(s['alchemy_recipes'])}) и чертежи ({len(s['crafting_schematics'])})")
        if s["alchemy_recipes"]:
            out.append("- Алхимия: " + ", ".join(s["alchemy_recipes"]))
        if s["crafting_schematics"]:
            out.append("- Крафт: " + ", ".join(s["crafting_schematics"]))
    out += map_summary(s)
    if s["inventory"]:
        visible = [it for it in s["inventory"] if it["name"].strip()]
        hidden = len(s["inventory"]) - len(visible)
        out.append(f"\n## Инвентарь ({len(visible)} позиций" + (f", ещё {hidden} служебных" if hidden else "") + ")")
        out += [f"- {it['name']} x{it['count']}" for it in visible]
    if s["errors"]:
        out.append("\n## Ошибки мода")
        out += [f"- {e}" for e in s["errors"]]
    return "\n".join(out)


def filter_pins(s: dict, type_filter: str = "", status: str = "all", limit: int = 100) -> list[dict]:
    pins = s["map_pins"]
    if type_filter:
        tf = type_filter.lower()
        pins = [p for p in pins if tf in p["type"].lower() or tf in pin_label(p["type"]).lower()
                or tf in p["name"].lower() or tf in p["tag"].lower()]
    if status == "hidden":
        pins = [p for p in pins if _is_hidden(p)]
    elif status == "open":
        pins = [p for p in pins if _is_open(p)]
    elif status == "done":
        pins = [p for p in pins if p["disabled"]]
    elif status == "todo":
        pins = [p for p in pins if not p["disabled"]]
    return sorted(pins, key=lambda p: p["distance"])[:limit]


def map_markdown(pins: list[dict]) -> str:
    if not pins:
        return "Подходящих точек нет."
    c = Counter(pin_status(p) for p in pins)
    head = f"# Точки карты: {len(pins)} ({', '.join(f'{k}: {v}' for k, v in c.items())})"
    return "\n".join([head] + [_pin_line(p) for p in pins])


# ---------------------------------------------------------------- route planning
ROUTE_SKIP = {"Enemy", "ChapterQuest", "StoryQuest", "SideQuest", "QuestAvailable", "MonsterQuest",
              "TreasureQuest", "Herb", "PlayerStash", "Harbor", "Boat", "Teleport", "Entrance"}
# lower weight = preferred (distance is multiplied by it)
ROUTE_WEIGHT = {"PlaceOfPower": 0.6, "TreasureHuntMappin": 0.8, "BossAndTreasure": 0.9,
                "DungeonCrawl": 0.9, "RoadSign": 1.15}


NEST_BOMB_IDS = ("grapeshot", "samum", "dancing star")
TYPE_REQUIREMENTS = {
    "MonsterNest": "нужна бомба: Картечь / Самум / Танцующая звезда (сначала перебить чудовищ)",
    "BossAndTreasure": "охраняемое сокровище — сильный страж, проверить уровень (красный череп = уйти)",
    "RescuingTown": "деревня занята бандитами/чудовищами — бой с группой",
    "BanditCamp": "лагерь — бой с группой бандитов",
    "BanditCampfire": "несколько бандитов у костра",
    "DungeonCrawl": "подземелье/пещера — может быть темно и тесно, взять факел",
    "SpoilsOfWar": "трофеи войны — часто под водой или с ключом рядом",
    "PlaceOfPower": "без требований; даёт очко навыка при первой активации",
    "RoadSign": "без требований; открывает быстрое перемещение",
}


def notes_path() -> Path:
    custom = os.environ.get("W3_POI_NOTES")
    if custom:
        return Path(custom)
    return Path(__file__).resolve().parent.parent / "poi_notes.json"


def load_notes() -> dict:
    p = notes_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def save_note(tag: str, note: str = "", skip: bool | None = None) -> str:
    data = load_notes()
    entry = data.get(tag, {"note": "", "skip": False})
    if note:
        entry["note"] = note
    if skip is not None:
        entry["skip"] = bool(skip)
    data[tag] = entry
    notes_path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return f"Заметка сохранена для {tag}: skip={entry['skip']}; {entry['note']}"


def has_nest_bomb(s: dict) -> bool:
    for it in s["inventory"]:
        iid = str(it.get("id", "")).lower()
        if any(b in iid for b in NEST_BOMB_IDS):
            return True
    return False


def _player_xy(s: dict) -> tuple[float, float] | None:
    try:
        x, y = s["world"]["position"].split()[:2]
        return float(x), float(y)
    except (KeyError, ValueError):
        return None


def _d(a, b) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def plan_route_impl(s: dict, count: int = 5, types: str = "", include_signposts: bool = True,
               max_radius: float = 0) -> dict:
    start = _player_xy(s)
    if start is None:
        return {"error": "В дампе нет позиции игрока."}
    wanted = [t.strip().lower() for t in types.split(",") if t.strip()]
    notes = load_notes()
    bombs = has_nest_bomb(s)
    skipped = []
    cands = []
    for p in s["map_pins"]:
        if p["disabled"] or p["type"] in ROUTE_SKIP or p["type"] in SERVICE_TYPES:
            continue
        if p["tag"] in ("", "None"):
            continue
        if p["type"] == "RoadSign" and (not include_signposts or p["discovered"]):
            continue
        if wanted and not any(w in p["type"].lower() or w in pin_label(p["type"]).lower() for w in wanted):
            continue
        xy = (float(p["x"]), float(p["y"]))
        if max_radius and _d(start, xy) > max_radius:
            continue
        n = notes.get(p["tag"], {})
        if n.get("skip"):
            skipped.append((p, "пропуск по заметке: " + n.get("note", "")))
            continue
        if p["type"] == "MonsterNest" and not bombs:
            skipped.append((p, "нет бомбы для гнезда"))
            continue
        cands.append((p, xy))
    route, cur = [], start
    while cands and len(route) < count:
        i = min(range(len(cands)),
                key=lambda k: _d(cur, cands[k][1]) * ROUTE_WEIGHT.get(cands[k][0]["type"], 1.0))
        route.append(cands.pop(i))
        cur = route[-1][1]
    # 2-opt on the open path starting at the player
    def length(r):
        pts = [start] + [xy for _, xy in r]
        return sum(_d(pts[k], pts[k + 1]) for k in range(len(pts) - 1))
    improved = True
    while improved and len(route) > 2:
        improved = False
        for a in range(len(route) - 1):
            for b in range(a + 1, len(route)):
                new = route[:a] + route[a:b + 1][::-1] + route[b + 1:]
                if length(new) + 0.5 < length(route):
                    route, improved = new, True
    stops, cur, total = [], start, 0.0
    for p, xy in route:
        leg = _d(cur, xy)
        total += leg
        stops.append({**p, "leg": round(leg), "cumulative": round(total),
                      "requirement": TYPE_REQUIREMENTS.get(p["type"], ""),
                      "note": notes.get(p["tag"], {}).get("note", "")})
        cur = xy
    tags = ",".join(p["tag"] for p, _ in route)
    cmds = []
    if route:
        cmds.append(f'aimark("{tags}")')
        fx, fy = route[0][1]
        cmds.append(f"aipin({round(fx)}, {round(fy)})")
    near_skipped = sorted(skipped, key=lambda t: _d(start, (float(t[0]["x"]), float(t[0]["y"]))))[:5]
    return {"start": start, "stops": stops, "total": round(total), "commands": cmds,
            "has_nest_bomb": bombs,
            "skipped": [{"tag": p["tag"], "type": p["type"], "reason": why} for p, why in near_skipped]}


def route_markdown(r: dict) -> str:
    if "error" in r:
        return r["error"]
    if not r["stops"]:
        return "Подходящих незачищенных точек не найдено."
    out = [f"# Маршрут: {len(r['stops'])} точек, ~{r['total']} м от Геральта "
           f"({round(r['start'][0])}, {round(r['start'][1])})", ""]
    for i, p in enumerate(r["stops"], 1):
        name = f" «{p['name']}»" if p["name"] else ""
        out.append(f"{i}. {pin_label(p['type'])}{name} — +{p['leg']} м (итого {p['cumulative']} м), "
                   f"({p['x']}, {p['y']}), {pin_status(p)} [{p['tag']}]")
        if p.get("requirement"):
            out.append(f"   требования: {p['requirement']}")
        if p.get("note"):
            out.append(f"   заметка: {p['note']}")
    if r.get("skipped"):
        out += ["", "Пропущено рядом:"]
        out += [f"- {pin_label(k['type'])} [{k['tag']}] — {k['reason']}" for k in r["skipped"]]
    if not r.get("has_nest_bomb"):
        out.append("Гнёзда исключены: нет бомбы (Картечь / Самум / Танцующая звезда) — сварить в алхимии.")
    out += ["", "Команды для консоли игры (отметить на карте и поставить метку на первую точку):"]
    out += [f"    {c}" for c in r["commands"]]
    out.append("Повторный aipin с теми же координатами убирает метку. Уровень врагов в точках "
               "неизвестен — при красном черепе над противником пропускать точку.")
    return "\n".join(out)


def load_state() -> tuple[dict | None, str | None]:
    path = log_path()
    if not path.exists():
        return None, (f"Файл лога не найден: {path}. Игра должна быть запущена с параметром "
                      "-debugscripts, либо укажите путь через W3_SCRIPTSLOG / --log.")
    rows = last_dump(read_tail(path))
    if rows is None:
        return None, ("В логе нет завершённого дампа. Загрузите сохранение, откройте консоль "
                      "и введите aidump, затем повторите.")
    return parse_dump(rows), None


def guide_path() -> Path:
    custom = os.environ.get("W3_AI_GUIDE")
    if custom:
        return Path(custom)
    here = Path(__file__).resolve().parent
    for cand in (here.parent / "AI_GUIDE.md", here / "AI_GUIDE.md"):
        if cand.exists():
            return cand
    return here.parent / "AI_GUIDE.md"


def read_guide(section: str = "") -> str:
    path = guide_path()
    if not path.exists():
        return f"Файл руководства не найден: {path}"
    text = path.read_text(encoding="utf-8")
    if not section.strip():
        return text
    q = section.strip().lower()
    blocks, cur = [], []
    for line in text.splitlines():
        if line.startswith("## ") and cur:
            blocks.append("\n".join(cur))
            cur = []
        cur.append(line)
    if cur:
        blocks.append("\n".join(cur))
    hits = [b for b in blocks if q in b.lower()]
    return "\n\n".join(hits) if hits else f"Раздел «{section}» не найден. Вызовите без аргумента для всего файла."


def log_status() -> str:
    path = log_path()
    if not path.exists():
        return f"Лог не найден: {path}"
    count = read_tail(path).count(MARK)
    return f"Лог: {path}\nРазмер: {path.stat().st_size // 1024} КБ\nСтрок мода в конце лога: {count}"


# ---------------------------------------------------------------- MCP server
def run_mcp() -> None:
    try:  # mcp 2.x
        from mcp.server.mcpserver import MCPServer as Server
    except ImportError:  # mcp 1.x
        from mcp.server.fastmcp import FastMCP as Server

    mcp = Server("witcher3")

    @mcp.tool()
    def get_witcher_state() -> str:
        """Последний снимок состояния игрока в The Witcher 3: уровень, опыт, очки навыков,
        характеристики, сложность, регион, снаряжение (уровень и прочность), навыки,
        активные/завершённые/проваленные квесты, текущие цели, активные эффекты,
        гвинт, известные рецепты и чертежи, сводка по карте (ближайшие неоткрытые и
        незачищенные места) и инвентарь. Снимок создаётся в игре командой aidump."""
        state, err = load_state()
        return err or to_markdown(state)

    @mcp.tool()
    def get_map_points(type_filter: str = "", status: str = "todo", limit: int = 60) -> str:
        """Точки карты текущего мира, отсортированные по расстоянию от Геральта.
        type_filter: часть типа, русского названия, имени или тега (например 'PlaceOfPower',
        'лагерь', 'сокровище', 'кузнец'); пусто = все.
        status: 'all' | 'todo' (не зачищено) | 'hidden' (ещё не найдено) |
        'open' (найдено, но не зачищено) | 'done' (зачищено/использовано).
        Координаты — мировые X/Y игры."""
        state, err = load_state()
        if err:
            return err
        return map_markdown(filter_pins(state, type_filter, status, max(1, min(limit, 500))))

    @mcp.tool()
    def plan_route(count: int = 5, types: str = "", include_signposts: bool = True,
                   max_radius: float = 0) -> str:
        """Оптимальный маршрут по ближайшим незачищенным точкам карты от текущей позиции Геральта
        (жадный ближайший сосед + 2-opt; места силы и сокровища в приоритете) и готовые команды
        для консоли игры: aimark("теги") отмечает точки на карте, aipin(x, y) ставит путевую метку
        на первую точку. count: число точек; types: фильтр типов через запятую (например
        'PlaceOfPower,сокровище'); include_signposts: включать неоткрытые указатели;
        max_radius: ограничение радиуса в метрах (0 = без ограничения)."""
        state, err = load_state()
        if err:
            return err
        return route_markdown(plan_route_impl(state, max(1, min(count, 30)), types,
                                              include_signposts, max_radius))

    @mcp.tool()
    def set_poi_note(tag: str, note: str = "", skip: bool | None = None) -> str:
        """Записать в базу poi_notes.json заметку о точке карты (что нужно: ключ, бомба, уровень,
        где лежит ключ, что внутри) и/или пометить точку skip=True, чтобы plan_route её не предлагал
        (skip=False — вернуть). tag — внутреннее имя точки из дампа/get_map_points."""
        return save_note(tag, note, skip)

    @mcp.tool()
    def get_guide(section: str = "") -> str:
        """Руководство для ИИ-гида (AI_GUIDE.md): правила роли, технические заметки по дампу,
        секреты и пропускаемый контент по регионам. СОДЕРЖИТ СПОЙЛЕРЫ — не пересказывать
        игроку концовки квестов. section: слово из заголовка/текста раздела (например
        'Белый Сад', 'Велен', 'Моды'); пусто = весь файл. Читать в начале разговора."""
        return read_guide(section)

    @mcp.tool()
    def witcher_log_status() -> str:
        """Диагностика: где лежит scriptslog.txt, его размер и есть ли в нём строки мода."""
        return log_status()

    mcp.run()


# ---------------------------------------------------------------- CLI
def main() -> None:
    global _LOG_OVERRIDE
    ap = argparse.ArgumentParser(description="The Witcher 3 state bridge for AI assistants")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--print", action="store_true", help="вывести состояние в Markdown")
    mode.add_argument("--json", action="store_true", help="вывести состояние в JSON")
    mode.add_argument("--map", action="store_true", help="вывести точки карты (Markdown)")
    mode.add_argument("--status", action="store_true", help="диагностика лога")
    mode.add_argument("--route", type=int, metavar="N", help="маршрут по N ближайшим точкам")
    mode.add_argument("--guide", nargs="?", const="", default=None, help="показать AI_GUIDE.md (или раздел)")
    ap.add_argument("--type", default="", help="фильтр типа точек для --map")
    ap.add_argument("--pins", default="todo", help="статус точек для --map: all|todo|hidden|open|done")
    ap.add_argument("--out", help="записать результат в файл вместо консоли")
    ap.add_argument("--log", help="путь к scriptslog.txt")
    args = ap.parse_args()
    _LOG_OVERRIDE = args.log

    if args.guide is not None:
        sys.stdout.reconfigure(encoding="utf-8")
        print(read_guide(args.guide))
        return

    if args.route:
        state, err = load_state()
        sys.stdout.reconfigure(encoding="utf-8")
        print(err or route_markdown(plan_route_impl(state, args.route, args.type)))
        return

    if not (args.print or args.json or args.map or args.status):
        run_mcp()
        return

    if args.status:
        text = log_status()
    else:
        state, err = load_state()
        if err:
            print(err, file=sys.stderr)
            sys.exit(1)
        if args.json:
            text = json.dumps(state, ensure_ascii=False, indent=2)
        elif args.map:
            text = map_markdown(filter_pins(state, args.type, args.pins, 500))
        else:
            text = to_markdown(state)

    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"Сохранено: {args.out}")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(text)


if __name__ == "__main__":
    main()
