# Початок роботи з чистою базою знань

Це авторитетний clean-install шлях для P.O.W.E.R. `v3.7.11`. Він створює лише
новий vault. Для наявних нотаток використовуйте
[гід міграції](migration-guide.ua.md), а не запускайте `power init` поверх них.

> **Контракт релізу:** використовуйте `v3.7.11` лише після появи signed tag та
> immutable wheel на [сторінці релізу GitHub](https://github.com/weby-homelab/power-framework/releases/tag/v3.7.11).
> Цей гід називає tag-bound target; сам URL не доводить завершення публікації.
> Перед установкою на не-Linux host
> перевірте [матрицю підтримки платформ](support-matrix.ua.md).

[Windows-гід](windows-11-installation.ua.md) є лише інформаційним. Windows і
macOS відкладені на невизначений строк і не є підтримуваними release-платформами
для `v3.7.11`.

## 1. Передумови

- Python 3.13 або 3.14 (`python3 --version`)
- `venv` і `pip` для цього інтерпретатора
- Доступ до GitHub Releases та налаштованого Python package index
- Git лише для встановлення з Git tag або source checkout

Використовуйте ізольований virtual environment. Для звичайного встановлення не
змінюйте системний Python і не покладайтеся на `--break-system-packages`.

## 2. Встановіть версіонований реліз

На Linux:

```bash
POWER_RELEASE_DIR="$HOME/.cache/power-release-3.7.11"
mkdir -p "$POWER_RELEASE_DIR"
gh release download v3.7.11 --repo weby-homelab/power-framework \
  --pattern 'power_framework-3.7.11-py3-none-any.whl' \
  --pattern 'power-native-requirements.txt' \
  --pattern 'power-release-manifest.json' \
  --dir "$POWER_RELEASE_DIR"

python3 -m venv "$HOME/.cache/power-3.7.11-venv"
POWER_PYTHON="$HOME/.cache/power-3.7.11-venv/bin/python"
POWER_CLI="$HOME/.cache/power-3.7.11-venv/bin/power"
POWER_WHEEL="$POWER_RELEASE_DIR/power_framework-3.7.11-py3-none-any.whl"
POWER_LOCK="$POWER_RELEASE_DIR/power-native-requirements.txt"
POWER_MANIFEST="$POWER_RELEASE_DIR/power-release-manifest.json"

"$POWER_PYTHON" -m pip install --require-hashes -r "$POWER_LOCK"
"$POWER_PYTHON" -m pip install --no-deps "$POWER_WHEEL"
```

Базовий release wheel залишається доступним як lean FTS-only library profile.
Офіційна команда Profile A вище встановлює обов'язковий extra `mcp`; `semantic`
додавайте лише для явно обраного локального dense-пошуку.

Перевірте executable, package metadata та lean import:

```bash
"$POWER_CLI" --version
"$POWER_PYTHON" -c \
  'from importlib.metadata import version; print(version("power-framework"))'
"$POWER_PYTHON" -c \
  'import power_framework; print("lean FTS import: OK")'
```

Обидві команди версії мають показати `3.7.11`, а остання команда —
`lean FTS import: OK`.

Для канонічних managed native launchers спочатку перегляньте dry-run, а потім
явно застосуйте точний release plan:

```bash
"$POWER_CLI" integrations install \
  --home "$HOME" \
  --power-wheel "$POWER_WHEEL" \
  --manifest "$POWER_MANIFEST" \
  --dependency-lock "$POWER_LOCK"
"$POWER_CLI" integrations install \
  --home "$HOME" \
  --power-wheel "$POWER_WHEEL" \
  --manifest "$POWER_MANIFEST" \
  --dependency-lock "$POWER_LOCK" \
  --apply --approved
POWER_CLI="$HOME/.local/bin/power"
```

### Альтернатива: встановлення із закріпленого tag

Цей шлях потребує Git:

```bash
"$POWER_PYTHON" -m pip install \
  'git+https://github.com/weby-homelab/power-framework.git@v3.7.11'
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
вибраному mode не пройдуть на цільовому хості. Явний mode важливий: профіль
`auto` може повернути labelled FTS fallback. FTS залишається доступним, якщо
dense model gate працює fail-closed.

## 7. Налаштуйте MCP для AI-агента

MCP server потребує одного наявного налаштованого vault root. Вкажіть той самий
interpreter virtual environment:

```json
{
  "mcpServers": {
    "power": {
      "command": "/home/YOU/.local/share/power/venv/bin/power-mcp",
      "args": [],
      "env": {
        "POWER_VAULT_DIR": "/home/YOU/Documents/power-vault"
      }
    }
  }
}
```

Перевірте точний interpreter і vault перед перезапуском клієнта:

```bash
POWER_VAULT_DIR="$POWER_VAULT" "$HOME/.local/share/power/venv/bin/power-mcp" preflight
```

Після зміни конфігурації або Python environment перезапустіть long-lived
MCP-клієнт. Повний контракт 20 інструментів і stdio security boundary
описано в [MCP Server](mcp-server.md).

Web UI не є окремим native-продуктом: він постачається тим самим wheel і
запускається лише у Web-only контейнері, описаному в
[контракті розгортання Profile B](architecture/unified-runtime.md).

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

- Python має версію 3.13 або 3.14, а interpreter належить окремому venv.
- CLI та distribution metadata повертають `3.7.11`.
- `power_framework` імпортується, а офіційний Profile A містить extra `mcp`.
- MCP preflight успішно імпортує `power_framework.mcp` через launcher `power-mcp`.
- `init`, `ingest`, `index --strict`, `lint` і `markdown-check` завершуються з
  кодом `0`.
- FTS sync завершується з кодом `0`, а FTS search повертає першу нотатку.
- MCP preflight використовує той самий interpreter і друкує
  `MCP preflight: OK`.
- Dense/reranked readiness записується лише після проходження optional gate на
  цільовому хості.
