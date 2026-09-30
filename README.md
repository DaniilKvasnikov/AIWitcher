# AI Witcher

Мост между **The Witcher 3: Wild Hunt** и ИИ-ассистентами. Мод выгружает состояние Геральта (уровень, опыт, навыки, снаряжение, квесты, инвентарь, регион), а небольшой Python-скрипт отдаёт эти данные нейросети — через [MCP](https://modelcontextprotocol.io) (Claude Desktop, Claude Code и другие MCP-клиенты) или просто как Markdown/JSON для любой другой модели.

Спросите «что мне качать дальше?» или «куда идти по квесту?» — и ассистент ответит, видя ваш реальный прогресс.

*English summary below.*

---

## Как это работает

```
Игра ── команда aidump ──> scriptslog.txt ──> witcher_mcp.py ──> Claude / ChatGPT / локальная LLM
         (мод modAIWitcher)   (лог скриптов)     (MCP или текст)
```

У скриптов Ведьмака нет доступа к файлам, поэтому мод пишет данные в стандартный лог скриптов игры (он ведётся при запуске с флагом `-debugscripts`) с меткой `AIW|`. Python-скрипт находит в логе последний завершённый дамп и преобразует его в читаемый вид.

Мод ничего не меняет в игре и не трогает сохранения: он добавляет только новые функции, не редактируя оригинальные скрипты.

## Что выгружается

- **Персонаж:** уровень, опыт и сколько нужно до следующего уровня, свободные очки навыков, здоровье, токсичность, кроны
- **Мир:** регион, координаты, игровое время
- **Надетое снаряжение:** мечи, броня, арбалет
- **Изученные навыки** с уровнями (внутренние имена игры)
- **Квесты:** отслеживаемый и все активные, с типом
- **Инвентарь:** названия и количество

Названия предметов и квестов выводятся на языке игры.

## Совместимость

| Версия игры | Статус |
| --- | --- |
| Remastered 5.00b (DX12, Steam) | ✅ проверено |
| Next-Gen 4.0x | должно работать (API скриптов совпадает), не проверялось |
| Classic 1.32 | не проверялось |

Нужны Windows и Python 3.10+.

---

## Быстрая установка (только мод)

Скачайте `AIWitcher-mod-vX.Y.Z.zip` со страницы [Releases](https://github.com/DaniilKvasnikov/AIWitcher/releases/latest) и распакуйте в папку игры, затем выполните шаги 2–3 ниже. Python-часть нужна для подключения к нейросети: клонируйте репозиторий или скачайте *Source code* из того же релиза.
## Установка

### 1. Мод

Скопируйте папку `mod/modAIWitcher` в папку `Mods` внутри папки игры (создайте `Mods`, если её нет):

```
<папка игры>\Mods\modAIWitcher\content\scripts\local\aiwitcher.ws
```

Папка игры — та, где лежат `bin`, `content` и `DLC`. В Steam: ПКМ по игре → *Управление* → *Просмотреть локальные файлы*.

> Мод не конфликтует с другими скриптовыми модами, так как не меняет оригинальные файлы игры, поэтому Script Merger не нужен.

### 2. Флаг запуска

Steam → ПКМ по игре → *Свойства* → *Общие* → *Параметры запуска*:

```
--launcher-skip -debugscripts
```

`--launcher-skip` пропускает REDlauncher и гарантирует, что `-debugscripts` дойдёт до игры. Флаг не отключает достижения.

### 3. Консоль разработчика

Откройте `<папка игры>\bin\config\base\general.ini` и добавьте в конец строку:

```
DBGConsoleOn=true
```

*(Сначала сделайте копию файла.)*

### 4. Python-часть

```bash
cd mcp_server
pip install -r requirements.txt
```

### 5. Проверка

1. Запустите игру. Первый запуск дольше обычного: игра компилирует скрипты.
2. Загрузите сохранение, откройте консоль (`~`, на некоторых раскладках `F2`) и введите:
   ```
   aidump
   ```
   Внизу экрана появится **«AI dump: OK»**.
3. Проверьте, что данные читаются:
   ```bash
   python mcp_server/witcher_mcp.py --print
   ```

---

## Использование

### Вариант А — Claude Desktop (MCP)

Откройте *Settings → Developer → Edit Config* и добавьте сервер (пример в [`examples/claude_desktop_config.json`](examples/claude_desktop_config.json)):

```json
{
  "mcpServers": {
    "witcher3": {
      "command": "python",
      "args": ["C:\\path\\to\\AIWitcher\\mcp_server\\witcher_mcp.py"]
    }
  }
}
```

Если `python` не в PATH или используется Anaconda/venv, укажите полный путь к `python.exe`. Затем полностью перезапустите Claude Desktop.

Теперь в игре вводите `aidump` и спрашивайте Claude о чём угодно — он сам вызовет инструмент `get_witcher_state`.

**Инструменты MCP:**

| Инструмент | Что делает |
| --- | --- |
| `get_witcher_state` | последний снимок состояния персонажа |
| `witcher_log_status` | диагностика: найден ли лог и есть ли в нём данные мода |

### Вариант Б — Claude Code и другие MCP-клиенты

```bash
claude mcp add witcher3 -- python C:\path\to\AIWitcher\mcp_server\witcher_mcp.py
```

Любой клиент с поддержкой MCP по stdio (Cursor, LM Studio, Open WebUI через mcpo и т.д.) подключается так же: команда `python`, аргумент — путь к `witcher_mcp.py`.

### Вариант В — любая нейросеть без MCP

Выгрузите состояние в файл и вставьте или прикрепите его в чат ChatGPT, Gemini, DeepSeek, локальной модели и т.п.:

```bash
python mcp_server/witcher_mcp.py --print                  # Markdown в консоль
python mcp_server/witcher_mcp.py --print --out state.md   # Markdown в файл
python mcp_server/witcher_mcp.py --json  --out state.json # JSON (для своих скриптов и агентов)
python mcp_server/witcher_mcp.py --status                 # диагностика
```

Пример вывода — [`examples/sample_output.md`](examples/sample_output.md).

### Параметры

| Что | Как |
| --- | --- |
| Свой путь к логу | `--log "D:\...\scriptslog.txt"` или переменная окружения `W3_SCRIPTSLOG` |
| Где лог по умолчанию | `Документы\The Witcher 3\scriptslog.txt` (OneDrive-варианты тоже проверяются) |

---

## Решение проблем

**Ошибка компиляции скриптов при запуске игры.** Текст ошибки содержит файл и номер строки. Скорее всего, обновление игры изменило функцию, которую использует мод. Откройте `aiwitcher.ws` и закомментируйте (`//`) вызов проблемного блока в функции `AIW_Dump()`, например `//AIW_DumpSkills(witcher);`. Остальные блоки продолжат работать. Если хотите вовсе убрать мод — удалите `Mods\modAIWitcher`.

**`Лог не найден` / `нет завершённого дампа`.**
- Проверьте, что `-debugscripts` дошёл до игры: в PowerShell при запущенной игре выполните
  `Get-CimInstance Win32_Process -Filter "Name='witcher3.exe'" | Select CommandLine`
- Если лог пустой, удалите файлы `*.redscripts` в `<папка игры>\content\content0\` и перезапустите игру. Они пересоздадутся.
- Убедитесь, что после загрузки сейва вы ввели `aidump`.

**Консоль не открывается.** Проверьте строку `DBGConsoleOn=true` в `general.ini`. Клавиша зависит от раскладки: `~`, `F2` или `ё`.

**Пустые названия предметов.** Это служебные предметы без локализованного имени. Для них выводится внутренний идентификатор.

## Удаление

1. Удалите `<папка игры>\Mods\modAIWitcher`.
2. Уберите `-debugscripts` (и при желании `--launcher-skip`) из параметров запуска.
3. Уберите `DBGConsoleOn=true` из `general.ini`.
4. Уберите блок `witcher3` из конфига MCP-клиента.

## Структура репозитория

```
mod/modAIWitcher/content/scripts/local/aiwitcher.ws   скрипт мода (WitcherScript)
mcp_server/witcher_mcp.py                             MCP-сервер и CLI
mcp_server/requirements.txt
examples/                                             пример конфига и вывода
```

## Идеи на будущее

- автоматический дамп при сохранении игры
- текущая цель квеста и отметки на карте
- кнопка в меню вместо консольной команды
- читаемые названия навыков

## Лицензия

Код — [MIT](LICENSE). The Witcher 3 и связанные материалы принадлежат CD PROJEKT RED. Проект неофициальный, не связан с CD PROJEKT RED и не одобрен ею, и распространяется некоммерчески в соответствии с их правилами для фанатского контента.

---

## English summary

**AI Witcher** lets AI assistants see your Witcher 3 progress. The `modAIWitcher` script mod adds an `aidump` console command that writes Geralt's level, XP, skills, gear, quests, inventory and location to the game's script log. `mcp_server/witcher_mcp.py` reads the latest dump and serves it as an **MCP server** (`get_witcher_state` tool) for Claude Desktop, Claude Code or any MCP client, or prints it as **Markdown / JSON** (`--print`, `--json`) for any other LLM.

Setup: copy `mod/modAIWitcher` to `<game>\Mods\`, add `--launcher-skip -debugscripts` to the launch options, add `DBGConsoleOn=true` to `bin\config\base\general.ini`, run `pip install -r mcp_server/requirements.txt`, then load a save and type `aidump` in the console. Tested on The Witcher 3 Remastered 5.00b (DX12).
