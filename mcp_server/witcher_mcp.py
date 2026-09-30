"""
AI Witcher - bridge between The Witcher 3 and AI assistants.

Reads the latest state dump written by the modAIWitcher game mod
into scriptslog.txt and exposes it:
  * as an MCP server (Claude Desktop, Claude Code, any MCP client):
        python witcher_mcp.py
  * as plain text for any other AI (ChatGPT, local LLMs, ...):
        python witcher_mcp.py --print          # Markdown
        python witcher_mcp.py --json           # JSON
        python witcher_mcp.py --print --out state.md

Log path can be overridden with the W3_SCRIPTSLOG environment variable
or the --log argument.
"""
import argparse
import json
import os
import sys
from pathlib import Path

TAIL_BYTES = 8 * 1024 * 1024  # the log can be huge, read only the tail
MARK = "AIW|"

QUEST_TYPES = {"0": "Сюжетный", "1": "Глава", "2": "Побочный",
               "3": "Заказ на чудовище", "4": "Поиск сокровищ"}

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
def parse_dump(rows: list[list[str]]) -> dict:
    state = {"character": {}, "world": {}, "equipped": [], "skills": [],
             "tracked_quest": None, "quests": [], "inventory": [], "errors": []}
    for kind, *f in rows:
        if kind == "CHAR" and len(f) >= 2:
            state["character"][f[0]] = f[1]
        elif kind == "WORLD" and len(f) >= 2:
            state["world"][f[0]] = f[1]
        elif kind == "EQUIP" and len(f) >= 3:
            state["equipped"].append({"slot": f[0], "name": f[1], "id": f[2]})
        elif kind == "SKILL" and len(f) >= 2:
            state["skills"].append({"id": f[0], "level": int(f[1]) if f[1].isdigit() else f[1]})
        elif kind == "TRACKED" and f:
            state["tracked_quest"] = f[0]
        elif kind == "QUEST" and len(f) >= 2:
            state["quests"].append({"type": QUEST_TYPES.get(f[0], f[0]), "title": f[1]})
        elif kind == "ITEM" and len(f) >= 2:
            state["inventory"].append({
                "name": f[0], "count": int(f[1]) if f[1].isdigit() else f[1],
                "id": f[2] if len(f) > 2 else "",
            })
        elif kind == "ERROR":
            state["errors"].append("|".join(f))
    return state


def to_markdown(s: dict) -> str:
    out = ["# Состояние Геральта (The Witcher 3)"]
    if s["character"]:
        out.append("\n## Персонаж")
        out += [f"- {k}: {v}" for k, v in s["character"].items()]
    if s["world"]:
        out.append("\n## Мир")
        out += [f"- {k}: {v}" for k, v in s["world"].items()]
    if s["equipped"]:
        out.append("\n## Надето")
        out += [f"- {e['name']} ({e['id']})" for e in s["equipped"]]
    if s["skills"]:
        out.append("\n## Изученные навыки (внутреннее имя: уровень)")
        out += [f"- {k['id']}: {k['level']}" for k in s["skills"]]
    if s["tracked_quest"] or s["quests"]:
        out.append("\n## Квесты")
        if s["tracked_quest"]:
            out.append(f"- ОТСЛЕЖИВАЕТСЯ: {s['tracked_quest']}")
        out += [f"- [{q['type']}] {q['title']}" for q in s["quests"]]
    if s["inventory"]:
        out.append(f"\n## Инвентарь ({len(s['inventory'])} позиций)")
        for it in s["inventory"]:
            if it["name"].strip():
                out.append(f"- {it['name']} x{it['count']}")
            else:
                out.append(f"- [служебный/без названия] {it['id'] or '?'} x{it['count']}")
    if s["errors"]:
        out.append("\n## Ошибки мода")
        out += [f"- {e}" for e in s["errors"]]
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
        """Возвращает последний снимок состояния игрока в The Witcher 3: уровень, опыт,
        очки навыков, здоровье, деньги, регион, надетое снаряжение, изученные навыки,
        активные квесты и инвентарь. Снимок создаётся в игре командой aidump."""
        state, err = load_state()
        return err or to_markdown(state)

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
    mode.add_argument("--status", action="store_true", help="диагностика лога")
    ap.add_argument("--out", help="записать результат в файл вместо консоли")
    ap.add_argument("--log", help="путь к scriptslog.txt")
    args = ap.parse_args()
    _LOG_OVERRIDE = args.log

    if not (args.print or args.json or args.status):
        run_mcp()
        return

    if args.status:
        text = log_status()
    else:
        state, err = load_state()
        if err:
            print(err, file=sys.stderr)
            sys.exit(1)
        text = json.dumps(state, ensure_ascii=False, indent=2) if args.json else to_markdown(state)

    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"Сохранено: {args.out}")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(text)


if __name__ == "__main__":
    main()
