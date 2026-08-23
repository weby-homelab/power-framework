# Матриця підтримки платформ P.O.W.E.R.

Ця матриця визначає операційні межі контракту релізу `v3.7.6`. Вона
відділяє автоматизоване покриття життєвого циклу від доказів для model-backed
режимів, фізичних хостів, GPU та якості пошуку. Зелений CI не сертифікує інший
хост, провайдер, корпус або envelope продуктивності.

## Поточна межа підтримки

| Платформа / середовище | Перевірено зараз | Умовно підтримується | Ця матриця не сертифікує |
| --- | --- | --- | --- |
| Linux, Python 3.13–3.14 | Ubuntu CI запускає повний suite, Ruff, MyPy, documentation і release-contract gates; package smoke перевіряє wheel/sdist поза checkout. | Dense, reranked і provider-backed workflows потребують локального model cache та реально прив'язаного provider. | Host-independent latency, GPU benefit, ANN recall і якість reranker поза опублікованими release receipts. |
| macOS | Відкладено на невизначений строк для `v3.7.6`; macOS CI та release upgrade evidence не заявляються. | Цільового релізу не заплановано. Майбутня пропозиція потребує названого runner, owner і свіжих receipts. | Усі claims сумісності, продуктивності, GPU, dense real-vault і reranker для macOS. |
| Hosted Windows CI | Відкладено на невизначений строк для `v3.7.6`; Windows CI та release upgrade evidence не заявляються. | Цільового релізу не заплановано. Майбутня пропозиція потребує названого runner, owner і свіжих receipts. | Усі claims lifecycle, provider, performance, GPU, dense real-vault і quality для Windows. |
| Фізичний Windows 11 25H2 | Відкладено на невизначений строк для `v3.7.6`; installation guide є лише інформаційним і не є release certification. | Цільового релізу не заплановано. Майбутня пропозиція потребує точних host/artifact receipts. | Фізична сумісність Windows, GPU performance, CUDA availability і latency claims. |

## Офіційні профілі розгортання

| Профіль | Обов'язковий runtime | Вимога Docker | Контракт canonical vault | Підтримуваний scope |
| --- | --- | --- | --- | --- |
| **A — headless / agent server** | Один native `power-framework[mcp]`, `power`, обов'язковий `power-mcp` через stdio, host-side POWER Skill і один canonical vault. | Немає. Docker і Web UI не є передумовами. | Native CLI та MCP використовують один vault і `ApplicationService`; Web container відсутній. | Повна POWER-інсталяція для FTS і налаштованого local MCP. Semantic/reranked залишається умовним до явного evidence моделей/provider. |
| **B — full human + agent server** | Усе з Profile A плюс рівно один відповідний image `power-web` із locked `[web,semantic,rerank]` dependencies. | Потрібен для Web UI. | Web container монтує той самий canonical vault read-write для governed proposal/apply, використовує той самий `ApplicationService`, а named volume містить лише rebuildable cache. | Authenticated Web UI на host loopback `127.0.0.1:8080`; FTS, semantic і reranked потребують реального non-fallback acceptance; Web MCP services і MCP TCP ports відсутні. |

Для Profile B потрібно надати non-root Web UID/GID права на host-side vault.
Видалення Web cache не може змінити Markdown, Git або `.power` truth. Віддалений
доступ до Web потребує authenticated reverse proxy, Tailscale або еквівалентного
trusted access layer.

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

Виконувані перевірки живуть у [CI](https://github.com/weby-homelab/power-framework/blob/main/.github/workflows/ci.yml), release
workflow — у [release.yml](https://github.com/weby-homelab/power-framework/blob/main/.github/workflows/release.yml), а фізична
процедура Windows — у [windows-11-installation.ua.md](windows-11-installation.ua.md),
але Windows і macOS не входять до межі `v3.7.6` та не мають запланованого
release target.
Roadmap фіксує межі доказів і pending gates у
[`ROADMAP_POWER.md`](https://github.com/weby-homelab/knowledge-base/blob/main/01_Projects/ROADMAP_POWER.md).
