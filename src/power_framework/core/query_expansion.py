from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from typing import ClassVar

from .utils import run_opencode_cli

logger = logging.getLogger(__name__)

OPENROUTER_MODELS = [
    "openrouter/google/gemini-2.5-flash",
    "openrouter/qwen/qwen3.5-flash-02-23",
]


class QueryExpander:
    SYNONYM_MAP: ClassVar[dict[str, list[str]]] = {
        "deploy": ["deployment", "розгортання"],
        "deployment": ["deploy", "розгортання"],
        "docker": ["container", "контейнер"],
        "container": ["docker", "контейнер"],
        "контейнер": ["docker", "container"],
        "backup": ["бекап", "резервне копіювання"],
        "бекап": ["backup", "резервне копіювання"],
        "резервне копіювання": ["backup", "бекап"],
        "search": ["пошук"],
        "пошук": ["search"],
        "query": ["запит"],
        "запит": ["query"],
        "note": ["нотатка", "замітка"],
        "нотатка": ["note", "замітка"],
        "замітка": ["note", "нотатка"],
        "index": ["індекс", "індексація"],
        "індекс": ["index", "індексація"],
        "індексація": ["index", "індекс"],
        "archive": ["архів"],
        "архів": ["archive"],
        "config": ["configuration", "конфігурація", "налаштування"],
        "configuration": ["config", "конфігурація", "налаштування"],
        "налаштування": ["config", "configuration", "конфігурація"],
        "конфігурація": ["config", "configuration", "налаштування"],
        "tag": ["тег", "мітка"],
        "тег": ["tag", "мітка"],
        "мітка": ["tag", "тег"],
        "network": ["мережа"],
        "мережа": ["network"],
        "security": ["безпека"],
        "безпека": ["security"],
        "test": ["тест"],
        "тест": ["test"],
        "error": ["помилка", "помилка"],
        "помилка": ["error"],
    }

    def __init__(self, use_llm: bool = False, api_key: str | None = None) -> None:
        self.use_llm = use_llm
        if api_key is not None:
            self.api_key = api_key
        else:
            self.api_key = os.environ.get("POWER_LLM_API_KEY") or os.environ.get(
                "OPENROUTER_API_KEY", ""
            )
        self.api_base = os.environ.get("POWER_LLM_API_BASE", "https://openrouter.ai/api/v1").rstrip(
            "/"
        )
        self.model = os.environ.get("POWER_LLM_MODEL", OPENROUTER_MODELS[0])

    def expand(self, query: str) -> list[str]:
        if not query or not query.strip():
            return []

        variants: list[str] = [query]
        variants.extend(self._synonym_expand(query))

        if self.use_llm and (self.api_key or self.api_base == "opencode"):
            try:
                llm_variants = self._llm_expand(query)
                variants.extend(llm_variants)
            except Exception:
                logger.warning("LLM query expansion failed, falling back to local synonyms")

        return self._deduplicate(variants)

    def _synonym_expand(self, query: str) -> list[str]:
        tokens = re.findall(r"[a-z0-9а-яєіїґ']+", query.lower())  # noqa: RUF001
        expanded: list[str] = []
        for token in tokens:
            if token in self.SYNONYM_MAP:
                for syn in self.SYNONYM_MAP[token]:
                    variant = re.sub(
                        r"\b" + re.escape(token) + r"\b",
                        syn,
                        query,
                        count=1,
                        flags=re.IGNORECASE,
                    )
                    if variant != query:
                        expanded.append(variant)
        return expanded

    def _llm_expand(self, query: str) -> list[str]:
        prompt = (
            f"Generate 2 alternative search queries for a knowledge base. "
            f"Original query: '{query}'. "
            f"Return only a JSON array of 2 strings, no other text."
        )

        if self.api_base == "opencode":
            res_text = run_opencode_cli(prompt)
            if not res_text:
                return []
            try:
                cleaned = res_text.strip()
                if cleaned.startswith("```"):
                    cleaned = cleaned.split("```")[1]
                    if cleaned.startswith("json"):
                        cleaned = cleaned[4:]
                alternatives = json.loads(cleaned.strip())
                if isinstance(alternatives, list):
                    return [str(a) for a in alternatives if a]
            except json.JSONDecodeError as e:
                logger.warning("Failed to parse local opencode JSON: %s", e)
            return []

        if not self.api_key:
            return []

        payload = json.dumps(
            {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 150,
                "temperature": 0.7,
            }
        ).encode("utf-8")

        req = urllib.request.Request(  # noqa: S310
            f"{self.api_base}/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
                body = json.loads(resp.read().decode("utf-8"))
                content = body["choices"][0]["message"]["content"]
                alternatives = json.loads(content)
                if isinstance(alternatives, list):
                    return [str(a) for a in alternatives if a]
        except (urllib.error.URLError, json.JSONDecodeError, KeyError, IndexError) as e:
            logger.warning("LLM expansion network error: %s", e)

        return []

    @staticmethod
    def _deduplicate(items: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in items:
            key = item.strip().lower()
            if key and key not in seen:
                seen.add(key)
                result.append(item.strip())
        return result
