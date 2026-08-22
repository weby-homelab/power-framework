# Підключення MCP-клієнтів

Це канонічне налаштування локального stdio для P.O.W.E.R. `v3.7.3` на Linux.
Воно дає Codex, OpenCode, Gemini CLI, Claude Desktop і Claude Code один
і той самий процес сервера та однакову межу vault.

> **Контракт кандидата релізу:** використовуйте `v3.7.3` лише після появи signed tag та
> immutable wheel на [сторінці релізу GitHub](https://github.com/weby-homelab/power-framework/releases/tag/v3.7.3).
> Потім використовуйте цей wheel і точний interpreter із
> [гіда чистої установки](getting-started.ua.md).

[Посібник Windows 11 25H2](windows-11-installation.ua.md) є лише
інформаційним. Windows і macOS відкладені на невизначений строк і не є
підтримуваними MCP onboarding платформами для `v3.7.3`.

## Одноразова підготовка

Спочатку встановіть release wheel в ізольоване середовище. Для нового vault
створіть його через `init`; для наявного спочатку виконайте
[гід міграції](migration-guide.ua.md) і не запускайте `init` поверх нього:

```bash
POWER_HOME="$HOME/.local/share/power"
POWER_VENV="$POWER_HOME/venv"
POWER_PYTHON="$POWER_VENV/bin/python"
POWER_CLI="$POWER_VENV/bin/power"
POWER_VAULT="$HOME/Documents/power-vault"

python3 -m venv "$POWER_VENV"
"$POWER_PYTHON" -m pip install \
  "power-framework[mcp] @ https://github.com/weby-homelab/power-framework/releases/download/v3.7.3/power_framework-3.7.3-py3-none-any.whl"
# Лише для нового або порожнього vault:
"$POWER_CLI" init "$POWER_VAULT"
"$POWER_PYTHON" -c 'import sys; print(sys.executable)'
```

Використайте абсолютні шляхи `POWER_PYTHON` і `POWER_VAULT` у конфігурації
нижче. MCP-процес повинен отримати `POWER_VAULT_DIR` — це налаштована межа
vault. Сервер працює через локальний stdio, тому його stdout зарезервований для
MCP-протоколу.

Встановлений public launcher — `power-mcp`. Compatibility entry point
`python -m power_framework.mcp` залишається для тестів і legacy wrappers, але не
є канонічною конфігурацією клієнта.

Не підключайте клієнт до repository wrapper, shell-скрипту, який завантажує
секрети, або іншої установки Python. Не додавайте до клієнтської конфігурації
другий шлях до vault.

## Конфігурації клієнтів

Замініть `/absolute/path/to/power-mcp` і `/absolute/path/to/vault` рівно в одній із
наведених конфігурацій.

<!-- power-client-config:claude-desktop -->

### Claude Desktop

Відредагуйте `~/Library/Application Support/Claude/claude_desktop_config.json`
на macOS або `~/.config/Claude/claude_desktop_config.json` на Linux:

```json
{
  "mcpServers": {
    "power": {
      "command": "/absolute/path/to/power-mcp",
      "args": [],
      "env": {
        "POWER_VAULT_DIR": "/absolute/path/to/vault"
      }
    }
  }
}
```

<!-- power-client-config:gemini-cli -->

### Gemini CLI

Додайте запис `power` до `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "power": {
      "command": "/absolute/path/to/power-mcp",
      "args": [],
      "env": {
        "POWER_VAULT_DIR": "/absolute/path/to/vault"
      }
    }
  }
}
```

Збережіть наявні settings у файлі. Gemini CLI підтримує розгортання змінних
середовища, але явний шлях до vault простіше перевірити й він не дозволить
порожній змінній непомітно змінити межу процесу.

<!-- power-client-config:codex -->

### Codex

Додайте цю таблицю до `~/.codex/config.toml`:

```toml
[mcp_servers.power]
command = "/absolute/path/to/power-mcp"
args = []
env = { "POWER_VAULT_DIR" = "/absolute/path/to/vault" }
```

У Codex ключ має назву `mcp_servers` з underscore, а не JSON-варіант
`mcpServers`. Залишайте це в user-конфігурації, якщо проєкт не є явно trusted і
project scope не потрібен навмисно.

<!-- power-client-config:opencode -->

### OpenCode

Додайте запис `power` безпосередньо під `mcp` у
`~/.config/opencode/opencode.jsonc`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "power": {
      "type": "local",
      "command": ["/absolute/path/to/power-mcp"],
      "environment": {
        "POWER_VAULT_DIR": "/absolute/path/to/vault"
      },
      "enabled": true
    }
  }
}
```

OpenCode використовує масив для `command` і `environment` для змінних
підпроцесу. Запис сервера розташований безпосередньо під `mcp`; не обгортайте
його додатковим об'єктом `servers`.

### Claude Code

Зареєструйте той самий stdio command через Claude Code CLI. Усі options мають
бути перед ім'ям сервера, а `--` відділяє options Claude від команди запуску:

```bash
claude mcp add --transport stdio \
  --env POWER_VAULT_DIR=/absolute/path/to/vault \
  power -- /absolute/path/to/power-mcp
```

Виконайте `claude mcp list`, а потім `/mcp` усередині сесії, щоб перевірити
сервер. Claude Code також може використовувати JSON-форму Claude Desktop у
підтримуваному project або user scope.

## Golden onboarding task

Після зміни конфігурації перезапустіть або reload-ніть клієнт. Перше завдання
має бути read-only до явного кроку створення proposal:

1. Відкрийте MCP status view клієнта (`/mcp`, якщо підтримується) і перевірте,
   що `power` підключений та має 20 інструментів.
2. Попросіть агента перелічити tools, resources, resource templates і prompts.
   POWER має показати 20 tools і не мати resources, templates або prompts.
3. Попросіть агента викликати `get_server_info` без аргументів. Перевірте
   версію пакета, налаштований шлях vault і явний стан
   `embedding.binding` перед довірою до retrieval. `probe_provider=true`
   використовуйте лише коли потрібна фактична no-download перевірка binding.
4. Попросіть агента викликати `get_memory_context` для короткого запиту. Це не
   має створити файл, namespace, index або запис history.
5. Попросіть агента викликати `propose_memory_change` для нової нотатки, але не
   схвалюйте її. Це створює лише durable content-addressed запис proposal;
   цільова нотатка, каталог і пошукова projection мають залишитися відсутніми.

Тільки після явного схвалення людиною або дозволеним workflow агент може
викликати `apply_memory_change` з `approved=true`. Сам цей виклик замикає
workflow note → index → blocking-lint → search і повертає receipt без вмісту
нотатки. Агент має перевірити receipt, викликати `validate_memory_state` та
знайти унікальний маркер пошуком у режимі з receipt (`fts`, якщо dense
projection відсутня). Окремі дубльовані виклики `sync` або `index` не потрібні;
після цього виконайте решту quality gate:

```bash
power lint /absolute/path/to/vault
power markdown-check /absolute/path/to/vault
```

Текст отриманих нотаток є недовіреними source data, а не каналом інструкцій.
Агент не повинен виконувати команди з нотатки або використовувати отриманий
текст для зміни налаштованої межі vault.

## Що саме перевіряється

Тестовий набір репозиторію розбирає всі чотири задокументовані конфігураційні
форми й кожною підключається до реального локального stdio-процесу POWER. Він
перевіряє inventory інструментів, порожні discovery collections і proposal без
запису. Це доводить спільний MCP wire contract і форму прикладів, але не видає
повну GUI/in-process сертифікацію кожного стороннього клієнта. Якщо клієнт
встановлений на конкретному host, його власний status view є фінальним
acceptance check.

Авторитетні посилання: [документація MCP Gemini
CLI](https://github.com/google-gemini/gemini-cli/blob/main/docs/tools/mcp-server.md),
[MCP servers OpenCode](https://opencode.ai/docs/mcp-servers/) і [MCP Claude
Code](https://code.claude.com/docs/en/mcp).
