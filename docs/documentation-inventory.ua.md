# Інвентаризація документації встановлення та міграції

**Стан на:** 2026-08-30

**Версія коду:** 3.7.10 release

**Обсяг:** публічні стартові описи, усі безпосередньо пов'язані з ними операційні
документи та виконуваний контракт CLI/MCP.

## Канонічні точки входу

| Документ | Призначення | Перевірений стан |
| --- | --- | --- |
| `README.md` | Англійський огляд і маршрути для агента | Вирівняно з 3.7.10 release |
| `README.ua.md` | Український огляд і маршрути для агента | Вирівняно з англійським описом |
| `docs/getting-started.md` | Чисте встановлення на POSIX | Повний acceptance gate |
| `docs/getting-started.ua.md` | Українська чиста установка | Семантично паритетна з 3.7.10 release |
| `docs/windows-11-installation.md` | Windows 11 25H2 / PowerShell | Повна окрема процедура |
| `docs/windows-11-installation.ua.md` | Українська Windows-процедура | Семантично паритетна |
| `docs/migration-guide.md` | Міграція наявної бази | Шість fail-closed фаз |
| `docs/migration-guide.ua.md` | Українська міграція | Семантично паритетна |
| `docs/cli.md` | Виконуваний CLI-контракт | 26 команд |
| `docs/mcp-server.md` | Виконуваний MCP-контракт | 20 інструментів |
| `docs/mcp-client-onboarding.md` | Golden onboarding для чотирьох клієнтів | stdio shape + proposal gate |
| `docs/mcp-client-onboarding.ua.md` | Український golden onboarding | Семантично паритетний |
| `docs/support-matrix.md` | Англійська матриця підтримки платформ | Tested / conditional / unsupported boundaries |
| `docs/support-matrix.ua.md` | Українська матриця підтримки платформ | Семантично паритетна |
| `docs/guides/hybrid-fleet-gpu-offloading-guide.md` | Англійський посібник гібридної GPU-архітектури | Універсальний асинхронний offloading |
| `docs/guides/hybrid-fleet-gpu-offloading-guide.ua.md` | Український посібник гібридної GPU-архітектури | Семантично паритетний |

## Пов'язані документи

| Документ або посилання | Класифікація | Результат аудиту |
| --- | --- | --- |
| `CONTRIBUTING.md` | Поточний development workflow | Існує; не є інструкцією кінцевого користувача |
| `docs/release-3.6.3.md` | Історичні release notes | Task v2, typed decisions, search ranking та evidence boundary |
| `docs/release-3.6.1.md` | Історичні release notes | Суворий CPU throttling і Linux-first release contract |
| `docs/release-3.6.0.md` | Історичні release notes | Linux-first architecture, evidence та upgrade contract |
| `docs/release-3.5.0.md` | Історичні release notes | Опублікований release contract; receipt і remote readback перевірені |
| `docs/hierarchical-index-migration*.md` | Звіт v1.6 | Позначено історичним; прибрано загальні `O(log n)` і руйнівну Git-пораду |
| `docs/tests/P.O.W.E.R.3.2.1-TEST-2.md` | Історичний тестовий артефакт | Залишено з явною версією у назві |
| `docs/tests/P.O.W.E.R.3.0.0-TEST.md` | Історичний search-quality звіт | Залишено з явною версією у назві |
| Документаційний сайт | Опублікований рендер | URL відповідав під час аудиту |
| Release wheel `v3.7.10` | Unified install artifact | Tag-bound wheel; signed tag/readback перевірятиме GitHub Release workflow |
| Python, Git, Microsoft, ONNX Runtime | Зовнішні prerequisites | Посилання ведуть на офіційні джерела |

## Усунений дрейф

- Старий MCP-інвентар замінено на фактичні `20` інструментів; CLI
  задокументовано як `26` top-level команд.
- До surface додано `power integrations` для unified native, Skill і launcher plans.
- `reranked` більше не називається стандартним режимом: код використовує `auto`,
  а reranking вмикається явно.
- Видалено небезпечне оновлення через destructive reset, непереносний `/tmp`,
  `%USERPROFILE%` у PowerShell і запуск MCP через глобальний `py` замість точного
  інтерпретатора venv.
- Встановлення прив'язано до release wheel `v3.7.10`, а не до
  рухомої гілки; tag, assets і release receipts перевірені через GitHub Release.
- Міграція більше не обіцяє автоматичне розпізнавання довільних папок, переписування
  всіх посилань або відновлення тексту через LLM. Додано manifest/hash reconciliation,
  вкладення, неоднозначні посилання, rollback і заборону автоматичного cutover.
- Приватний roadmap іншої бази знань вилучено з публічної навігації MkDocs.

## Межі перевірки

Локальний smoke test підтверджує створення чистої бази, ingest, strict index, lint,
Markdown-перевірку, FTS sync/search і status. Фізична перевірка Windows 11 25H2
для follow-up revision `4e5b2b9` є історичною; результати наведено у [звіті
перевірки](tests/windows-11-25h2-validation.md). `v3.7.10` не запускає
`windows-latest` або `macos-latest`: обидві платформи відкладені на невизначений
строк і не мають release certification. Межі та заборонені inference claims
зведені у [матриці підтримки](support-matrix.ua.md).

Автоматичний gate `scripts/check_doc_drift.py` перевіряє поточні кількості CLI/MCP,
пошуковий контракт, заборонені застарілі шаблони та всі локальні Markdown-посилання
у канонічному наборі документів. Окремий client-onboarding gate перевіряє всі
чотири конфігураційні форми та забороняє старий wrapper/небезпечну межу vault.
