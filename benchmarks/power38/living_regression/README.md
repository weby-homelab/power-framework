# POWER 3.8 Living Retrieval Regression Dataset

Єдиний живий регресійний набір для перевірки якості та інваріантів пошуку `POWER` без one-shot холдаут-ритуалів і версій `v1.x`.

## Принцип роботи («Соло-інженер»)

1. **Без спалювання датасету:** якщо тест виявив дефект релевантного пошуку чи порушення авторитетності — виправляємо код і перезапускаємо цей самий набір.
2. **Живе розширення:** кожен новий реальний баг із щоденної роботи додається новим запитом у [`queries.jsonl`](queries.jsonl) з анонімізованими даними.
3. **Два режими бюджету:**
   - `FAST`: лексичний FTS/BM25 + канонічні сервіси (`dense_used == False`).
   - `BALANCED`: Stage 3 `mode="semantic"` (dense після фіксу `F-01`, `dense_used == True`) + лексичний FTS + канонічні сервіси.

`hermetic` перевіряє виконання dense-шляху та інваріанти з детермінованим
ембедером, підігнаним під теми корпусу. Його оцінки не вимірюють якість BGE-M3.
Пороги якості `BALANCED` перевіряє локальний прогін `real --enforce-gates`,
а не автоматичний герметичний тест.

Бенчмарк створює окремий тимчасовий кеш індексу. Перевірка `query_side_writes`
порівнює стан файлів сховища та його кешу після кожного читання. Службовий
SQLite SHM і порожній WAL не враховуються; файли БД і непорожній WAL перевіряються.
Це перевірка вмісту файлів у двох каталогах, не моніторинг усіх файлових операцій.
Запити без оцінок релевантності перевіряються за інваріантами, але не додають
балів до метрик ранжування (`scored_counts` показує їхні знаменники).

## Команди запуску

У GitHub CI герметичний гейт працює через `tests/test_phase5e_living_benchmark.py`
у штатному pytest, включно з перевіркою CLI. `vault_dir=` у Python API має
вказувати на новий каталог; наявні сховища не змінюються.

```bash
# Локальний герметичний smoke (детермінований 1024-dim ембедер без зовнішніх ваг)
python scripts/run_living_benchmark.py --embedder hermetic --enforce-gates

# Локальний прогін на S-Book із реальним BGE-M3 (Iris Xe / CPU <= 4 потоки)
# Примітка для onnxruntime >= 1.30 (external data): вкажіть HF_HUB_CACHE на матеріалізовану (non-symlink) копію моделі.
HF_HUB_CACHE=/path/to/materialized-models/hub HF_HUB_OFFLINE=1 POWER_MODEL_OFFLINE=1 \
  OMP_NUM_THREADS=4 POWER_EMBED_NUM_THREADS=4 POWER_EMBED_DEVICE=auto \
  python scripts/run_living_benchmark.py --embedder real --modes FAST,BALANCED --enforce-gates
```
