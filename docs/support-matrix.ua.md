# Матриця підтримки платформ P.O.W.E.R.

Ця матриця визначає операційні межі поточного контракту `v3.4.0`. Вона
відділяє автоматизоване покриття життєвого циклу від доказів для model-backed
режимів, фізичних хостів, GPU та якості пошуку. Зелений CI не сертифікує інший
хост, провайдер, корпус або envelope продуктивності.

## Поточна межа підтримки

| Платформа / середовище | Перевірено зараз | Умовно підтримується | Ця матриця не сертифікує |
| --- | --- | --- | --- |
| Linux, Python 3.11–3.14 | Ubuntu CI запускає повний suite, Ruff, MyPy, documentation і release-contract gates; package smoke перевіряє wheel/sdist поза checkout. | Dense, reranked і provider-backed workflows потребують локального model cache та реально прив'язаного provider. | Latency на real vault, GPU benefit, ANN recall і якість reranker. |
| macOS, Python 3.13 | `macos-latest` smoke перевіряє import, init, ingest, strict index, lint, markdown-check, strict FTS sync і FTS search з offline model settings. | Model-backed dense search потребує локально доступної моделі та verified runtime provider. | Продуктивність фізичного Mac, GPU acceleration, dense real-vault evidence і якість reranker. |
| Hosted Windows CI, Python 3.13 | `windows-latest` smoke перевіряє import, init, ingest, strict index, lint, markdown-check, strict FTS sync, FTS search і CPU provider selection. | Для фізичної установки потрібен [Windows-гід](windows-11-installation.ua.md); вибір provider приймається лише після session readback. | GPU performance фізичного Windows 11 25H2, CUDA DLL на машині користувача, dense real-vault evidence і quality claims. |
| Фізичний Windows 11 25H2 | Окремий [гід встановлення Windows](windows-11-installation.ua.md) і його validation receipts визначають процедуру установки та host-specific checks. | У receipt мають бути exact Python, release artifact, OS build, model cache, ONNX provider і hardware. | Hosted CI не є сертифікацією фізичного Windows 11; GPU або latency claim не виводиться без свіжого host receipt. |

## Правила доказів для агентів

- `tested` означає лише lifecycle coverage. Це доказ названого command path на
  названому runner і версії Python.
- `conditional` означає precondition, а не успішний runtime claim. Перед dense
  роботою перевіряйте `power doctor --json` і вимагайте active provider readback.
- `unsupported` або відсутній evidence — stop condition. Не робіть мовчазний
  fallback з явно запитаного GPU provider на CPU.
- Для real vault потрібні immutable generation, повне coverage, content-free
  retrieval receipt, cold/warm/process/MCP controls і resource attribution,
  перш ніж робити latency або ranking claims.

## Джерело правди

Виконувані перевірки живуть у [CI](../.github/workflows/ci.yml), release
workflow — у [release.yml](../.github/workflows/release.yml), а фізична
процедура Windows — у [windows-11-installation.ua.md](windows-11-installation.ua.md).
Roadmap фіксує межі доказів і pending gates у
[`ROADMAP_POWER.md`](https://github.com/weby-homelab/knowledge-base/blob/main/01_Projects/ROADMAP_POWER.md).
