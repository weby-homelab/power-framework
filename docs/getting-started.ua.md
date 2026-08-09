# Початок роботи з чистою базою знань

Це авторитетний clean-install шлях для P.O.W.E.R. `v3.4.0`. Він створює лише
новий vault. Для наявних нотаток використовуйте
[гід міграції](migration-guide.ua.md), а не запускайте `power init` поверх них.

Користувачам Windows 11 25H2 потрібно виконати повний
[Windows-гід](windows-11-installation.ua.md) з точними PowerShell-шляхами та
MCP acceptance checks.

## 1. Передумови

- Python 3.11 або новіший (`python3 --version`)
- `venv` і `pip` для цього інтерпретатора
- Доступ до GitHub Releases та налаштованого Python package index
- Git лише для встановлення з Git tag або source checkout

Використовуйте ізольований virtual environment. Для звичайного встановлення не
змінюйте системний Python і не покладайтеся на `--break-system-packages`.

## 2. Встановіть версіонований реліз

На Linux або macOS:

```bash
python3 -m venv "$HOME/.local/share/power-framework/venv"
POWER_PYTHON="$HOME/.local/share/power-framework/venv/bin/python"
POWER_CLI="$HOME/.local/share/power-framework/venv/bin/power"

"$POWER_PYTHON" -m pip install --upgrade pip
"$POWER_PYTHON" -m pip install \
  https://github.com/weby-homelab/power-framework/releases/download/v3.4.0/power_framework-3.4.0-py3-none-any.whl
```

Release wheel фіксує версію вихідного коду P.O.W.E.R. Його залежності
вирішуються через налаштований Python package index.

Перевірте executable, package metadata та MCP import:

```bash
"$POWER_CLI" --version
"$POWER_PYTHON" -c \
  'from importlib.metadata import version; print(version("power-framework"))'
"$POWER_PYTHON" -c \
  'import power_framework.mcp, onnxruntime; print("imports: OK")'
```

Обидві команди версії мають показати `3.4.0`, а остання команда —
`imports: OK`.

### Альтернатива: встановлення із закріпленого tag

Цей шлях потребує Git:

```bash
"$POWER_PYTHON" -m pip install \
  'git+https://github.com/weby-homelab/power-framework.git@v3.4.0'
```

Не використовуйте незакріплений `main`, якщо важлива відтворюваність.

## 3. Ініціалізуйте порожній vault

Оберіть новий шлях. `power init` навмисно відмовляється працювати з непорожнім
каталогом.

```bash
POWER_VAULT="$HOME/Documents/power-vault"
"$POWER_CLI" init "$POWER_VAULT"
```

Команда створює канонічну структуру:

```text
power-vault/
├── 00_Inbox/
├── 01_Projects/
├── 02_Areas/
├── 03_Resources/
├── 04_Archive/
├── 05_Templates/
│   └── default.md
├── 06_Daily_Logs/
├── PROTOCOLS/
├── index.md
└── log.md
```

Каталоги `_index.md` у canonical і вкладених теках створює `power index`, а не
`power init`; великі каталоги розбиваються на обмежені сторінки `_index-N.md`.

## 4. Додайте першу нотатку

```bash
"$POWER_CLI" ingest "$POWER_VAULT" \
  --type Resource \
  --title "First note" \
  --description "Clean-install acceptance note" \
  --tags power acceptance
```

Підтримувані типи: `Project`, `Area`, `Resource`, `Daily Log`, `Archive` і
`System Guide`. `power ingest` маршрутизує їх у канонічні папки POWER.

## 5. Виконайте acceptance gate чистого vault

```bash
"$POWER_CLI" index "$POWER_VAULT" --strict
"$POWER_CLI" lint "$POWER_VAULT"
"$POWER_CLI" markdown-check "$POWER_VAULT"
```

Усі три команди мають завершитися з кодом `0`. Попередження про orphan для
першої нотатки без inbound links є інформаційним; невалідні OKF-метадані та
биті внутрішні посилання неприпустимі.

Побудуйте та перевірте легкий пошук без dense models:

```bash
"$POWER_CLI" sync "$POWER_VAULT" --fts-only
"$POWER_CLI" search "$POWER_VAULT" "acceptance" --mode fts
```

Результат має містити `First note`.

## 6. Опційний dense-пошук

Перша повна синхронізація завантажує й перевіряє pinned model assets і може
потребувати значного часу, мережевого трафіку, диска та пам'яті:

```bash
"$POWER_CLI" sync "$POWER_VAULT"
"$POWER_CLI" search "$POWER_VAULT" "clean installation" --mode semantic
```

Не заявляйте готовність semantic або reranked mode, доки full sync і пошук у
вибраному mode не пройдуть на цільовому хості. FTS залишається доступним, якщо
dense model gate працює fail-closed.

## 7. Налаштуйте MCP для AI-агента

MCP server потребує одного наявного налаштованого vault root. Вкажіть той самий
interpreter virtual environment:

```json
{
  "mcpServers": {
    "power": {
      "command": "/home/YOU/.local/share/power-framework/venv/bin/python",
      "args": ["-m", "power_framework.mcp"],
      "env": {
        "POWER_VAULT_DIR": "/home/YOU/Documents/power-vault"
      }
    }
  }
}
```

Перевірте точний interpreter і vault перед перезапуском клієнта:

```bash
POWER_VAULT_DIR="$POWER_VAULT" "$POWER_PYTHON" -c \
  'import os; from pathlib import Path; import power_framework.mcp; p=Path(os.environ["POWER_VAULT_DIR"]); assert p.is_dir(); print("MCP preflight: OK")'
```

Після зміни конфігурації або Python environment перезапустіть long-lived
MCP-клієнт. Повний контракт 17 інструментів і transport security boundary
описано в [MCP Server](mcp-server.md).

## 8. Щоденна послідовність

Після зміни нотаток:

```bash
"$POWER_CLI" index "$POWER_VAULT" --strict
"$POWER_CLI" lint "$POWER_VAULT"
"$POWER_CLI" markdown-check "$POWER_VAULT"
```

Запускайте `power sync`, коли змінився набір searchable sources і потрібне
оновлення FTS/dense index. Спочатку читайте `index.md`, потім релевантний
канонічний `_index.md`; не завантажуйте всі Markdown-файли лише для discovery.

## 9. Оновлення або видалення

Оновлюйтеся до явно обраного релізу й повторюйте acceptance gate. Щоб видалити
Python application, не видаляючи vault:

```bash
"$POWER_PYTHON" -m pip uninstall power-framework
```

Vault — це звичайні Markdown-файли, незалежні від Python runtime. Зробіть backup
перед видаленням будь-якої з цих локацій.

## Acceptance checklist

- Python має версію 3.11+, а interpreter належить окремому venv.
- CLI та distribution metadata повертають `3.4.0`.
- `power_framework.mcp` і `onnxruntime` імпортуються успішно.
- `init`, `ingest`, `index --strict`, `lint` і `markdown-check` завершуються з
  кодом `0`.
- FTS sync завершується з кодом `0`, а FTS search повертає першу нотатку.
- MCP preflight використовує той самий interpreter і друкує
  `MCP preflight: OK`.
- Dense/reranked readiness записується лише після проходження optional gate на
  цільовому хості.
