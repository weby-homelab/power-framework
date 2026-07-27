"""Generate a realistic 541+ file mixed UA/EN P.A.R.A. vault for IR benchmarking.

Produces:
- A set of TARGET notes (one per query) with known relevance grades.
- A large pool of DISTRACTOR notes (mixed UA/EN) to simulate a real Second Brain.

Run: python generate_corpus.py
"""

from __future__ import annotations

import random
import shutil
from pathlib import Path

SEED = 20260717
random.seed(SEED)

VAULT = Path("/tmp/power_bench_corpus")
TOPICS = ["01_Projects", "02_Areas", "03_Resources", "04_Archive", "06_Daily_Logs"]
N_DISTRACTORS = 508

# ----------------------------------------------------------------------------
# Target notes: (rel_path, title, description, tags, body, lang)
# One per benchmark query in this generator's committed target corpus.
# ----------------------------------------------------------------------------
TARGETS: list[tuple[str, str, str, list[str], str, str]] = [
    # TC-01 Docker
    (
        "03_Resources/DockerDeployment.md",
        "Docker Deployment and Container Orchestration",
        "How to deploy and run docker containers in production with compose",
        ["docker", "deployment", "container"],
        "This guide explains docker deployment of container workloads using docker-compose and container networking on Debian servers.",
        "en",
    ),
    # TC-02 GPG
    (
        "02_Areas/Security/GpgSigning.md",
        "GPG Signing Git Commits",
        "Configure GPG signing for verified git commits and tags",
        ["gpg", "git", "security", "signing"],
        "Enable GPG signing of git commits with `git config commit.gpgsign true` and a GPG key for verified signatures.",
        "en",
    ),
    # TC-03 LLM benchmark
    (
        "03_Resources/LlmInferenceBenchmark.md",
        "LLM Inference Speed Benchmark on GPU",
        "Measuring tokens per second and VRAM for LLM inference",
        ["llm", "inference", "benchmark", "gpu"],
        "A methodology for LLM inference speed benchmark on GPU: measure decode t/s, prefill, and VRAM pressure for local models.",
        "en",
    ),
    # TC-04 Proxmox
    (
        "02_Areas/Infrastructure/ProxmoxLxc.md",
        "Proxmox LXC Container Network Configuration",
        "Setup network bridges and VLANs for LXC containers on Proxmox VE",
        ["proxmox", "lxc", "container", "network"],
        "Proxmox LXC container network configuration uses Linux bridges (vmbr0) and VLAN tagging for isolated container networks.",
        "en",
    ),
    # TC-05 FastAPI
    (
        "03_Resources/FastapiSecurity.md",
        "FastAPI Security Authentication Endpoint",
        "Secure FastAPI endpoints with OAuth2 and dependency injection",
        ["fastapi", "security", "authentication", "endpoint"],
        "Protect FastAPI security by adding authentication to each endpoint via Depends(get_current_user) and OAuth2 bearer tokens.",
        "en",
    ),
    # TC-06 Pydantic
    (
        "03_Resources/PydanticValidation.md",
        "Pydantic Validation Schema Metadata",
        "Use Pydantic models to validate request schemas and metadata",
        ["pydantic", "validation", "schema", "metadata"],
        "Pydantic validation ensures request schema and metadata correctness with model_dump() and field validators in FastAPI.",
        "en",
    ),
    # TC-07 Second Brain
    (
        "03_Resources/SecondBrain.md",
        "Knowledge Base Second Brain Obsidian Notes",
        "Build a second brain knowledge base with Obsidian and P.A.R.A.",
        ["knowledge", "second-brain", "obsidian", "notes"],
        "A knowledge base second brain built with Obsidian notes and the P.A.R.A. method for personal knowledge management.",
        "en",
    ),
    # TC-08 GitHub Actions
    (
        "01_Projects/CiCd/GitHubActions.md",
        "GitHub Actions CI CD Workflow Release",
        "Automate CI/CD release pipelines with GitHub Actions workflows",
        ["github", "actions", "ci", "cd", "workflow", "release"],
        "GitHub Actions CI CD workflow automates build, test, and release on tag push using reusable workflows and release.yml.",
        "en",
    ),
    # TC-09 Tailscale
    (
        "02_Areas/Network/TailscaleVpn.md",
        "VPN Tailscale Network Tunnel",
        "Connect devices with a Tailscale VPN mesh network tunnel",
        ["vpn", "tailscale", "network", "tunnel"],
        "Tailscale provides a VPN mesh network tunnel that connects devices securely over WireGuard without opening ports.",
        "en",
    ),
    # TC-10 Firewall
    (
        "02_Areas/Security/FirewallHardening.md",
        "Firewall Security Hardening Audit",
        "Audit and harden firewall rules for server security",
        ["firewall", "security", "hardening", "audit"],
        "Firewall security hardening audit reviews nftables/ufw rules, drops unused ports, and enables logging for intrusion detection.",
        "en",
    ),
    # TC-11 MCP
    (
        "03_Resources/McpServer.md",
        "MCP Server Agent Tool Integration",
        "Integrate AI agents with an MCP server exposing tools",
        ["mcp", "server", "agent", "tool", "integration"],
        "MCP server agent tool integration lets AI agents call external tools through the Model Context Protocol server interface.",
        "en",
    ),
    # TC-12 Samba
    (
        "04_Archive/Storage/SambaBackup.md",
        "Backup Archive Storage Samba",
        "Store backups on a Samba network share archive storage",
        ["backup", "archive", "storage", "samba"],
        "Backup archive storage on a Samba share uses rsync over SMB to a NAS for long-term archive of daily snapshots.",
        "en",
    ),
    # TC-13 Power Safety
    (
        "01_Projects/PowerSafetyUa.md",
        "Power Safety Ukraine Power Outage",
        "Monitor power outages for Power Safety Ukraine project",
        ["power", "safety", "ukraine", "outage"],
        "Power Safety Ukraine tracks power outage schedules and alerts citizens about electricity cuts via a public dashboard.",
        "en",
    ),
    # TC-14 Embedding/RAG
    (
        "03_Resources/EmbeddingRag.md",
        "Embedding Vector Semantic Search RAG",
        "Build RAG with dense embedding vector semantic search",
        ["embedding", "vector", "semantic", "search", "rag"],
        "Embedding vector semantic search powers RAG by retrieving relevant chunks via dense embeddings and cosine similarity.",
        "en",
    ),
    # TC-CL-01 EN->UKR docker
    (
        "03_Resources/NalashtuvanniaDocker.md",
        "Налаштування безпеки докер контейнерів",
        "Інструкція з конфігурації безпеки docker daemon",
        ["docker", "security", "контейнери"],
        "Цей документ описує розгортання та захист контейнерів docker. Потрібно налаштувати права доступу користувачів та вимкнути привілейований режим.",
        "uk",
    ),
    # TC-CL-02 UKR->EN postgres backup
    (
        "03_Resources/PostgresBackup.md",
        "Postgres database backup guidelines",
        "How to run pg_dump for backup restoration",
        ["database", "postgres", "backup"],
        "This guide explains how to perform nightly postgresql backup dumps with pg_dump and store them securely offsite.",
        "en",
    ),
    # TC-CL-03 EN->UKR GPG
    (
        "02_Areas/Security/PidpysanniaGpg.md",
        "Підписання GPG git комітів",
        "Налаштування GPG для підписання git комітів",
        ["gpg", "git", "підпис"],
        "Щоб увімкнути підписання GPG git комітів, використовуйте git config commit.gpgsign true та налаштуйте GPG ключ для перевірки.",
        "uk",
    ),
    # TC-CL-04 UKR->EN Tailscale
    (
        "02_Areas/Network/TailscaleSetup.md",
        "Tailscale VPN network setup",
        "Step by step Tailscale VPN mesh network setup",
        ["tailscale", "vpn", "network"],
        "This Tailscale VPN network setup connects your devices through an encrypted WireGuard tunnel without port forwarding.",
        "en",
    ),
    # TC-CL-04b UKR->EN postgres (variant)
    (
        "03_Resources/PostgresBackupUa.md",
        "Резервне копіювання бази даних Postgres",
        "Щоденне резервне копіювання postgres через pg_dump",
        ["postgres", "backup", "база"],
        "Цей документ описує резервне копіювання бази даних postgres за допомогою pg_dump та зберігання архівів.",
        "uk",
    ),
    # TC-CL-05 EN->UKR firewall
    (
        "02_Areas/Security/PravylaFirevolu.md",
        "Жорсткі правила фаєрволу аудит",
        "Аудит правил фаєрволу та жорсткі обмеження",
        ["firewall", "аудит", "безпека"],
        "Жорсткі правила фаєрволу аудит перевіряють налаштування nftables, закривають зайві порти та вмикають логування.",
        "uk",
    ),
    # TC-CL-06 UKR->EN LLM benchmark
    (
        "03_Resources/LlmBenchmarkUa.md",
        "LLM inference speed benchmark on GPU",
        "Measuring tokens per second for local LLM inference",
        ["llm", "benchmark", "gpu"],
        "This LLM inference speed benchmark on GPU measures decode tokens per second and VRAM usage for quantized models.",
        "en",
    ),
    # TC-CL-07 EN->UKR MCP
    (
        "03_Resources/IntegratsiiaMcp.md",
        "Інтеграція MCP сервера агента",
        "Підключення інструментів через MCP сервер для агентів",
        ["mcp", "agent", "інтеграція"],
        "Інтеграція MCP сервера агента дозволяє ШІ-агентам викликати зовнішні інструменти через Model Context Protocol.",
        "uk",
    ),
    # TC-CL-08 UKR->EN Proxmox
    (
        "02_Areas/Infrastructure/ProxmoxLxcConfig.md",
        "Proxmox LXC network config",
        "Configure networking for LXC containers on Proxmox",
        ["proxmox", "lxc", "network"],
        "This Proxmox LXC network config uses vmbr0 bridges and VLANs to isolate container traffic on the hypervisor.",
        "en",
    ),
    # TC-CL-09 EN->UKR Obsidian
    (
        "03_Resources/DruhyiMozok.md",
        "База знань Другий Мозок Obsidian",
        "Система персональних знань на основі Obsidian",
        ["obsidian", "знання", "pkm"],
        "База знань Другий Мозок Obsidian використовує метод P.A.R.A. для структурування персональних знань та нотаток.",
        "uk",
    ),
    # TC-CL-10 UKR->EN FastAPI
    (
        "03_Resources/FastapiAuthUa.md",
        "FastAPI authentication endpoint",
        "Secure FastAPI endpoints with auth dependencies",
        ["fastapi", "authentication", "endpoint"],
        "This FastAPI authentication endpoint protects routes via Depends(get_current_user) and OAuth2 bearer tokens.",
        "en",
    ),
    # TC-CL-11 EN->RU Samba
    (
        "04_Archive/Storage/SambaArhiv.md",
        "Резервное копирование Samba архив",
        "Хранение архивов на Samba сетевом ресурсе",
        ["samba", "archive", "backup"],
        "Резервное копирование Samba архив выполняется через rsync по SMB на сетевое хранилище NAS для долгосрочного архива.",
        "ru",
    ),
    # TC-CL-12 RU->EN firewall
    (
        "02_Areas/Security/FirewallAuditRu.md",
        "Firewall security audit",
        "Review firewall rules and harden the perimeter",
        ["firewall", "security", "audit"],
        "This firewall security audit reviews nftables rules, closes unused ports, and enables logging for intrusion detection.",
        "en",
    ),
    # TC-CL-13 EN->UKR SSH port
    (
        "02_Areas/Security/ZminaPortuSsh.md",
        "Зміна порту SSH налаштування",
        "Налаштування зміни порту SSH для безпеки",
        ["ssh", "port", "налаштування"],
        "Зміна порту SSH налаштування передбачає редагування /etc/ssh/sshd_config та перезапуск sshd для приховування стандартного порту.",
        "uk",
    ),
    # TC-CL-14 UKR->EN sync roles
    (
        "03_Resources/KnowledgeBaseSync.md",
        "Knowledge base auto-sync roles",
        "Automatic role-based sync of the knowledge base",
        ["knowledge", "sync", "roles"],
        "This knowledge base auto-sync roles configuration replicates notes across agents based on assigned RBAC roles.",
        "en",
    ),
    # TC-CL-15 EN->UKR RAG
    (
        "03_Resources/SemantuchnyiPoshyk.md",
        "Семантичний векторний пошук RAG",
        "Побудова RAG на основі семантичного векторного пошуку",
        ["rag", "semantic", "search"],
        "Семантичний векторний пошук RAG використовує щільні ембедінги для знаходження релевантних фрагментів тексту.",
        "uk",
    ),
    # TC-CL-16 UKR->EN abstention
    (
        "03_Resources/AbstentionNotes.md",
        "Abstention non-existent facts",
        "Safe refusal when facts are not present in the corpus",
        ["abstention", "safety", "hallucination"],
        "This abstention policy makes the agent refuse to answer when non-existent facts are requested, avoiding hallucination.",
        "en",
    ),
    # TC-CL-17 EN->UKR rename
    (
        "03_Resources/OnovlenniaZviazkiv.md",
        "Оновлення зв'язків перейменування нотаток",
        "Автоматичне оновлення зв'язків при перейменуванні нотаток",
        ["rename", "links", "propagation"],
        "Оновлення зв'язків перейменування нотаток виконує каскадну пропагацію шляхів у полі related інших нотаток.",
        "uk",
    ),
    # TC-CL-18 UKR->EN graph
    (
        "03_Resources/KnowledgeGraph.md",
        "Knowledge graph project database",
        "Link projects to databases in the knowledge graph",
        ["graph", "project", "database"],
        "This knowledge graph project database links a project node to its postgres database node via typed relations.",
        "en",
    ),
]

# ----------------------------------------------------------------------------
# Distractor generation
# ----------------------------------------------------------------------------
DISTRACTOR_TITLES_EN = [
    "Monthly Budget Planning",
    "Recipe for Borscht Soup",
    "Travel Guide to Lviv",
    "Garden Vegetable Planting",
    "Book Notes: Dune",
    "Weekly Standing Meeting",
    "Family Photo Album Index",
    "Car Maintenance Checklist",
    "Guitar Chords Basics",
    "Coffee Brewing Methods",
    "Home Workout Routine",
    "Chess Opening Theory",
    "Bird Watching Log",
    "Painting Watercolor Tips",
    "Cycling Route Map",
    "Pottery Workshop Notes",
    "Sourdough Bread Baking",
    "Yoga Session Journal",
    "Aquarium Fish Care",
    "Stamp Collection Catalog",
    "Hiking Trail Review",
    "Wine Tasting Notes",
    "Calligraphy Practice",
    "Knitting Pattern Library",
    "Photography Exposure Guide",
    "Meditation Timer Log",
    "Cheese Tasting Journal",
    "Board Game Rules Summary",
    " origami Folding Steps",
    "Puzzle Solving Notes",
]
DISTRACTOR_TITLES_UA = [
    "Планування сімейного бюджету",
    "Рецепт борщу",
    "Подорож до Карпат",
    "Садівництво на дачі",
    "Нотатки про книгу",
    "Щотижневий статус-звіт",
    "Альбом світлин родини",
    "Обслуговування авто",
    "Основи гітари",
    "Способи заварювання кави",
    "Домашня тренувальна рутина",
    "Теорія шахових дебютів",
    "Журнал спостереження за птахами",
    "Поради з акварелі",
    "Маршрут для велосипеда",
    "Нотатки з кераміки",
    "Випікання хліба",
    "Щоденник йоги",
    "Догляд за акваріумом",
    "Каталог марок",
    "Огляд туристичного маршруту",
    "Нотатки про вино",
    "Практика каліграфії",
    "Бібліотека візерунків",
    "Посібник з фотографії",
    "Журнал медитації",
    "Щоденник сиру",
    "Правила настільних ігор",
    "Кроки орігамі",
    "Нотатки розв'язування головоломок",
]
DISTRACTOR_BODY_EN = (
    "This note contains general information about {topic}. Nothing of interest is hidden here. "
    "It discusses everyday routines, personal reflections, and miscellaneous observations about {topic} "
    "that are unrelated to infrastructure, security, or software engineering topics."
)
DISTRACTOR_BODY_UA = (
    "Ця нотатка містить загальну інформацію про {topic}. Тут немає нічого цікавого для пошуку. "
    "Обговорюються повсякденні справи, особисті роздуми та різні спостереження щодо {topic}, "
    "що не стосуються інфраструктури, безпеки чи програмування."
)


def write_note(
    path: Path, title: str, desc: str, tags: list[str], body: str, lang: str, day: int
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # distribute timestamps across 2025-2026 for freshness tests
    ts = f"2026-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}T{random.randint(0, 23):02d}:{random.randint(0, 59):02d}:00"
    front = (
        f'---\ntype: Resource\ntitle: "{title}"\n'
        f'description: "{desc}"\ntags: [{", ".join(tags)}]\n'
        f"timestamp: {ts}\n---\n\n# {title}\n\n{body}\n"
    )
    path.write_text(front, encoding="utf-8")


def main() -> None:
    if VAULT.exists():
        shutil.rmtree(VAULT)
    VAULT.mkdir(parents=True)

    # 1. Target notes
    for rel, title, desc, tags, body, lang in TARGETS:
        write_note(VAULT / rel, title, desc, tags, body, lang, 0)
    print(f"Wrote {len(TARGETS)} target notes")

    # 2. Distractors spread across topics + mixed language
    written = 0
    for i in range(N_DISTRACTORS):
        topic_en = random.choice(DISTRACTOR_TITLES_EN)
        topic_ua = random.choice(DISTRACTOR_TITLES_UA)
        use_ua = random.random() < 0.55
        title = topic_ua if use_ua else topic_en
        desc = title
        tags = ["notes", "misc", ("побут" if use_ua else "life")]
        body = (DISTRACTOR_BODY_UA if use_ua else DISTRACTOR_BODY_EN).format(topic=title)
        lang = "uk" if use_ua else "en"
        topic_dir = random.choice(TOPICS)
        sub = random.choice(["", "Misc", "Archive_Old", "Daily", "Notes"])
        d = VAULT / topic_dir / sub
        fname = f"Distractor_{i:04d}.md"
        write_note(d / fname, title, desc, tags, body, lang, 0)
        written += 1
    print(f"Wrote {written} distractor notes")
    total = len(TARGETS) + written
    print(f"TOTAL FILES: {total}")


if __name__ == "__main__":
    main()
