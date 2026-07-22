"""Deterministic topic-driven frozen benchmark generator for POWER 3.1.

Architecture (E1 methodological review):
  - 50 frozen topics, each with bilingual (UA/EN) title/content/query/atomic_answer.
  - Exactly 4 answerable queries per topic = 200 base answerable (50/stratum).
  - Primary document = the topic's own UA or EN doc, literally containing the
    atomic answer as a substring.
  - 5 explicit absent topics (not in corpus) yield 20 no-answer queries (1/stratum).
  - 8 dedicated QDD* distractor queries with primary + contradictory distractor doc.
  - Sparse qrels: only positive entries (primary + optional secondary) + explicit
    distractors. Missing (query_id, doc_id) pair ⇒ relevance 0.

SCOPE AND LIMITATIONS:
  - SYNTHETIC BENCHMARK — not human-annotated, not production evidence.
  - Relevance is rule-assigned by topic membership, not by human judges.
  - Corpus documents are generated from templates, not real vault data.
  - Suitable for hermetic CI regression testing only.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

# ── Constants ────────────────────────────────────────────────────────────────
SEED = 42
N_TOPICS = 50
N_ABSENT = 5
STRATA = ("ua_to_ua", "en_to_en", "ua_to_en", "en_to_ua")
FIXED_TIMESTAMP = "2026-07-22T00:00:00+00:00"
ANNOTATOR = "synthetic-generator-v1"
RUBRIC_VERSION = "1.0"
SCHEMA_VERSION = "3.1.0"
BENCHMARK_VERSION = "3.1.0"

# Language-direction → (query_lang, target_doc_lang)
LANG_MAP: dict[str, tuple[str, str]] = {
    "ua_to_ua": ("uk", "uk"),
    "en_to_en": ("en", "en"),
    "ua_to_en": ("uk", "en"),
    "en_to_ua": ("en", "uk"),
}

# Paired topics for secondary docs: (1,2), (3,4), …, (49,50)
PAIRS: dict[int, int] = {}
for i in range(1, N_TOPICS + 1, 2):
    PAIRS[i] = i + 1 if i + 1 <= N_TOPICS else i - 1
    PAIRS[i + 1] = i


# ── Topic records ────────────────────────────────────────────────────────────
# Each entry: (ua_title, ua_content, ua_query, ua_answer,
#               en_title, en_content, en_query, en_answer)

TOPIC_DATA: list[tuple[str, str, str, str, str, str, str, str]] = [
    # ── 1–10: Infrastructure & DevOps ─────────────────────────────────────
    (
        "Оптимізація Docker через Multi-Stage Build",
        "Multi-stage build дозволяє зменшити розмір фінального образу Docker. "
        "Використовуйте alpine як базовий образ. Копіюйте лише необхідні артефакти "
        "з проміжних етапів за допомогою COPY --from.",
        "як оптимізувати Docker образи через multi-stage build",
        "Multi-stage build дозволяє зменшити розмір фінального образу",
        "Docker Multi-Stage Build Optimization",
        "Multi-stage build reduces the final Docker image size. Use alpine as the "
        "base image. Copy only required artifacts from intermediate stages using COPY --from.",
        "how to optimize Docker images with multi-stage build",
        "Multi-stage build reduces the final Docker image size",
    ),
    (
        "Docker Compose мережі та volumes",
        "Docker Compose дозволяє об'єднувати контейнери в мережі та використовувати "
        "volumes для зберігання даних. Healthcheck перевіряє працездатність сервісу. "
        "Restart policies забезпечують відновлення після збоїв.",
        "як налаштувати Docker Compose мережі та volumes",
        "Docker Compose дозволяє об'єднувати контейнери в мережі",
        "Docker Compose Networks and Volumes",
        "Docker Compose connects containers via networks and persists data with volumes. "
        "Healthcheck verifies service readiness. Restart policies ensure recovery after failures.",
        "how to configure Docker Compose networks and volumes",
        "Docker Compose connects containers via networks and persists data with volumes",
    ),
    (
        "Розгортання Kubernetes з k3s",
        "k3s це легковажна версія Kubernetes для edge та IoT. Розгортання включає "
        "встановлення Ingress контролера та Service Mesh. Використовуйте Helm для "
        "управління застосунками.",
        "як розгорнути Kubernetes кластер з k3s",
        "k3s це легковажна версія Kubernetes для edge та IoT",
        "Kubernetes Deployment with k3s",
        "k3s is a lightweight Kubernetes distribution for edge and IoT. Deployment "
        "includes Ingress controller and Service Mesh setup. Use Helm for application management.",
        "how to deploy Kubernetes cluster with k3s",
        "k3s is a lightweight Kubernetes distribution for edge and IoT",
    ),
    (
        "Kubernetes Networking та Ingress",
        "Kubernetes Networking включає ClusterIP, NodePort та LoadBalancer сервіси. "
        "Ingress контролер маршрутизує зовнішній трафік. Network Policies обмежують "
        "комунікацію між подами.",
        "що таке Kubernetes Networking та Ingress",
        "Kubernetes Networking включає ClusterIP, NodePort та LoadBalancer сервіси",
        "Kubernetes Networking and Ingress",
        "Kubernetes networking includes ClusterIP, NodePort, and LoadBalancer services. "
        "Ingress controller routes external traffic. Network Policies restrict pod-to-pod communication.",
        "what is Kubernetes networking and Ingress",
        "Kubernetes networking includes ClusterIP, NodePort, and LoadBalancer services",
    ),
    (
        "CI/CD Pipeline з GitHub Actions",
        "GitHub Actions дозволяє створити CI/CD пайплайн з linting, type checking, "
        "unit tests та деплоєм. Використовуйте matrix стратегію для тестування "
        "на різних версіях Python.",
        "як налаштувати CI/CD пайплайн з GitHub Actions",
        "GitHub Actions дозволяє створити CI/CD пайплайн з linting, type checking, unit tests",
        "CI/CD Pipeline with GitHub Actions",
        "GitHub Actions enables CI/CD pipelines with linting, type checking, unit tests, "
        "and deployment. Use matrix strategy for testing across Python versions.",
        "how to set up CI/CD pipeline with GitHub Actions",
        "GitHub Actions enables CI/CD pipelines with linting, type checking, unit tests",
    ),
    (
        "Terraform Infrastructure as Code",
        "Terraform дозволяє керувати інфраструктурою через код. Використовуйте "
        "terraform plan для попереднього перегляду змін та terraform apply для "
        "застосування. State файл зберігає стан інфраструктури.",
        "що таке Terraform Infrastructure as Code",
        "Terraform дозволяє керувати інфраструктурою через код",
        "Terraform Infrastructure as Code",
        "Terraform manages infrastructure through code. Use terraform plan to preview "
        "changes and terraform apply to execute them. The state file tracks infrastructure state.",
        "what is Terraform Infrastructure as Code",
        "Terraform manages infrastructure through code",
    ),
    (
        "Ansible автоматизація конфігурацій",
        "Ansible дозволяє автоматизувати конфігурацію серверів без агентів. "
        "Playbooks описують бажаний стан системи. Використовуйте ролі для "
        "багаторазового використання коду.",
        "як автоматизувати конфігурацію серверів з Ansible",
        "Ansible дозволяє автоматизувати конфігурацію серверів без агентів",
        "Ansible Configuration Automation",
        "Ansible automates server configuration without agents. Playbooks describe the "
        "desired system state. Use roles for reusable configuration code.",
        "how to automate server configuration with Ansible",
        "Ansible automates server configuration without agents",
    ),
    (
        "Стратегія резервного копіювання BorgBackup",
        "BorgBackup забезпечує дедуплікацію та шифрування бекапів. Рекомендується "
        "щоденне копіювання на NAS та щотижневе на віддалений сервер. "
        "Використовуйте borg prune для автоматичного видалення старих бекапів.",
        "як налаштувати резервне копіювання з BorgBackup",
        "BorgBackup забезпечує дедуплікацію та шифрування бекапів",
        "Backup Strategy with BorgBackup",
        "BorgBackup provides deduplication and encryption for backups. Recommended daily "
        "backups to NAS and weekly offsite replication. Use borg prune for automatic cleanup.",
        "how to set up backup strategy with BorgBackup",
        "BorgBackup provides deduplication and encryption for backups",
    ),
    (
        "Prometheus та Grafana моніторинг",
        "Prometheus збирає метрики з Node Exporter, а Grafana візуалізує їх "
        "на дашбордах. Alertmanager надсилає сповіщення при перевищенні порогів. "
        "Налаштуйте правила для CPU, пам'яті та дисків.",
        "як налаштувати моніторинг з Prometheus та Grafana",
        "Prometheus збирає метрики з Node Exporter, а Grafana візуалізує їх на дашбордах",
        "Prometheus and Grafana Monitoring",
        "Prometheus collects metrics from Node Exporter, Grafana visualizes them on "
        "dashboards. Alertmanager sends notifications on threshold breaches. Configure "
        "rules for CPU, memory, and disk.",
        "how to set up monitoring with Prometheus and Grafana",
        "Prometheus collects metrics from Node Exporter, Grafana visualizes them on dashboards",
    ),
    (
        "Alerting правила Prometheus",
        "Prometheus alerting rules визначають умови для сповіщень. Наприклад, "
        "CPU > 80% для 5 хвилин. Alertmanager маршрутизує сповіщення в Slack "
        "або email. Використовуйте inhibit_rules для запобігання дублікатам.",
        "як налаштувати alerting правила Prometheus",
        "Prometheus alerting rules визначають умови для сповіщень",
        "Prometheus Alerting Rules",
        "Prometheus alerting rules define conditions for notifications. For example, "
        "CPU > 80% for 5 minutes. Alertmanager routes alerts to Slack or email. "
        "Use inhibit_rules to prevent duplicates.",
        "how to configure Prometheus alerting rules",
        "Prometheus alerting rules define conditions for notifications",
    ),
    # ── 11–20: Security & Network ────────────────────────────────────────
    (
        "Налаштування NFTables фаєрвола",
        "NFTables є сучасною заміною iptables в Linux. Правила описуються "
        "в таблицях з ланцюгами input, output та forward. Використовуйте "
        "nft для додавання правил блокування портів.",
        "як налаштувати NFTables фаєрвол",
        "NFTables є сучасною заміною iptables в Linux",
        "NFTables Firewall Configuration",
        "NFTables is the modern replacement for iptables on Linux. Rules are defined "
        "in tables with input, output, and forward chains. Use nft to add port blocking rules.",
        "how to configure NFTables firewall",
        "NFTables is the modern replacement for iptables on Linux",
    ),
    (
        "Захист SSH з Fail2ban",
        "Fail2ban захищає SSH від брутфорс атак. Він аналізує логи та блокує "
        "IP після N невдалих спроб. Налаштуйте maxretry = 5 та bantime = 3600.",
        "як налаштувати Fail2ban для захисту SSH",
        "Fail2ban захищає SSH від брутфорс атак",
        "SSH Protection with Fail2ban",
        "Fail2ban protects SSH from brute-force attacks. It analyzes logs and blocks "
        "IPs after N failed attempts. Configure maxretry = 5 and bantime = 3600.",
        "how to configure Fail2ban for SSH protection",
        "Fail2ban protects SSH from brute-force attacks",
    ),
    (
        "TLS сертифікати Let's Encrypt",
        "Let's Encrypt надає безкоштовні TLS сертифікати через протокол ACME. "
        "Certbot автоматизує отримання та оновлення сертифікатів. "
        "Сертифікати дійсні 90 днів, оновлюйте їх через cron.",
        "як отримати TLS сертифікати Let's Encrypt",
        "Let's Encrypt надає безкоштовні TLS сертифікати через протокол ACME",
        "Let's Encrypt TLS Certificates",
        "Let's Encrypt provides free TLS certificates via the ACME protocol. Certbot "
        "automates certificate issuance and renewal. Certificates are valid for 90 days.",
        "how to obtain Let's Encrypt TLS certificates",
        "Let's Encrypt provides free TLS certificates via the ACME protocol",
    ),
    (
        "Tailscale VPN налаштування",
        "Tailscale створює mesh VPN на основі WireGuard. Пристрої отримують "
        "унікальні IP в мережі 100.x.x.x. Налаштуйте ACL для контролю "
        "доступу між пристроями.",
        "як налаштувати Tailscale VPN",
        "Tailscale створює mesh VPN на основі WireGuard",
        "Tailscale VPN Setup",
        "Tailscale creates a mesh VPN based on WireGuard. Devices get unique IPs "
        "in the 100.x.x.x range. Configure ACLs for access control between devices.",
        "how to set up Tailscale VPN",
        "Tailscale creates a mesh VPN based on WireGuard",
    ),
    (
        "Аудит безпеки інфраструктури",
        "Аудит безпеки включає перевірку firewall правил, TLS сертифікатів "
        "та доступу до VPN. Використовуйте nmap для сканування портів та "
        "Lynis для перевірки системи.",
        "як провести аудит безпеки інфраструктури",
        "Аудит безпеки включає перевірку firewall правил, TLS сертифікатів та доступу до VPN",
        "Infrastructure Security Audit",
        "Security audit includes reviewing firewall rules, TLS certificates, and VPN "
        "access. Use nmap for port scanning and Lynis for system hardening checks.",
        "how to conduct infrastructure security audit",
        "Security audit includes reviewing firewall rules, TLS certificates, and VPN access",
    ),
    (
        "Посилення безпеки SSH",
        "Посилення безпеки SSH включає відключення root логіну, використання "
        "ключів замість паролів та зміну стандартного порту. Налаштуйте "
        "PermitRootLogin no та PasswordAuthentication no.",
        "як посилити безпеку SSH сервера",
        "Посилення безпеки SSH включає відключення root логіну, використання ключів замість паролів",
        "SSH Security Hardening",
        "SSH hardening includes disabling root login, using key-based authentication "
        "instead of passwords, and changing the default port. Set PermitRootLogin no "
        "and PasswordAuthentication no.",
        "how to harden SSH server security",
        "SSH hardening includes disabling root login, using key-based authentication instead of passwords",
    ),
    (
        "API Gateway з FastAPI",
        "FastAPI дозволяє створити API Gateway з високою продуктивністю. "
        "Використовуйте middleware для автентифікації та rate limiting. "
        "Pydantic моделі забезпечують валідацію даних.",
        "як створити API Gateway з FastAPI",
        "FastAPI дозволяє створити API Gateway з високою продуктивністю",
        "API Gateway with FastAPI",
        "FastAPI enables high-performance API Gateway creation. Use middleware for "
        "authentication and rate limiting. Pydantic models provide data validation.",
        "how to build API Gateway with FastAPI",
        "FastAPI enables high-performance API Gateway creation",
    ),
    (
        "Rate Limiting в API Gateway",
        "Rate limiting обмежує кількість запитів до API. Використовуйте "
        "Redis для зберігання лічильників. Алгоритм sliding window "
        "забезпечує точне обмеження, наприклад 100 запитів за хвилину.",
        "як налаштувати rate limiting в API Gateway",
        "Rate limiting обмежує кількість запитів до API",
        "Rate Limiting in API Gateway",
        "Rate limiting restricts the number of API requests. Use Redis for counter "
        "storage. The sliding window algorithm provides accurate limits, e.g., 100 requests per minute.",
        "how to configure rate limiting in API Gateway",
        "Rate limiting restricts the number of API requests",
    ),
    (
        "JWT автентифікація в FastAPI",
        "JWT (JSON Web Token) забезпечує автентифікацію в FastAPI. "
        "Токен містить payload з user_id та expiration. "
        "Використовуйте python-jose для створення та верифікації токенів.",
        "як налаштувати JWT автентифікацію в FastAPI",
        "JWT (JSON Web Token) забезпечує автентифікацію в FastAPI",
        "JWT Authentication in FastAPI",
        "JWT (JSON Web Token) provides authentication in FastAPI. The token contains "
        "a payload with user_id and expiration. Use python-jose for token creation and verification.",
        "how to configure JWT authentication in FastAPI",
        "JWT (JSON Web Token) provides authentication in FastAPI",
    ),
    (
        "Redis кешування для FastAPI",
        "Redis забезпечує швидке кешування даних в FastAPI додатках. "
        "Використовуйте redis-py для взаємодії. TTL (time to live) "
        "автоматично видаляє застарілі дані з кешу.",
        "як використовувати Redis для кешування в FastAPI",
        "Redis забезпечує швидке кешування даних в FastAPI додатках",
        "Redis Caching for FastAPI",
        "Redis provides fast data caching for FastAPI applications. Use redis-py for "
        "interaction. TTL (time to live) automatically removes stale cached data.",
        "how to use Redis caching for FastAPI",
        "Redis provides fast data caching for FastAPI applications",
    ),
    # ── 21–30: Development & Testing ──────────────────────────────────────
    (
        "Асинхронний Python з asyncio",
        "asyncio дозволяє писати конкурентний код в Python. Використовуйте "
        "async/await для корутин. ThreadPoolExecutor виконує блокуючі "
        "операції в окремому потоці без блокування event loop.",
        "як використовувати asyncio для асинхронного Python",
        "asyncio дозволяє писати конкурентний код в Python",
        "Async Python with asyncio",
        "asyncio enables concurrent Python code. Use async/await for coroutines. "
        "ThreadPoolExecutor runs blocking operations in a separate thread without "
        "blocking the event loop.",
        "how to use asyncio for async Python",
        "asyncio enables concurrent Python code",
    ),
    (
        "Pydantic валідація даних",
        "Pydantic забезпечує валідацію даних через Python-типи. BaseModel "
        "автоматично перевіряє та конвертує поля. Використовуйте "
        "Field для додаткових обмежень та валідаторів.",
        "як використовувати Pydantic для валідації даних",
        "Pydantic забезпечує валідацію даних через Python-типи",
        "Pydantic Data Validation",
        "Pydantic provides data validation through Python types. BaseModel automatically "
        "validates and converts fields. Use Field for additional constraints and validators.",
        "how to use Pydantic for data validation",
        "Pydantic provides data validation through Python types",
    ),
    (
        "SQLAlchemy ORM асинхронні запити",
        "SQLAlchemy підтримує асинхронні запити через AsyncSession. "
        "Використовуйте select для побудови запитів та await session.execute. "
        "Declarative Base визначає моделі даних.",
        "як писати асинхронні запити з SQLAlchemy",
        "SQLAlchemy підтримує асинхронні запити через AsyncSession",
        "SQLAlchemy ORM Async Queries",
        "SQLAlchemy supports async queries via AsyncSession. Use select for query "
        "building and await session.execute. Declarative Base defines data models.",
        "how to write async queries with SQLAlchemy",
        "SQLAlchemy supports async queries via AsyncSession",
    ),
    (
        "FastAPI розробка веб-додатків",
        "FastAPI є високопродуктивним веб-фреймворком для Python. "
        "Автоматична генерація OpenAPI документації. Використовуйте "
        "Depends для ін'єкції залежностей.",
        "як розробляти веб-додатки з FastAPI",
        "FastAPI є високопродуктивним веб-фреймворком для Python",
        "FastAPI Web Development",
        "FastAPI is a high-performance web framework for Python. It auto-generates "
        "OpenAPI documentation. Use Depends for dependency injection.",
        "how to develop web applications with FastAPI",
        "FastAPI is a high-performance web framework for Python",
    ),
    (
        "Тестування з Pytest",
        "Pytest є фреймворком для тестування Python коду. Fixtures "
        "забезпечують багаторазове використання тестових даних. "
        "Parametrize дозволяє запускати один тест з різними параметрами.",
        "як використовувати Pytest для тестування Python",
        "Pytest є фреймворком для тестування Python коду",
        "Testing with Pytest",
        "Pytest is a testing framework for Python code. Fixtures provide reusable "
        "test data. Parametrize runs one test with multiple parameter sets.",
        "how to use Pytest for Python testing",
        "Pytest is a testing framework for Python code",
    ),
    (
        "Логування з systemd та journalctl",
        "systemd збирає логи сервісів через journald. journalctl дозволяє "
        "переглядати та фільтрувати логи. Використовуйте journalctl -u "
        "для фільтрації за сервісом та -p для рівня важливості.",
        "як переглядати логи через systemd та journalctl",
        "systemd збирає логи сервісів через journald",
        "Logging with systemd and journalctl",
        "systemd collects service logs via journald. journalctl allows viewing and "
        "filtering logs. Use journalctl -u to filter by service and -p for priority level.",
        "how to view logs with systemd and journalctl",
        "systemd collects service logs via journald",
    ),
    (
        "Налаштування PostgreSQL продуктивності",
        "PostgreSQL продуктивність залежить від налаштувань shared_buffers, "
        "work_mem та effective_cache_size. Використовуйте EXPLAIN ANALYZE "
        "для аналізу повільних запитів.",
        "як налаштувати продуктивність PostgreSQL",
        "PostgreSQL продуктивність залежить від налаштувань shared_buffers, work_mem",
        "PostgreSQL Performance Tuning",
        "PostgreSQL performance depends on shared_buffers, work_mem, and "
        "effective_cache_size settings. Use EXPLAIN ANALYZE for slow query analysis.",
        "how to tune PostgreSQL performance",
        "PostgreSQL performance depends on shared_buffers, work_mem",
    ),
    (
        "Міграція PostgreSQL 14 на 16",
        "Міграція PostgreSQL з версії 14 на 16 включає бекап, реплікацію "
        "та валідацію. Використовуйте pg_dump та pg_restore. "
        "Очікуваний час простою — 30 хвилин.",
        "як мігрувати PostgreSQL з 14 на 16",
        "Міграція PostgreSQL з версії 14 на 16 включає бекап, реплікацію та валідацію",
        "PostgreSQL 14 to 16 Migration",
        "Migrating PostgreSQL from version 14 to 16 includes backup, replication, "
        "and validation. Use pg_dump and pg_restore. Expected downtime is 30 minutes.",
        "how to migrate PostgreSQL from 14 to 16",
        "Migrating PostgreSQL from version 14 to 16 includes backup, replication, and validation",
    ),
    (
        "Резервне копіювання PostgreSQL",
        "Резервне копіювання PostgreSQL виконується через pg_dump. "
        "Для великих баз використовуйте pg_basebackup. "
        "Відновлення виконується через pg_restore або COPY з бекапу.",
        "як створити резервну копію PostgreSQL",
        "Резервне копіювання PostgreSQL виконується через pg_dump",
        "PostgreSQL Backup and Restore",
        "PostgreSQL backup is performed via pg_dump. For large databases use "
        "pg_basebackup. Restore via pg_restore or COPY from backup.",
        "how to backup and restore PostgreSQL",
        "PostgreSQL backup is performed via pg_dump",
    ),
    (
        "SQLite вбудована база даних",
        "SQLite є вбудованою реляційною базою даних без окремого сервера. "
        "Дані зберігаються в одному файлі. Ідеально для мобільних "
        "додатків та тестування.",
        "що таке SQLite вбудована база даних",
        "SQLite є вбудованою реляційною базою даних без окремого сервера",
        "SQLite Embedded Database",
        "SQLite is an embedded relational database without a separate server. Data is "
        "stored in a single file. Ideal for mobile apps and testing.",
        "what is SQLite embedded database",
        "SQLite is an embedded relational database without a separate server",
    ),
    # ── 31–40: System Administration ──────────────────────────────────────
    (
        "ZFS файлова система",
        "ZFS забезпечує цілісність даних та високу ємність. Підтримує "
        "snapshot, compression та deduplication. Використовуйте zpool "
        "для створення пулів зберігання.",
        "як налаштувати ZFS файлову систему",
        "ZFS забезпечує цілісність даних та високу ємність",
        "ZFS Filesystem",
        "ZFS provides data integrity and high capacity. Supports snapshots, compression, "
        "and deduplication. Use zpool to create storage pools.",
        "how to configure ZFS filesystem",
        "ZFS provides data integrity and high capacity",
    ),
    (
        "Linux адміністрування серверів",
        "Linux адміністрування включає управління systemd сервісами, "
        "моніторинг через journalctl та налаштування sudo. "
        "Cron виконує планові завдання за розкладом.",
        "як адмініструвати Linux сервер",
        "Linux адміністрування включає управління systemd сервісами",
        "Linux Server Administration",
        "Linux administration includes managing systemd services, monitoring via "
        "journalctl, and sudo configuration. Cron runs scheduled tasks.",
        "how to administer Linux server",
        "Linux administration includes managing systemd services",
    ),
    (
        "Cron планові завдання",
        "Cron дозволяє виконувати завдання за розкладом в Linux. "
        "Формат: хвилина година день місяць день_тижня. "
        "Наприклад, 0 3 * * * означає щодня о 3 ранку.",
        "як налаштувати cron планові завдання в Linux",
        "Cron дозволяє виконувати завдання за розкладом в Linux",
        "Cron Scheduled Tasks",
        "Cron executes scheduled tasks in Linux. Format: minute hour day month weekday. "
        "For example, 0 3 * * * means daily at 3 AM.",
        "how to schedule cron tasks in Linux",
        "Cron executes scheduled tasks in Linux",
    ),
    (
        "Docker Healthcheck налаштування",
        "Docker HEALTHCHECK перевіряє працездатність контейнера. "
        "Налаштуйте інтервал перевірки та кількість ретраїв. "
        "Приклад: HEALTHCHECK --interval=30s --retries=3 CMD curl -f http://localhost",
        "як налаштувати Docker HEALTHCHECK",
        "Docker HEALTHCHECK перевіряє працездатність контейнера",
        "Docker Healthcheck Configuration",
        "Docker HEALTHCHECK verifies container readiness. Configure check interval "
        "and retry count. Example: HEALTHCHECK --interval=30s --retries=3 CMD curl -f http://localhost",
        "how to configure Docker HEALTHCHECK",
        "Docker HEALTHCHECK verifies container readiness",
    ),
    (
        "BGE-M3 модель ембедінгів",
        "BGE-M3 це багатомовна модель ембедінгів від BAAI з 1024 вимірами. "
        "Підтримує 100+ мов. Використовуйте ONNX runtime для інференсу.",
        "що таке BGE-M3 модель ембедінгів",
        "BGE-M3 це багатомовна модель ембедінгів від BAAI з 1024 вимірами",
        "BGE-M3 Embedding Model",
        "BGE-M3 is a multilingual embedding model from BAAI with 1024 dimensions. "
        "Supports 100+ languages. Use ONNX runtime for inference.",
        "what is BGE-M3 embedding model",
        "BGE-M3 is a multilingual embedding model from BAAI with 1024 dimensions",
    ),
    (
        "miniLM модель ембедінгів",
        "miniLM є легкою моделлю ембедінгів від Microsoft. "
        "384 виміри, підходить для обмежених ресурсів. "
        "Використовується як fallback коли BGE-M3 недоступний.",
        "що таке miniLM модель ембедінгів",
        "miniLM є легкою моделлю ембедінгів від Microsoft",
        "miniLM Embedding Model",
        "miniLM is a lightweight embedding model from Microsoft with 384 dimensions. "
        "Suitable for resource-constrained environments. Used as fallback when BGE-M3 is unavailable.",
        "what is miniLM embedding model",
        "miniLM is a lightweight embedding model from Microsoft with 384 dimensions",
    ),
    (
        "Cross-Encoder для реранкінгу",
        "Cross-Encoder оцінює релевантність пари query-document. "
        "На відміну від bi-encoder, він враховує взаємодію слів. "
        "Повільніший але точніший, використовується для фінального ранжування.",
        "як працює Cross-Encoder для реранкінгу",
        "Cross-Encoder оцінює релевантність пари query-document",
        "Cross-Encoder for Reranking",
        "Cross-Encoder scores query-document relevance pairs. Unlike bi-encoder, "
        "it considers word interaction. Slower but more accurate, used for final ranking.",
        "how does Cross-Encoder reranking work",
        "Cross-Encoder scores query-document relevance pairs",
    ),
    (
        "Метрика nDCG для оцінки пошуку",
        "nDCG (Normalized Discounted Cumulative Gain) оцінює якість "
        "ранжування. Враховує позицію релевантних документів. "
        "nDCG@10 вимірює якість топ-10 результатів.",
        "що таке метрика nDCG для оцінки пошуку",
        "nDCG (Normalized Discounted Cumulative Gain) оцінює якість ранжування",
        "nDCG Metric for Search Evaluation",
        "nDCG (Normalized Discounted Cumulative Gain) evaluates ranking quality. "
        "It considers the position of relevant documents. nDCG@10 measures top-10 quality.",
        "what is nDCG metric for search evaluation",
        "nDCG (Normalized Discounted Cumulative Gain) evaluates ranking quality",
    ),
    (
        "Метрика UDCG for пошуку",
        "UDCG (Ungraded Discounted Cumulative Gain) є варіантом DCG "
        "без градацій релевантності. Використовується коли релевантність "
        "бінарна. Простіший за nDCG але менш інформативний.",
        "що таке метрика UDCG",
        "UDCG (Ungraded Discounted Cumulative Gain) є варіантом DCG",
        "UDCG Metric for Search",
        "UDCG (Ungraded Discounted Cumulative Gain) is a variant of DCG without "
        "relevance grades. Used when relevance is binary. Simpler than nDCG but less informative.",
        "what is UDCG metric",
        "UDCG (Ungraded Discounted Cumulative Gain) is a variant of DCG",
    ),
    (
        "FTS5 пошуковий індекс",
        "FTS5 є повнотекстовим пошуковим індексом в SQLite. "
        "Підтримує ранжування за BM25. Швидший за LIKE "
        "для пошуку тексту в великих таблицях.",
        "що таке FTS5 пошуковий індекс",
        "FTS5 є повнотекстовим пошуковим індексом в SQLite",
        "FTS5 Search Index",
        "FTS5 is a full-text search index in SQLite. Supports BM25 ranking. "
        "Faster than LIKE for text search in large tables.",
        "what is FTS5 search index",
        "FTS5 is a full-text search index in SQLite",
    ),
    # ── 41–50: AI, LLM & Knowledge Management ────────────────────────────
    (
        "Chain-of-Thought промптинг",
        "Chain-of-Thought (CoT) покращує логічне міркування LLM. "
        "Додайте кроки міркування в промпт. Few-shot CoT "
        "надає приклади міркування для кращих результатів.",
        "як використовувати Chain-of-Thought промптинг",
        "Chain-of-Thought (CoT) покращує логічне міркування LLM",
        "Chain-of-Thought Prompting",
        "Chain-of-Thought (CoT) improves LLM logical reasoning. Add reasoning "
        "steps in the prompt. Few-shot CoT provides reasoning examples for better results.",
        "how to use Chain-of-Thought prompting",
        "Chain-of-Thought (CoT) improves LLM logical reasoning",
    ),
    (
        "Дизайн промптів для LLM",
        "Ефективний дизайн промптів включає system prompt з контекстом "
        "та user prompt з завданням. Використовуйте конкретні "
        "інструкції та приклади для кращих відповідей LLM.",
        "як дизайнити ефективні промпти для LLM",
        "Ефективний дизайн промптів включає system prompt з контекстом",
        "LLM Prompt Design",
        "Effective prompt design includes a system prompt with context and a user "
        "prompt with the task. Use specific instructions and examples for better LLM responses.",
        "how to design effective LLM prompts",
        "Effective prompt design includes a system prompt with context",
    ),
    (
        "OKF метадані для нотаток",
        "OKF (Open Knowledge Format) визначає структуру метаданих нотаток. "
        "Включає поля type, title, description та timestamp. "
        "Використовується в P.A.R.A. методології.",
        "що таке OKF метадані для нотаток",
        "OKF (Open Knowledge Format) визначає структуру метаданих нотаток",
        "OKF Metadata for Notes",
        "OKF (Open Knowledge Format) defines note metadata structure. Includes "
        "type, title, description, and timestamp fields. Used in P.A.R.A. methodology.",
        "what is OKF metadata for notes",
        "OKF (Open Knowledge Format) defines note metadata structure",
    ),
    (
        "P.A.R.A. методологія організації знань",
        "P.A.R.A. складається з Projects, Areas, Resources та Archives. "
        "Projects мають дедлайни. Areas є постійними сферами "
        "відповідальності.",
        "що таке P.A.R.A. методологія",
        "P.A.R.A. складається з Projects, Areas, Resources та Archives",
        "P.A.R.A. Knowledge Organization",
        "P.A.R.A. consists of Projects, Areas, Resources, and Archives. Projects "
        "have deadlines. Areas are ongoing responsibilities.",
        "what is P.A.R.A. methodology",
        "P.A.R.A. consists of Projects, Areas, Resources, and Archives",
    ),
    (
        "POWER Framework управління",
        "POWER Framework об'єднує P.A.R.A. та OKF з LLM-агентами. "
        "Включає індексацію, пошук та ROT аудит. "
        "Використовує BGE-M3 для багатомовного пошуку.",
        "що таке POWER Framework",
        "POWER Framework об'єднує P.A.R.A. та OKF з LLM-агентами",
        "POWER Framework Management",
        "POWER Framework combines P.A.R.A. and OKF with LLM agents. Includes "
        "indexing, search, and ROT audit. Uses BGE-M3 for multilingual search.",
        "what is POWER Framework",
        "POWER Framework combines P.A.R.A. and OKF with LLM agents",
    ),
    (
        "MCP Server для AI агентів",
        "MCP (Model Context Protocol) сервер дозволяє AI агентам "
        "взаємодіяти з інструментами. FastMCP спрощує створення "
        "серверів. Підтримує ресурси, інструменти та промпти.",
        "що таке MCP Server для AI агентів",
        "MCP (Model Context Protocol) сервер дозволяє AI агентам взаємодіяти з інструментами",
        "MCP Server for AI Agents",
        "MCP (Model Context Protocol) server enables AI agents to interact with "
        "tools. FastMCP simplifies server creation. Supports resources, tools, and prompts.",
        "what is MCP Server for AI agents",
        "MCP (Model Context Protocol) server enables AI agents to interact with tools",
    ),
    (
        "Graph RAG пошук знань",
        "Graph RAG поєднує графові зв'язки з RAG пошуком. "
        "Замість flat chunks використовує зв'язки між концепціями. "
        "Покращує релевантність для багатоходових запитів.",
        "що таке Graph RAG пошук знань",
        "Graph RAG поєднує графові зв'язки з RAG пошуком",
        "Graph RAG Knowledge Search",
        "Graph RAG combines graph relationships with RAG search. Instead of flat "
        "chunks, it uses concept relationships. Improves relevance for multi-hop queries.",
        "what is Graph RAG knowledge search",
        "Graph RAG combines graph relationships with RAG search",
    ),
    (
        "Порівняння моделей ембедінгів",
        "BGE-M3 має 1024 виміри та підтримує 100+ мов. "
        "OpenAI embeddings мають 1536 виміри але платні. "
        "miniLM має 384 виміри та найшвидший.",
        "порівняння моделей ембедінгів BGE-M3 OpenAI miniLM",
        "BGE-M3 має 1024 виміри та підтримує 100+ мов",
        "Embedding Models Comparison",
        "BGE-M3 has 1024 dimensions and supports 100+ languages. "
        "OpenAI embeddings have 1536 dimensions but are paid. "
        "miniLM has 384 dimensions and is fastest.",
        "compare embedding models BGE-M3 OpenAI miniLM",
        "BGE-M3 has 1024 dimensions and supports 100+ languages",
    ),
    (
        "Service Mesh з Istio",
        "Istio забезпечує service mesh для Kubernetes мікросервісів. "
        "Додає mutual TLS, traffic management та observability. "
        "Envoy proxy працює як sidecar в кожному поді.",
        "що таке Service Mesh з Istio",
        "Istio забезпечує service mesh для Kubernetes мікросервісів",
        "Service Mesh with Istio",
        "Istio provides service mesh for Kubernetes microservices. Adds mutual TLS, "
        "traffic management, and observability. Envoy proxy runs as sidecar in each pod.",
        "what is Service Mesh with Istio",
        "Istio provides service mesh for Kubernetes microservices",
    ),
    (
        "Disaster Recovery план",
        "Disaster Recovery план включає RTO (Recovery Time Objective) "
        "та RPO (Recovery Point Objective). Резервне копіювання "
        "в різні регіони. Регулярне тестування відновлення.",
        "що таке Disaster Recovery план",
        "Disaster Recovery план включає RTO (Recovery Time Objective) та RPO",
        "Disaster Recovery Plan",
        "Disaster Recovery plan defines RTO (Recovery Time Objective) "
        "and RPO (Recovery Point Objective). Multi-region backups. Regular restoration testing.",
        "what is Disaster Recovery plan",
        "Disaster Recovery plan defines RTO (Recovery Time Objective) and RPO",
    ),
]

# ── Absent topics (not in corpus) ──────────────────────────────────────────
ABSENT_DATA: list[tuple[str, str, str, str]] = [
    (
        "як налаштувати TensorFlow на GPU",
        "TensorFlow потребує CUDA та cuDNN для роботи на GPU",
        "how to configure TensorFlow on GPU",
        "TensorFlow requires CUDA and cuDNN for GPU support",
    ),
    (
        "як створити S3 сумісне сховище",
        "MinIO надає S3-сумісне об'єктне сховище",
        "how to set up S3 compatible storage",
        "MinIO provides S3-compatible object storage",
    ),
    (
        "як розробляти React компоненти",
        "React використовує JSX для створення компонентів",
        "how to develop React components",
        "React uses JSX to create components",
    ),
    (
        "як налаштувати RabbitMQ черги",
        "RabbitMQ використовує AMQP протокол для черг повідомлень",
        "how to configure RabbitMQ queues",
        "RabbitMQ uses AMQP protocol for message queues",
    ),
    (
        "як індексувати дані в Elasticsearch",
        "Elasticsearch використовує інвертований індекс для пошуку",
        "how to index data in Elasticsearch",
        "Elasticsearch uses inverted index for search",
    ),
]

# ── Distractor query definitions ──────────────────────────────────────────
# (query_id, query, lang, target_lang, stratum, q_class, tags,
#  primary_topic_idx, distractor_topic_idx)
DISTRACTOR_DEFS = [
    (
        "QDD0001",
        "What is the best embedding model for multilingual search?",
        "en",
        "en",
        "en_to_en",
        "conceptual",
        ["embedding", "distractor"],
        34,
        35,
    ),
    (
        "QDD0002",
        "Яка найкраща модель ембедінгів для багатомовного пошуку?",
        "uk",
        "uk",
        "ua_to_ua",
        "conceptual",
        ["embedding", "distractor"],
        34,
        35,
    ),
    (
        "QDD0003",
        "Compare Docker build strategies for production",
        "en",
        "en",
        "en_to_en",
        "conceptual",
        ["docker", "distractor"],
        0,
        1,
    ),
    (
        "QDD0004",
        "Порівняння стратегій збірки Docker для продакшну",
        "uk",
        "uk",
        "ua_to_ua",
        "conceptual",
        ["docker", "distractor"],
        0,
        1,
    ),
    (
        "QDD0005",
        "Kubernetes vs Nomad for container orchestration",
        "en",
        "en",
        "en_to_en",
        "conceptual",
        ["kubernetes", "distractor"],
        2,
        3,
    ),
    (
        "QDD0006",
        "Kubernetes чи Nomad для оркестрації контейнерів",
        "uk",
        "uk",
        "ua_to_ua",
        "conceptual",
        ["kubernetes", "distractor"],
        2,
        3,
    ),
    (
        "QDD0007",
        "Best monitoring stack for production infrastructure",
        "en",
        "en",
        "en_to_en",
        "conceptual",
        ["monitoring", "distractor"],
        8,
        9,
    ),
    (
        "QDD0008",
        "Найкращий стек моніторингу для продакшн інфраструктури",
        "uk",
        "uk",
        "ua_to_ua",
        "conceptual",
        ["monitoring", "distractor"],
        8,
        9,
    ),
]


def did(topic_idx: int, lang: str) -> str:
    """Deterministic document ID for a topic.

    Use 'ua' for Ukrainian documents in the doc_id, 'en' for English.
    The lang parameter is the internal code ('uk' or 'en').
    """
    suffix = "ua" if lang == "uk" else "en"
    return f"topic-{topic_idx + 1:03d}-{suffix}.md"


def make_okf_content(record: tuple, lang: str) -> str:
    """Generate OKF markdown content for a document."""
    if lang == "uk":
        title, content = record[0], record[1]
        ts = "2026-01-15T10:00:00"
        ntype = "Resource"
    else:
        title, content = record[4], record[5]
        ts = "2026-01-15T10:00:00"
        ntype = "Resource"
    # Truncate description to first 80 chars
    desc = content[:80].replace('"', "'")
    return (
        f"---\n"
        f"type: {ntype}\n"
        f'title: "{title}"\n'
        f'description: "{desc}"\n'
        f"timestamp: {ts}\n"
        f"---\n"
        f"\n"
        f"# {title}\n"
        f"\n"
        f"{content}\n"
    )


def generate_corpus(out_root: Path) -> dict[str, str]:
    """Write topic documents and return {doc_id: content}."""
    corpus: dict[str, str] = {}
    corpus_dir = out_root / "corpus"
    corpus_dir.mkdir(parents=True, exist_ok=True)

    for idx, record in enumerate(TOPIC_DATA):
        for lang in ("uk", "en"):
            doc_id = did(idx, lang)
            content = make_okf_content(record, lang)
            (corpus_dir / doc_id).write_text(content, encoding="utf-8")
            corpus[doc_id] = content
    return corpus


def generate_queries(corpus: dict[str, str]) -> list[dict[str, Any]]:
    """Generate 200 answerable + 20 no-answer + 8 distractor queries."""
    queries: list[dict[str, Any]] = []

    # ── 200 answerable base queries (4 per topic) ────────────────────────
    for idx, record in enumerate(TOPIC_DATA):
        ua_q = record[2]
        en_q = record[6]
        for stratum in STRATA:
            q_lang, t_lang = LANG_MAP[stratum]
            q_text = ua_q if q_lang == "uk" else en_q
            prefix = {
                "ua_to_ua": "QUU",
                "en_to_en": "QEE",
                "ua_to_en": "QUE",
                "en_to_ua": "QEU",
            }[stratum]

            queries.append(
                {
                    "query_id": f"{prefix}{idx + 1:04d}",
                    "query": q_text,
                    "language": q_lang,
                    "target_language": t_lang,
                    "stratum": stratum,
                    "query_class": "conceptual",
                    "tags": [f"topic_{idx + 1:03d}"],
                }
            )

    # ── 20 no-answer queries (5 absent × 4 strata) ───────────────────────
    for abs_idx, record in enumerate(ABSENT_DATA):
        ua_q, _ua_ans, en_q, _en_ans = record
        for stratum in STRATA:
            q_lang, _ = LANG_MAP[stratum]
            q_text = ua_q if q_lang == "uk" else en_q
            prefix = {
                "ua_to_ua": "QNUU",
                "en_to_en": "QNEE",
                "ua_to_en": "QNUE",
                "en_to_ua": "QNEU",
            }[stratum]
            queries.append(
                {
                    "query_id": f"{prefix}{abs_idx + 1:04d}",
                    "query": q_text,
                    "language": q_lang,
                    "target_language": _,
                    "stratum": stratum,
                    "query_class": "no_answer",
                    "tags": ["no_answer", f"absent_{abs_idx + 1:03d}"],
                }
            )

    # ── 8 distractor queries ──────────────────────────────────────────────
    queries.extend(
        {
            "query_id": defn[0],
            "query": defn[1],
            "language": defn[2],
            "target_language": defn[3],
            "stratum": defn[4],
            "query_class": defn[5],
            "tags": defn[6],
        }
        for defn in DISTRACTOR_DEFS
    )

    return queries


def generate_qrels(
    queries: list[dict[str, Any]],
    corpus: dict[str, str],
) -> list[dict[str, Any]]:
    """Generate sparse qrels: primary + secondary positive, plus distractor.

    Missing (query_id, doc_id) pair ⇒ relevance 0.

    Base answerable queries (QUU/QEE/QUE/QEU):
      - 1 primary: topic's doc matching target_language
      - 1 secondary: paired topic's doc in same target_language

    No-answer queries (QNUU/QNEE/QNUE/QNEU):
      - NO entries (all zero by convention)

    Distractor queries (QDD*):
      - 1 primary from primary_topic_idx
      - 1 distractor from distractor_topic_idx (relevance=2, utility=-0.5)
    """
    qrels: list[dict[str, Any]] = []

    # Build query → topic mapping
    qid_to_topic: dict[str, int] = {}
    qid_to_stratum: dict[str, str] = {}
    qid_to_class: dict[str, str] = {}
    qid_to_is_answerable: dict[str, bool] = {}
    for q in queries:
        qid = q["query_id"]
        qid_to_stratum[qid] = q["stratum"]
        qid_to_class[qid] = q["query_class"]
        qid_to_is_answerable[qid] = q["query_class"] != "no_answer"
        if q["query_class"] != "no_answer" and not qid.startswith("QDD"):
            # Extract topic index from tags
            for tag in q.get("tags", []):
                if tag.startswith("topic_"):
                    qid_to_topic[qid] = int(tag.split("_")[1]) - 1  # 0-based

    now_iso = FIXED_TIMESTAMP

    # ── Base answerable queries ───────────────────────────────────────────
    for q in queries:
        qid = q["query_id"]
        if q["query_class"] == "no_answer":
            continue
        if qid.startswith("QDD"):
            continue

        # QID format determines stratum, extract topic from tags
        idx = qid_to_topic.get(qid)
        if idx is None:
            continue
        stratum = q["stratum"]
        t_lang = LANG_MAP[stratum][1]
        lang_code = "uk" if t_lang == "uk" else "en"

        primary_doc = did(idx, lang_code)
        pair_idx = PAIRS.get(idx + 1, idx) - 1  # 0-based
        secondary_doc = did(pair_idx, lang_code)

        # Primary
        if primary_doc in corpus:
            qrels.append(
                {
                    "query_id": qid,
                    "document_id": primary_doc,
                    "relevance": 2,
                    "utility": 0.8,
                    "distractor": False,
                    "language_direction": stratum,
                    "query_class": q["query_class"],
                    "annotator": ANNOTATOR,
                    "rubric_version": RUBRIC_VERSION,
                    "timestamp": now_iso,
                }
            )

        # Secondary (paired topic)
        if secondary_doc in corpus and secondary_doc != primary_doc:
            qrels.append(
                {
                    "query_id": qid,
                    "document_id": secondary_doc,
                    "relevance": 1,
                    "utility": 0.3,
                    "distractor": False,
                    "language_direction": stratum,
                    "query_class": q["query_class"],
                    "annotator": ANNOTATOR,
                    "rubric_version": RUBRIC_VERSION,
                    "timestamp": now_iso,
                }
            )

    # ── Distractor queries ────────────────────────────────────────────────
    for defn in DISTRACTOR_DEFS:
        qid = defn[0]
        stratum = defn[4]
        q_class = defn[5]
        prim_idx = defn[7]
        dist_idx = defn[8]
        t_lang = LANG_MAP[stratum][1]
        lang_code = "uk" if t_lang == "uk" else "en"

        primary_doc = did(prim_idx, lang_code)
        distractor_doc = did(dist_idx, lang_code)

        # Primary
        if primary_doc in corpus:
            qrels.append(
                {
                    "query_id": qid,
                    "document_id": primary_doc,
                    "relevance": 2,
                    "utility": 0.8,
                    "distractor": False,
                    "language_direction": stratum,
                    "query_class": q_class,
                    "annotator": ANNOTATOR,
                    "rubric_version": RUBRIC_VERSION,
                    "timestamp": now_iso,
                }
            )

        # Distractor
        if distractor_doc in corpus and distractor_doc != primary_doc:
            qrels.append(
                {
                    "query_id": qid,
                    "document_id": distractor_doc,
                    "relevance": 2,
                    "utility": -0.5,
                    "distractor": True,
                    "distractor_reason": (
                        "topically similar but does not support the target atomic fact"
                    ),
                    "language_direction": stratum,
                    "query_class": q_class,
                    "annotator": ANNOTATOR,
                    "rubric_version": RUBRIC_VERSION,
                    "timestamp": now_iso,
                }
            )

    # Sort for deterministic output
    qrels.sort(key=lambda x: (x["query_id"], x["document_id"]))
    return qrels


def generate_expected_answers(
    queries: list[dict[str, Any]],
    qrels: list[dict[str, Any]],
    corpus: dict[str, str],
) -> list[dict[str, Any]]:
    """Build expected answers with real atomic facts from topic records.

    citation_document_ids = only primary (non-distractor, relevance>=2) docs.
    """
    # Build primary doc map: query_id → [primary doc ids]
    primary_map: dict[str, list[str]] = {}
    for qrel in qrels:
        if qrel["relevance"] >= 2 and not qrel.get("distractor", False):
            primary_map.setdefault(qrel["query_id"], []).append(qrel["document_id"])

    answers: list[dict[str, Any]] = []

    for q in queries:
        qid = q["query_id"]
        is_no_answer = q["query_class"] == "no_answer"

        if is_no_answer:
            answers.append(
                {
                    "query_id": qid,
                    "expected_answer": "This query cannot be answered from the available documents.",
                    "atomic_facts": ["No relevant information available in the corpus."],
                    "forbidden_facts": [],
                    "citation_document_ids": [],
                    "no_answer": True,
                }
            )
            continue

        # Derive atomic answer from topic record
        idx = None
        for tag in q.get("tags", []):
            if tag.startswith("topic_"):
                idx = int(tag.split("_")[1]) - 1  # 0-based
                break

        if idx is not None and idx < len(TOPIC_DATA):
            record = TOPIC_DATA[idx]
            # Atomic answer must match document language (target_language)
            if q["target_language"] == "uk":
                atomic = record[3]  # UA atomic answer
                expected = record[2] + ". " + atomic + "."
            else:
                atomic = record[7]  # EN atomic answer
                expected = record[6] + ". " + atomic + "."
            facts = [atomic]
        elif qid.startswith("QDD"):
            # Derive atomic answer from primary doc in qrels
            prim_docs = primary_map.get(qid, [])
            if prim_docs:
                doc_id = prim_docs[0]
                # Map doc_id back to topic idx
                for ti in range(len(TOPIC_DATA)):
                    for lang_code, suffix in [("uk", "ua"), ("en", "en")]:
                        if did(ti, lang_code) == doc_id:
                            record = TOPIC_DATA[ti]
                            atomic = record[3] if suffix == "ua" else record[7]
                            facts = [atomic]
                            expected = atomic + "."
                            break
                    else:
                        continue
                    break
                else:
                    expected = f"Information about {q['query']} is available."
                    facts = [expected]
            else:
                expected = f"Information about {q['query']} is available."
                facts = [expected]
        else:
            expected = f"Information about {q['query']} is available."
            facts = [expected]

        citation_ids = sorted(primary_map.get(qid, []))
        answers.append(
            {
                "query_id": qid,
                "expected_answer": expected,
                "atomic_facts": facts[:3],
                "forbidden_facts": ["No contradictory information should be cited."],
                "citation_document_ids": citation_ids[:3],
                "no_answer": False,
            }
        )

    return answers


def compute_sha256(obj: Any) -> str:
    text = json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(text).hexdigest()


def main() -> None:
    out_root = Path(__file__).resolve().parent.parent / "dataset" / "v1"
    corpus_dir = out_root / "corpus"
    corpus_dir.mkdir(parents=True, exist_ok=True)

    # Clean old corpus
    for old in corpus_dir.glob("*.md"):
        old.unlink()

    corpus = generate_corpus(out_root)
    queries = generate_queries(corpus)
    qrels = generate_qrels(queries, corpus)
    answers = generate_expected_answers(queries, qrels, corpus)

    # ── Write files ───────────────────────────────────────────────────────
    queries_path = out_root / "queries.jsonl"
    with queries_path.open("w", encoding="utf-8") as f:
        for q in queries:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")

    qrels_path = out_root / "qrels.synthetic.jsonl"
    with qrels_path.open("w", encoding="utf-8") as f:
        for qrel in qrels:
            f.write(json.dumps(qrel, ensure_ascii=False) + "\n")

    answers_path = out_root / "expected-answers.jsonl"
    with answers_path.open("w", encoding="utf-8") as f:
        for a in answers:
            f.write(json.dumps(a, ensure_ascii=False) + "\n")

    # ── Corpus manifest ──────────────────────────────────────────────────
    corpus_hashes: list[dict[str, str]] = []
    for doc_id in sorted(corpus):
        fp = corpus_dir / doc_id
        content_hash = hashlib.sha256(fp.read_bytes()).hexdigest()
        # Determine language from doc_id suffix
        lang = "uk" if doc_id.endswith("-ua.md") else "en"
        # Extract title from content
        content_text = corpus[doc_id]
        title_match = re.search(r'^title: "(.+)"', content_text, re.MULTILINE)
        title = title_match.group(1) if title_match else doc_id
        corpus_hashes.append(
            {
                "document_id": doc_id,
                "file": f"corpus/{doc_id}",
                "sha256": content_hash,
                "type": "Resource",
                "title": title,
                "language": lang,
            }
        )
    corpus_hashes.sort(key=lambda x: x["document_id"])

    qrels_hash = compute_sha256(qrels)
    queries_hash = compute_sha256(queries)
    answers_hash = compute_sha256(answers)
    corpus_text = json.dumps(corpus_hashes, sort_keys=True)
    corpus_hash = hashlib.sha256(corpus_text.encode()).hexdigest()

    # Stratum counts (answerable only for base, total for manifest)
    strata_counts: dict[str, int] = dict.fromkeys(STRATA, 0)
    for q in queries:
        strata_counts[q["stratum"]] = strata_counts.get(q["stratum"], 0) + 1

    # Answerable per stratum
    ans_strata: dict[str, int] = dict.fromkeys(STRATA, 0)
    for q in queries:
        if q["query_class"] != "no_answer":
            ans_strata[q["stratum"]] = ans_strata.get(q["stratum"], 0) + 1

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "benchmark_version": BENCHMARK_VERSION,
        "generator": "generate_benchmark.py",
        "generator_seed": SEED,
        "generated_at": FIXED_TIMESTAMP,
        "corpus": {
            "count": len(corpus),
            "hash_sha256": corpus_hash,
            "files": corpus_hashes,
        },
        "queries": {
            "count": len(queries),
            "hash_sha256": queries_hash,
            "strata": strata_counts,
            "answerable_per_stratum": ans_strata,
        },
        "qrels": {
            "count": len(qrels),
            "hash_sha256": qrels_hash,
            "annotator": ANNOTATOR,
            "rubric_version": RUBRIC_VERSION,
            "annotation_type": "synthetic_deterministic",
        },
        "expected_answers": {
            "count": len(answers),
            "hash_sha256": answers_hash,
        },
        "scope_and_limitations": [
            "SYNTHETIC BENCHMARK — not human-annotated, not production evidence",
            "Dataset is topic-driven: 50 frozen topics with explicit bilingual content",
            "Relevance is rule-assigned by topic membership, not by human judges",
            "Corpus documents are generated from templates, not real vault data",
            "No private paths, secrets, or real note content included",
            "Suitable for regression testing and CI gates only",
            "Sparse qrels: only positive + distractor entries; missing pair = relevance 0",
        ],
    }

    manifest_path = out_root / "corpus-manifest.json"
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    # Annotation guidelines
    (out_root / "annotation-guidelines.md").write_text(
        "# POWER 3.1 Synthetic Benchmark — Annotation Guidelines\n\n"
        "## Scope\n"
        "This is a SYNTHETIC benchmark generated deterministically by code.\n"
        "All relevance judgements are topic-driven, not human-annotated.\n\n"
        "## Relevance Scale\n"
        "- 2 (High): Primary document — directly answers the query\n"
        "- 1 (Medium): Secondary related document\n"
        "- 0 (None): No relevant information\n\n"
        "## Utility Scale\n"
        "- +0.8: Primary document, directly resolves the query\n"
        "- +0.3: Secondary, partially relevant\n"
        "- 0.0: No utility (implicit — no qrels entry)\n"
        "- -0.5: Distractor (topically similar but contradictory)\n\n"
        "## Sparse Qrels\n"
        "Only positive and distractor entries are stored.\n"
        "Missing (query_id, document_id) pairs imply relevance=0.\n\n"
        "## No-Answer Queries\n"
        "No-answer queries have no qrels entries (all implicit zero).\n\n"
        "## Distractor Queries\n"
        "QDD* queries have a primary document AND a topically similar\n"
        "contradictory distractor document with negative utility.\n\n"
        "## Limitation\n"
        "This is NOT human annotation. Do not cite this as production evidence.\n",
        encoding="utf-8",
    )

    # CHANGELOG
    (out_root / "CHANGELOG.md").write_text(
        "# dataset/v1 Changelog\n\n"
        "## v2 — 2026-07-22\n\n"
        "- Complete methodological redesign (E1 review)\n"
        "- Topic-driven: 50 frozen topics with bilingual UA/EN content\n"
        "- Exactly 200 answerable queries (50/stratum), no random primary assignment\n"
        f"- {len(queries)} queries ({len([q for q in queries if q['query_class'] != 'no_answer'])} answerable, "
        f"{len([q for q in queries if q['query_class'] == 'no_answer'])} no-answer)\n"
        f"- {len(corpus)} corpus documents, {len(qrels)} sparse qrels entries\n"
        "- Atomic answers are literal substrings of primary documents\n"
        "- Generator: `generate_benchmark.py` (seed=42)\n"
        "- Scope: synthetic only — not human annotation\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
