# Intel iGPU через OpenVINO

Канонічні BGE-M3 embeddings і BGE reranker використовують спільний селектор
OpenVINO. Прискорення залежить від Intel GPU, драйверів і доступу контейнера до
`/dev/dri`; сам вибір провайдера не доводить виграш швидкості.

## Встановлення

Створіть окреме середовище Python 3.13–3.14. Спочатку перевірте наявність wheel
`onnxruntime-openvino` для обраної версії Python та ОС. Для LXC оператор має
налаштувати `/dev/dri`, права доступу та сумісні Intel GPU драйвери.
Див. [офіційні вимоги OpenVINO EP](https://onnxruntime.ai/docs/execution-providers/OpenVINO-ExecutionProvider.html).

Із checkout вихідного коду:

```bash
python3.13 -m venv .venv-openvino
. .venv-openvino/bin/activate
python -m pip install . tokenizers 'huggingface-hub>=1.30.0,<1.31.0' 'numpy>=1.24.0,<2.5' onnxruntime-openvino
python -c "import onnxruntime as ort; print(ort.get_available_providers())"
```

У середовищі має бути лише один ORT-пакет. `onnxruntime-openvino` не можна
поєднувати з `onnxruntime`, `onnxruntime-gpu` чи `onnxruntime-directml`: вони
записують той самий модуль `onnxruntime`. Не додавайте extras `semantic`,
`rerank`, `gpu` і не запускайте sync залежностей, який поверне інший ORT-пакет.
Прямий BGE reranker не потребує FastEmbed.

## Налаштування CLI

`POWER_EMBED_DEVICE` та `POWER_RERANKER_DEVICE` приймають `auto`, `cpu`, `cuda`,
`rocm`, `openvino`, `directml`. Якщо режим reranker не задано, він успадковує
режим embeddings. Пріоритет `auto`: CUDA → ROCm → OpenVINO → DirectML → CPU.

| Змінна | Призначення |
| --- | --- |
| `POWER_EMBED_DEVICE=openvino` | Вимагати OpenVINO для embeddings. |
| `POWER_RERANKER_DEVICE=openvino` | Вимагати OpenVINO для reranker. |
| `POWER_EMBED_DEVICE_TYPE=GPU` | Пристрій OpenVINO; типово `GPU`, можливі `GPU.0`, `GPU.1` або свідомий вибір `CPU`. |
| `POWER_RERANKER_DEVICE_TYPE` | Окремий тип пристрою reranker; якщо не задано, успадковує тип embeddings. |

Порожній тип пристрою відхиляється. Решту значень перевіряє OpenVINO.
`POWER_EMBED_DEVICE_ID` на OpenVINO не впливає. Опції `device_id` та
`arena_extend_strategy` цьому EP не передаються.

Явний `openvino` завершується `requested_onnx_provider_unavailable`, коли EP
відсутній, або `requested_onnx_provider_not_bound`, коли прив'язався інший EP.
POWER прибирає `CPUExecutionProvider` і задає
`session.disable_cpu_ep_fallback=1`; якщо OpenVINO не може обробити всі вузли
графа, ONNX Runtime завершує створення сесії помилкою замість CPU EP. `auto`
зберігає цей fallback. `device_type=CPU` свідомо спрямовує обчислення на CPU
через OpenVINO EP, а не через `CPUExecutionProvider`. Внутрішні політики
OpenVINO також залежать від `device_type`: `CPU` використовує його CPU-плагін,
а `AUTO`, `HETERO` та `MULTI` можуть планувати роботу на CPU. Для GPU задайте
`GPU` або `GPU.<індекс>`; сама прив'язка OpenVINO EP не доводить, що всі вузли
виконались на GPU. Наведене налаштування керує лише CPU EP ONNX Runtime.

У явних режимах POWER також вимикає повторний запуск на іншому EP після помилки
inference; у `auto` він збережений. Після успішного inference `active_provider`
показує поточну прив'язку, зокрема CPU fallback у `auto`. Помилки явного режиму
повертаються виклику без тихого переходу на `CPUExecutionProvider`.

Перевіряйте `platform.platform()`, `platform.machine()`, `onnxruntime.__version__`
та `onnxruntime.get_available_providers()` саме в робочому Python-середовищі.
Марка процесора чи назва ОС не доводять доступність backend. Навіть наявність EP
у списку потребує проби моделі: драйвери, права `/dev/dri` або модель можуть
завадити прив'язці. У CPU-only збірці режими `auto` та `cpu` зберігають CPU-шлях.

## Перевірка

Використовуйте вже перевірені повні локальні кеші моделей:

```bash
export POWER_EGRESS_POLICY=deny POWER_MODEL_OFFLINE=1
export POWER_EMBED_DEVICE=openvino POWER_RERANKER_DEVICE=openvino
export POWER_EMBED_DEVICE_TYPE=GPU
power doctor /path/to/vault --probe-provider --json
```

Очікується `embedding.bound_provider == OpenVINOExecutionProvider`.
Без `--probe-provider` doctor не завантажує модель. Відсутній кеш моделі —
окрема помилка, яка не доводить несправність OpenVINO.

[Виконуваний Python smoke-тест](openvino.md#cache-only-acceptance) перевіряє
1024-вимірний скінченний вектор, скінченний reranker score та прив'язку обох EP.
Він не читає значення SessionOptions; їх конфігурацію перевіряють offline unit
тести. Цей smoke-тест не доводить продуктивність обладнання.

Повний sync потребує окремого погодження оператора. Для issue #471 на незмінному
знімку vault потрібно виміряти час <8.5 год, RAM <7000 MB, swap, кількість
нотаток/чанків, exclusions і semantic retrieval без fallback. Історичне
`Coverage: 3624/3624` стосується лише відповідного знімка. Тести з підміною
рантайму не доводять живе GPU-виконання або продуктивність.
