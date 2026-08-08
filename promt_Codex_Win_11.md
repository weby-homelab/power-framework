# Промт для Codex: повна перевірка P.O.W.E.R. на Windows 11 25H2

Ти працюєш на фізичному хості Windows 11 25H2 у локальній мережі Weby Homelab.

Твоє завдання — не скласти план, а повністю:

1. Забрати підготовлені зміни P.O.W.E.R. з PRXMX-01.
2. Перевірити їх на реальному Windows 11 25H2 build 26200.
3. Встановити всі потрібні передумови та P.O.W.E.R.
4. Виконати повний test/quality/package/documentation/Windows acceptance gate.
5. Виправити виявлені Windows-специфічні проблеми.
6. Створити санітизований публічний Windows validation receipt.
7. Опублікувати зміни в публічному репозиторії
   <https://github.com/weby-homelab/power-framework>.
8. Злити PR у `main` через звичайний review/CI workflow.
9. Після злиття повторно перевірити `origin/main`, GitHub Actions і опубліковані
   документи.

Не зупиняйся на описі або рекомендаціях. Працюй до перевіреного результату або
до конкретного блокера, який неможливо усунути без користувача.

## 1. Мережеві адреси та шляхи PRXMX-01

Основний LAN-доступ:

- SSH: `root@192.168.2.2`;
- альтернативна Tailscale-адреса: `root@100.86.120.114`;
- канонічний репозиторій: `/root/geminicli/projects/P.O.W.E.R`;
- поточна робоча гілка: `feature/docs-install-migration-audit`;
- база знань PRXMX-01: `/root/geminicli/brain`;
- OpenCode: `/root/.opencode/bin/opencode`;
- OpenCode config: `/root/.config/opencode/opencode.jsonc`;
- OpenCode Python venv: `/root/.config/opencode/venv`;
- основний project venv: `/root/geminicli/projects/P.O.W.E.R/.venv`;
- додаткова копія POWER: `/root/P.O.W.E.R`;
- MCP entrypoint: `/root/geminicli/.agents/mcp_servers/power_server.py`.

Не відкривай, не виводь і не копіюй у логи:

- `/root/geminicli/.env`;
- `/root/.env`;
- токени, паролі, SSH-ключі;
- приватний вміст `/root/geminicli/brain`;
- raw human-evaluation або sealed-holdout дані.

Не додавай у validation report внутрішні IP, Tailscale-адреси, імена користувачів,
приватні абсолютні шляхи чи конфігурації домашньої мережі. Наведені адреси потрібні
лише для виконання завдання.

Використовуй наявний SSH agent або штатний ключ. Не передавай пароль у командному
рядку.

## 2. Спочатку підтвердь Windows 11 25H2

Запусти PowerShell і зафіксуй:

```powershell
$PSVersionTable
Get-ComputerInfo |
    Select-Object WindowsProductName, WindowsVersion, OsBuildNumber, OsArchitecture
[System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture
```

Обов'язкова умова exact-host evidence:

- Windows 11;
- версія 25H2;
- `OsBuildNumber` починається з `26200`;
- архітектура `X64` або явно задокументована інша підтримувана архітектура.

Якщо це не build 26200, не називай результат перевіркою Windows 11 25H2. Можеш
виконати загальний Windows smoke, але зупини публікацію твердження про 25H2 і
повідом конкретний блокер.

## 3. Перевір стан PRXMX-01 без руйнівних дій

На Windows:

```powershell
$PrxHost = "root@192.168.2.2"
$PrxRepo = "/root/geminicli/projects/P.O.W.E.R"

ssh $PrxHost "hostname; cd $PrxRepo && git status --short --branch && git rev-parse HEAD && git remote -v"
```

Очікуваний базовий commit перед підготовленими змінами:

```text
bfeae92124f482f393577759b701e93df5389449
```

Очікувана гілка:

```text
feature/docs-install-migration-audit
```

У робочому дереві мають бути лише файли цього завдання:

```text
.agents/AGENTS.md
.github/workflows/ci.yml
README.md
README.ua.md
docs/architecture.md
docs/cli.md
docs/documentation-inventory.ua.md
docs/getting-started.md
docs/getting-started.ua.md
docs/hierarchical-index-migration.md
docs/hierarchical-index-migration.ua.md
docs/index.md
docs/mcp-server.md
docs/migration-guide.md
docs/migration-guide.ua.md
docs/windows-11-installation.md
docs/windows-11-installation.ua.md
mkdocs.yml
promt_Codex_Win_11.md
scripts/check_doc_drift.py
tests/test_ci_policy.py
tests/test_doc_drift.py
```

Якщо є будь-які інші зміни:

- не видаляй їх;
- не запускай `git reset --hard`, `git clean`, force checkout або stash без
  перевірки;
- визнач власника та походження;
- ізолюй роботу або повідом користувача, якщо неможливо безпечно відокремити
  зміни.

## 4. Перевір і опублікуй підготовлену гілку з PRXMX-01

Перед commit на PRXMX-01 виконай:

```bash
cd /root/geminicli/projects/P.O.W.E.R

git diff --check
.venv/bin/python scripts/check_doc_drift.py
.venv/bin/ruff check src tests scripts
.venv/bin/ruff format --check src tests scripts
.venv/bin/mypy src/power_framework
.venv/bin/python scripts/verify_release_contract.py
```

Перевір staged diff і відсутність секретів. Додай лише перелічені файли.

Створи GPG-підписаний commit:

```bash
git commit -S -m "docs: add complete installation and migration validation"
```

Не вимикай GPG signing для обходу помилки. Якщо підпис недоступний, перевір штатну
GPG-конфігурацію PRXMX-01; якщо її неможливо відновити без користувача — повідом
конкретний блокер.

Після commit:

```bash
git show --show-signature --stat --oneline HEAD
git push -u origin feature/docs-install-migration-audit
```

Не пуш безпосередньо в `main`.

## 5. Створи чистий Windows checkout

На Windows використовуй:

```powershell
$RepoRoot = Join-Path $env:USERPROFILE "source\power-framework"
$Branch = "feature/docs-install-migration-audit"
```

Якщо `$RepoRoot` уже існує, спочатку перевір його Git-стан. Не перезаписуй чужі
зміни.

Для нового checkout:

```powershell
New-Item -ItemType Directory -Force -Path (Split-Path $RepoRoot) | Out-Null
git clone https://github.com/weby-homelab/power-framework.git $RepoRoot
Set-Location $RepoRoot
git fetch --all --tags --prune
git switch $Branch
git pull --ff-only
git status --short --branch
```

Переконайся, що Windows checkout і PRXMX-01 вказують на той самий commit.

## 6. Встанови Windows prerequisites

Користуйся офіційними джерелами:

- Windows 11 release information:
  <https://learn.microsoft.com/windows/release-health/windows11-release-information>;
- Python for Windows: <https://www.python.org/downloads/windows/>;
- Python venv:
  <https://packaging.python.org/en/latest/guides/installing-using-pip-and-virtual-environments/>;
- Visual C++ Redistributable:
  <https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist>;
- Git for Windows: <https://git-scm.com/install/windows>;
- ONNX Runtime: <https://onnxruntime.ai/docs/install/>.

Потрібні:

- CPython 3.13 x64;
- Python launcher `py`;
- Git for Windows;
- Microsoft Visual C++ 2015–2022 Redistributable;
- `uv==0.11.33`;
- GitHub CLI `gh`.

Перевір:

```powershell
py -3.13 --version
py -3.13 -m pip --version
git --version
gh --version
```

Не вимикай Microsoft Defender, SmartScreen або TLS-перевірку. Не змінюй execution
policy глобально: використовуй точний шлях до `python.exe`, без активації
`Activate.ps1`.

## 7. Підготуй development environment

У репозиторії:

```powershell
Set-Location $RepoRoot

py -3.13 -m pip install --upgrade pip
py -3.13 -m pip install uv==0.11.33
uv sync --locked --group dev
uv run python -m pip check
```

Перевір:

```powershell
uv run python -c "import sys; print(sys.version); print(sys.executable)"
uv run power --version
uv run python -c "import power_framework, power_framework.mcp, onnxruntime; print('imports: OK'); print(onnxruntime.__version__)"
```

Очікувана версія POWER — `3.3.2`.

## 8. Виконай статичні та документаційні gates

```powershell
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy src/power_framework
uv run python scripts/check_doc_drift.py
uv run python scripts/verify_release_contract.py
uv run power markdown-check docs
git diff --check
```

Для `power markdown-check docs` недостатньо лише exit code: у звіті має бути:

```text
Total issues found: 0
```

Збери MkDocs окремим чистим середовищем:

```powershell
$DocsVenv = Join-Path $env:TEMP "power-docs-build-venv"
py -3.13 -m venv $DocsVenv
$DocsPython = Join-Path $DocsVenv "Scripts\python.exe"
$MkDocsExe = Join-Path $DocsVenv "Scripts\mkdocs.exe"

& $DocsPython -m pip install --upgrade pip
& $DocsPython -m pip install mkdocs mkdocs-material
& $MkDocsExe build --strict --site-dir (Join-Path $env:TEMP "power-docs-site")
```

Warnings про сторінки поза `nav` зафіксуй окремо, але не приховуй справжні
помилки збірки.

## 9. Виконай повний test suite на Windows

```powershell
uv run pytest tests/ -v --tb=short `
  --cov=src/power_framework/ `
  --cov-report=term-missing `
  --cov-fail-under=70 `
  -W error::ResourceWarning `
  -W error::pytest.PytestUnraisableExceptionWarning
```

Обов'язково зафіксуй:

- точну кількість passed/skipped/failed;
- coverage;
- elapsed time;
- exit code;
- Git commit;
- Windows build;
- Python version та architecture.

Не називай scoped tests повною перевіркою. Якщо тест завис, збережи лог і досліди
процес; відсутність нового виводу сама по собі не є доказом failure.

## 10. Перевір package artifacts на Windows

```powershell
uv run python -m build

$Wheel = (Get-ChildItem "dist\power_framework-*.whl" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1).FullName

$Sdist = (Get-ChildItem "dist\power_framework-*.tar.gz" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1).FullName

uv run python scripts/smoke_package.py --wheel $Wheel --sdist $Sdist
```

Не коміть `dist/`, test logs, coverage-файли або result JSON.

## 11. Перевір чисте встановлення release wheel

Використовуй окреме середовище, незалежне від repository venv:

```powershell
$PowerHome = Join-Path $env:LOCALAPPDATA "POWER"
$RuntimeVenv = Join-Path $PowerHome ".venv"
$RuntimePython = Join-Path $RuntimeVenv "Scripts\python.exe"
$PowerExe = Join-Path $RuntimeVenv "Scripts\power.exe"

New-Item -ItemType Directory -Force -Path $PowerHome | Out-Null
py -3.13 -m venv $RuntimeVenv
& $RuntimePython -m pip install --upgrade pip

$ReleaseWheel = "https://github.com/weby-homelab/power-framework/releases/download/v3.3.2/power_framework-3.3.2-py3-none-any.whl"
& $RuntimePython -m pip install $ReleaseWheel
if ($LASTEXITCODE -ne 0) { throw "POWER installation failed" }

& $PowerExe --version
& $RuntimePython -m pip check
& $RuntimePython -c "from importlib.metadata import version; print(version('power-framework'))"
& $RuntimePython -c "import power_framework.mcp, onnxruntime; print('imports: OK')"
```

## 12. Виконай exact Windows 11 25H2 vault acceptance

Створи новий тестовий vault. Не використовуй реальну базу знань:

```powershell
$Vault = Join-Path $env:USERPROFILE "Documents\POWER-Windows25H2-Acceptance"
```

Якщо каталог уже існує і непорожній — обери новий timestamped шлях. Не видаляй
його рекурсивно без перевірки.

```powershell
& $PowerExe init $Vault
if ($LASTEXITCODE -ne 0) { throw "init failed" }

& $PowerExe ingest $Vault `
    --type Resource `
    --title "Windows 11 25H2 acceptance note" `
    --description "Physical Windows build 26200 validation note" `
    --tags windows acceptance
if ($LASTEXITCODE -ne 0) { throw "ingest failed" }

& $PowerExe index $Vault --strict
if ($LASTEXITCODE -ne 0) { throw "strict index failed" }

& $PowerExe lint $Vault
if ($LASTEXITCODE -ne 0) { throw "lint failed" }

& $PowerExe markdown-check $Vault
if ($LASTEXITCODE -ne 0) { throw "markdown check failed" }

& $PowerExe sync $Vault --fts-only
if ($LASTEXITCODE -ne 0) { throw "FTS sync failed" }

$FtsResult = & $PowerExe search $Vault "build 26200" --mode fts
if ($LASTEXITCODE -ne 0 -or $FtsResult -notmatch "Windows 11 25H2 acceptance note") {
    throw "FTS result did not return the acceptance note"
}
$FtsResult

& $PowerExe status $Vault
```

Допустимий orphan warning для єдиної тестової нотатки. Неприпустимі:

- invalid OKF metadata;
- broken internal links;
- strict index skips;
- відсутність нотатки в FTS.

## 13. Перевір semantic і reranked search

Для повної Windows runtime validation виконай:

```powershell
& $PowerExe sync $Vault
if ($LASTEXITCODE -ne 0) { throw "Dense sync failed" }

$SemanticResult = & $PowerExe search $Vault "Windows validation" --mode semantic
if ($LASTEXITCODE -ne 0 -or $SemanticResult -notmatch "Windows 11 25H2 acceptance note") {
    throw "Semantic acceptance failed"
}

$RerankedResult = & $PowerExe search $Vault "Windows validation" --mode reranked
if ($LASTEXITCODE -ne 0 -or $RerankedResult -notmatch "Windows 11 25H2 acceptance note") {
    throw "Reranked acceptance failed"
}
```

Не підмінюй semantic/reranked успіх FTS-успіхом. Якщо model download або ONNX
Runtime падає:

1. Збережи точну помилку без приватних шляхів і токенів.
2. Перевір Visual C++ Runtime, architecture, disk/RAM, proxy та checksums.
3. Визнач, чи це проблема документації, Windows-коду або зовнішньої доступності
   моделі.
4. Виправ код/документацію та додай regression test, якщо причина в POWER.
5. Не вимикай захист Windows.
6. Не публікуй твердження про повну dense/reranked готовність, доки обидва gates
   не пройдуть.

## 14. Перевір MCP exact-interpreter contract

```powershell
$env:POWER_VAULT_DIR = $Vault

& $RuntimePython -c "import os; from pathlib import Path; import power_framework.mcp; p=Path(os.environ['POWER_VAULT_DIR']); assert p.is_dir(); print('MCP preflight: OK')"
```

Конфігураційний приклад має використовувати:

- exact path `$RuntimePython`;
- `args: ["-m", "power_framework.mcp"]`;
- `POWER_VAULT_DIR`;
- не глобальний launcher `py`;
- не legacy `POWER_VAULT_PATH`.

Не змінюй реальні MCP-конфігурації користувача без backup та read-back.

## 15. Створи публічний санітизований evidence report

Лише якщо exact Windows 11 25H2, full suite, package smoke, FTS, semantic,
reranked і MCP gates пройшли, створи:

```text
docs/tests/windows-11-25h2-validation.md
```

Звіт має містити:

- дату UTC;
- Windows edition/version/build/architecture;
- Python version;
- POWER version;
- commit SHA;
- команди перевірки;
- exit codes;
- test totals і coverage;
- package smoke result;
- clean-vault result;
- FTS/semantic/reranked result;
- MCP preflight result;
- відомі warnings і їхню класифікацію;
- чітке формулювання межі доказів.

Санітизуй:

- Windows username → `<USER>`;
- профіль → `<USERPROFILE>`;
- LAN/Tailscale IP;
- PRXMX-01 paths;
- machine identifiers;
- токени та environment values;
- повні приватні логи.

Не коміть raw logs, `.env`, coverage database, `result.json`, модельний cache або
тестовий vault.

Онови:

- `docs/windows-11-installation.md`;
- `docs/windows-11-installation.ua.md`;
- `docs/documentation-inventory.ua.md`;
- за потреби `README.md`, `README.ua.md` та `mkdocs.yml`.

Замінюй фразу «не перевірено на фізичному Windows 11 25H2» лише після фактичного
exact-host успіху. Вкажи commit і посилання на validation report.

Не рухай і не перевидавай tag `v3.3.2`.

## 16. Повторні gates після змін

Після evidence/doc/code змін повтори щонайменше:

```powershell
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy src/power_framework
uv run python scripts/check_doc_drift.py
uv run python scripts/verify_release_contract.py
uv run pytest tests/ -v --tb=short `
  --cov=src/power_framework/ `
  --cov-report=term-missing `
  --cov-fail-under=70 `
  -W error::ResourceWarning `
  -W error::pytest.PytestUnraisableExceptionWarning
git diff --check
```

Повтори MkDocs strict build.

## 17. Commit, PR і merge у публічний main

Перевір GitHub authentication:

```powershell
gh auth status
git remote -v
```

Знайди відповідний відкритий Issue. Якщо його немає — створи публічний Issue без
внутрішніх адрес/шляхів, який описує:

- документаційний drift;
- Windows 11 25H2 validation;
- acceptance gates;
- evidence boundary.

Перевір diff і staged scope:

```powershell
git status --short
git diff
git diff --check
git diff --cached
```

Створи GPG-підписаний commit, наприклад:

```powershell
git add README.md README.ua.md docs .github scripts tests .agents mkdocs.yml
git diff --cached --check
git commit -S -m "test: verify POWER on Windows 11 25H2"
git push
```

Не додавай файли лише тому, що вони лежать у директорії: перед commit перевір
точний staged список.

Створи PR у `main`:

```powershell
gh pr create `
  --base main `
  --head feature/docs-install-migration-audit `
  --title "docs: complete installation, migration, and Windows 11 25H2 validation" `
  --body-file <SANITIZED_PR_BODY_FILE>
```

PR має:

- посилатися на Issue через `Closes #...`;
- описувати усунений drift;
- містити exact Windows 11 25H2 evidence;
- перелічувати локальні gates;
- пояснювати різницю між physical 25H2 validation і `windows-latest`;
- не містити LAN IP, приватних шляхів або секретів.

Дочекайся всіх GitHub checks:

```powershell
gh pr checks --watch
```

Обов'язково мають пройти:

- Linux test matrix;
- Windows runtime smoke;
- security;
- package smoke;
- documentation build;
- CodeQL та інші required checks.

Не використовуй admin bypass і не пуш напряму в `main`.

Після зелених checks виконай squash merge:

```powershell
gh pr merge --squash --delete-branch
```

Якщо branch protection або review requirement блокує merge, не обходь його —
повідом точну вимогу.

## 18. Перевір main після merge

```powershell
git switch main
git pull --ff-only
git fetch --all --tags --prune

$LocalMain = git rev-parse HEAD
$RemoteMain = git rev-parse origin/main

$LocalMain
$RemoteMain

if ($LocalMain -ne $RemoteMain) {
    throw "Local main does not match origin/main"
}
```

Перевір PR і GitHub Actions:

```powershell
gh pr view --json number,state,mergedAt,mergeCommit,url
gh run list --branch main --limit 20
```

Прочитай назад файли саме з `origin/main` або raw GitHub:

- `README.md`;
- `README.ua.md`;
- `docs/getting-started.md`;
- `docs/getting-started.ua.md`;
- `docs/windows-11-installation.md`;
- `docs/windows-11-installation.ua.md`;
- `docs/migration-guide.md`;
- `docs/migration-guide.ua.md`;
- `docs/documentation-inventory.ua.md`;
- `docs/tests/windows-11-25h2-validation.md`.

Перевір GitHub Pages після успішного Docs workflow:

<https://weby-homelab.github.io/power-framework/>

## 19. Фінальний звіт користувачу

Поверни українською:

1. Windows edition/version/build/architecture.
2. PRXMX-01 source commit і Windows-tested commit.
3. Що було встановлено.
4. Результати Ruff, MyPy, doc drift, release contract, MkDocs.
5. Full pytest totals, coverage та duration.
6. Package smoke result.
7. FTS, semantic, reranked і MCP results.
8. Issue URL.
9. PR URL.
10. Merge commit SHA в `main`.
11. Результати GitHub Actions після merge.
12. Посилання на опублікований Windows evidence report.
13. Чітке розділення:
    - перевірено на фізичному Windows 11 25H2;
    - перевірено на GitHub `windows-latest`;
    - залишилося неперевіреним.

Не називай локальний commit або відкритий PR публікацією в `main`. Завдання
завершене лише після merge, read-back `origin/main` і зелених post-merge checks.
