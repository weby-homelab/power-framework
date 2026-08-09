# Встановлення P.O.W.E.R. на Windows 11 25H2

Цей гід встановлює версіонований реліз P.O.W.E.R. `v3.3.2` в ізольоване
віртуальне середовище, створює чистий vault, перевіряє CLI та налаштовує
MCP-клієнт. Усі команди наведено для PowerShell.

## Межа підтримки та доказів

- P.O.W.E.R. потребує Python 3.11 або новішого.
- Windows 11 25H2 є офіційним релізом Windows 11 (сімейство OS build `26200`).
- ONNX Runtime підтримує Windows 11, а його Windows-збірки потребують
  актуального Microsoft Visual C++ Runtime.
- P.O.W.E.R. `v3.3.2` має автоматизований кросплатформний regression-тест
  поведінки rename-overwrite у Windows.
- Фізичну перевірку Windows 11 25H2 завершено 2026-08-08 для follow-up revision
  `4e5b2b9`; див. [звіт перевірки](tests/windows-11-25h2-validation.md).
  Це підтверджує follow-up source/build і не переміщує та не перевидає
  незмінні release-артефакти `v3.3.2`.

Офіційні передумови:

- [Інформація про релізи Windows 11](https://learn.microsoft.com/windows/release-health/windows11-release-information)
- [Python для Windows](https://www.python.org/downloads/windows/)
- [Офіційний гід Python щодо virtual environment](https://packaging.python.org/en/latest/guides/installing-using-pip-and-virtual-environments/)
- [Microsoft Visual C++ Redistributable](https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist)
- [Вимоги ONNX Runtime](https://onnxruntime.ai/docs/install/)

## 1. Підтвердьте версію Windows та архітектуру

Відкрийте Windows Terminal із вкладкою PowerShell. Для встановлення в профіль
користувача за цим гідом права адміністратора не потрібні.

```powershell
Get-ComputerInfo | Select-Object WindowsProductName, WindowsVersion, OsBuildNumber, OsArchitecture
[System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture
```

Для Windows 11 25H2 значення `OsBuildNumber` має починатися з `26200`.
P.O.W.E.R. використовує CPU ONNX Runtime; CUDA toolkit не потрібен.

## 2. Встановіть передумови

Встановіть 64-бітний CPython із python.org. Під час setup увімкніть Python
launcher і запропоновані параметри `PATH`. Консервативний рекомендований вибір —
Python 3.13; поточному package contract відповідають Python 3.11–3.14.

Встановіть актуальний Microsoft Visual C++ 2015–2022 Redistributable для
архітектури хоста. Git не потрібен для встановлення release wheel нижче, але
потрібен для source або editable-встановлення:

```powershell
winget install --id Git.Git -e --source winget
```

Після встановлення передумов закрийте й знову відкрийте Windows Terminal, потім
перевірте:

```powershell
py --version
py -m pip --version
git --version
```

Якщо Git не встановлювали, бо використовуватимете лише release wheel, перевірку
`git --version` можна пропустити.

## 3. Створіть ізольований runtime

Використовуйте точні шляхи: тоді P.O.W.E.R. працює без активації PowerShell
script і без зміни execution policy.

```powershell
$PowerHome = Join-Path $env:LOCALAPPDATA "POWER"
$VenvDir = Join-Path $PowerHome ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$PowerExe = Join-Path $VenvDir "Scripts\power.exe"

New-Item -ItemType Directory -Force -Path $PowerHome | Out-Null
py -m venv $VenvDir
& $VenvPython -m pip install --upgrade pip
```

Підтвердьте, що обрано virtual environment, а не глобальний інтерпретатор:

```powershell
& $VenvPython -c "import sys; print(sys.version); print(sys.executable); print(sys.prefix != sys.base_prefix)"
```

Останній рядок має бути `True`, а шлях до executable має завершуватися на
`POWER\.venv\Scripts\python.exe`.

## 4. Встановіть незмінний реліз

Release wheel не потребує Git і фіксує версію вихідного коду P.O.W.E.R. Його
Python-залежності все одно завантажуються з налаштованого Python package index.

```powershell
$ReleaseWheel = "https://github.com/weby-homelab/power-framework/releases/download/v3.3.2/power_framework-3.3.2-py3-none-any.whl"
& $VenvPython -m pip install $ReleaseWheel
if ($LASTEXITCODE -ne 0) { throw "Помилка встановлення P.O.W.E.R." }
```

Перевірте executable, distribution metadata, імпорти та ONNX Runtime:

```powershell
& $PowerExe --version
& $VenvPython -c "from importlib.metadata import version; print(version('power-framework'))"
& $VenvPython -c "import power_framework, power_framework.mcp, onnxruntime; print('imports: OK'); print(onnxruntime.__version__)"
if ($LASTEXITCODE -ne 0) { throw "Помилка перевірки імпортів P.O.W.E.R." }
```

Обидві перевірки версії мають показати `3.3.2`, а перевірка імпортів —
`imports: OK`.

### Альтернатива: встановлення із закріпленого tag

Використовуйте лише коли Git уже встановлено:

```powershell
& $VenvPython -m pip install "git+https://github.com/weby-homelab/power-framework.git@v3.3.2"
```

Не встановлюйте незакріплений `main`, якщо важлива відтворюваність.

## 5. Створіть і перевірте чисту базу знань

Оберіть новий або порожній каталог. `power init` навмисно відмовляється
працювати з непорожнім каталогом; для наявної бази використовуйте migration
guide.

```powershell
$Vault = Join-Path $env:USERPROFILE "Documents\POWER-Vault"
& $PowerExe init $Vault
if ($LASTEXITCODE -ne 0) { throw "Не вдалося ініціалізувати vault" }

& $PowerExe ingest $Vault --type Resource --title "First note" --description "Clean-install acceptance note"
if ($LASTEXITCODE -ne 0) { throw "Не вдалося створити першу нотатку" }

& $PowerExe index $Vault --strict
if ($LASTEXITCODE -ne 0) { throw "Strict-індексація не пройшла" }

& $PowerExe lint $Vault
if ($LASTEXITCODE -ne 0) { throw "Lint vault не пройшов" }

& $PowerExe markdown-check $Vault
if ($LASTEXITCODE -ne 0) { throw "Markdown check не пройшов" }
```

Попередження про orphan для першої нотатки без inbound link є інформаційним.
Acceptance gate: exit code `0`, відсутні невалідні OKF-метадані та биті
внутрішні посилання.

Побудуйте легкий FTS-індекс і доведіть retrieval без завантаження моделей:

```powershell
& $PowerExe sync $Vault --fts-only
if ($LASTEXITCODE -ne 0) { throw "FTS-синхронізація не пройшла" }

& $PowerExe search $Vault "acceptance" --mode fts
if ($LASTEXITCODE -ne 0) { throw "FTS-пошук не пройшов" }
```

Результат має містити `First note`.

## 6. Опційний dense та reranked пошук

Semantic і reranked режими потребують закріплених BGE-M3 та reranker model
assets. Перша повна синхронізація може потребувати значного часу, мережевого
трафіку, диска та пам'яті:

```powershell
& $PowerExe sync $Vault
if ($LASTEXITCODE -ne 0) { throw "Dense-синхронізація не пройшла" }

& $PowerExe search $Vault "clean installation" --mode semantic
if ($LASTEXITCODE -ne 0) { throw "Semantic-пошук не пройшов" }
```

Моделі зберігаються в Hugging Face cache, а не всередині virtual environment.
P.O.W.E.R. перевіряє закріплений model contract і працює fail-closed, якщо
обов'язкові assets відсутні або пошкоджені. Не вимикайте Microsoft Defender чи
SmartScreen заради успішного download: спочатку перевірте точну помилку, proxy,
доступне місце та security event.

## 7. Налаштуйте MCP-клієнт

Завжди вказуйте точний interpreter virtual environment. Глобальний launcher
`py` може обрати інший Python, у якому P.O.W.E.R. не встановлено.

Для Claude Desktop відредагуйте
`$env:APPDATA\Claude\claude_desktop_config.json`. Замініть `YOUR-NAME` на
реальний каталог користувача або отримайте точні значення командами:

```powershell
$VenvPython
$Vault
```

Приклад JSON (backslash потрібно подвоювати):

```json
{
  "mcpServers": {
    "power": {
      "command": "C:\\Users\\YOUR-NAME\\AppData\\Local\\POWER\\.venv\\Scripts\\python.exe",
      "args": ["-m", "power_framework.mcp"],
      "env": {
        "POWER_VAULT_DIR": "C:\\Users\\YOUR-NAME\\Documents\\POWER-Vault"
      }
    }
  }
}
```

Перед перезапуском MCP-клієнта перевірте interpreter і vault:

```powershell
$env:POWER_VAULT_DIR = $Vault
& $VenvPython -c "import os; from pathlib import Path; import power_framework.mcp; p=Path(os.environ['POWER_VAULT_DIR']); assert p.is_dir(); print('MCP preflight: OK')"
```

Після збереження конфігурації перезапустіть MCP-клієнт. Long-lived client не
перечитує автоматично оновлене Python environment або JSON.

## 8. Оновлення, rollback і видалення

Для оновлення до конкретного релізу замініть версію в URL wheel і повторіть
install із `--upgrade`. Після цього перевірте `power --version`.

Rollback на `v3.3.2`:

```powershell
& $VenvPython -m pip install --force-reinstall $ReleaseWheel
& $PowerExe --version
```

Видалення застосунку без зміни vault:

```powershell
& $VenvPython -m pip uninstall power-framework
```

Vault складається зі звичайних Markdown-файлів і відокремлений від Python
runtime. Зробіть backup перед видаленням будь-якого з цих каталогів.

## Усунення проблем

| Симптом | Рішення |
| --- | --- |
| `py` не розпізнано | Повторіть python.org installer з увімкненим launcher, відкрийте Terminal знову та перевірте Windows App Execution Aliases/PATH. |
| `power` не розпізнано | Використовуйте точний `$PowerExe` із цього гіда; глобальна зміна `PATH` не потрібна. |
| `Activate.ps1` заблоковано | Activation не потрібна. Продовжуйте через `$VenvPython` і `$PowerExe`. Якщо змінюєте execution policy, спочатку прочитайте офіційний гід Microsoft і перевірте Group Policy організації. |
| `DLL load failed` під час import `onnxruntime` | Встановіть або відновіть актуальний Visual C++ 2015–2022 Redistributable для архітектури хоста, потім відкрийте Terminal знову. |
| `pip install git+...` падає | Встановіть Git for Windows або використовуйте release wheel, який не потребує Git. |
| MCP-клієнт повідомляє `module not found` | Його `command` вказує на неправильний Python. Використайте повний шлях `.venv\Scripts\python.exe` і перезапустіть клієнт. |
| Явний `POWER_EMBED_DEVICE=cuda` завершується `requested_onnx_provider_not_bound` | Це fail-closed GPU-контракт: сесія не прив'язала CUDA. Не приховуйте помилку; перевірте `nvidia-*` runtime, `onnxruntime-gpu`, або задайте `POWER_EMBED_DEVICE=auto` лише коли CPU fallback справді потрібен. |
| `power init` відмовляється працювати | Каталог не порожній. Не обходьте захисну перевірку; оберіть новий шлях або migration guide. |
| Dense sync падає | Залишайте failure closed. Перевірте диск, network/proxy та точну model error; FTS доступний через `sync --fts-only` і `search --mode fts`. |

## Acceptance checklist

- Windows повідомляє version 25H2 / build family `26200`.
- Обраний Python має версію 3.11+; venv-перевірка повертає `True`.
- `power --version` і distribution metadata повертають `3.3.2`.
- `power_framework.mcp` та `onnxruntime` імпортуються успішно.
- `init`, `ingest`, `index --strict`, `lint` і `markdown-check` завершуються з
  кодом `0`.
- FTS sync завершується з кодом `0`, а пошук повертає acceptance note.
- MCP preflight друкує `MCP preflight: OK` через точно налаштований Python.
- Dense/reranked capability можна заявляти лише якщо optional full sync і
  відповідний search пройшли на цільовому Windows host.
