"""Tests for the QueryExpander class."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from power_framework.core.query_expansion import QueryExpander


class TestQueryExpander:
    """Tests for QueryExpander synonym expansion."""

    def test_synonym_expand_simple(self):
        expander = QueryExpander()
        variants = expander.expand("deploy")
        assert "deploy" in variants
        assert "deployment" in variants
        assert "розгортання" in variants

    def test_synonym_expand_docker_to_container(self):
        expander = QueryExpander()
        variants = expander.expand("docker")
        assert "docker" in variants
        assert "container" in variants
        assert "контейнер" in variants

    def test_synonym_expand_uk_to_en(self):
        expander = QueryExpander()
        variants = expander.expand("контейнер")
        assert "контейнер" in variants
        assert "docker" in variants
        assert "container" in variants

    def test_synonym_expand_backup(self):
        expander = QueryExpander()
        variants = expander.expand("backup")
        assert "backup" in variants
        assert "бекап" in variants
        assert "резервне копіювання" in variants

    def test_empty_query(self):
        expander = QueryExpander()
        assert expander.expand("") == []
        assert expander.expand("   ") == []

    def test_no_synonyms(self):
        expander = QueryExpander()
        variants = expander.expand("foobarqwerty")
        assert variants == ["foobarqwerty"]

    def test_deduplication(self):
        expander = QueryExpander()
        variants = expander.expand("test")
        # "test" has only one synonym: "тест" (and "test" itself)
        # So we should have unique variants only
        assert len(variants) == len(set(v.strip().lower() for v in variants))

    def test_multi_word_query_partial_synonyms(self):
        expander = QueryExpander()
        variants = expander.expand("docker deployment")
        assert "docker deployment" in variants
        assert any("container" in v for v in variants)
        assert any("розгортання" in v for v in variants)

    def test_case_preserved_in_variants(self):
        expander = QueryExpander()
        variants = expander.expand("Docker Config")
        assert "Docker Config" in variants
        # Case-insensitive matching for synonyms
        assert any("container" in v.lower() for v in variants)


class TestQueryExpanderLLM:
    """Tests for QueryExpander LLM expansion mode."""

    def test_llm_skipped_when_no_api_key(self):
        expander = QueryExpander(use_llm=True, api_key="")
        with patch("urllib.request.urlopen") as mock_urlopen:
            variants = expander.expand("docker")
            mock_urlopen.assert_not_called()
        assert "docker" in variants
        assert "container" in variants

    def test_llm_graceful_on_network_error(self):
        expander = QueryExpander(use_llm=True, api_key="sk-test-key")
        with patch(
            "urllib.request.urlopen", side_effect=TimeoutError("network timeout")
        ):
            variants = expander.expand("docker")
        assert "docker" in variants

    def test_llm_graceful_on_bad_json(self):
        expander = QueryExpander(use_llm=True, api_key="sk-test-key")
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"not json"
        mock_resp.__enter__.return_value = mock_resp
        with patch("urllib.request.urlopen", return_value=mock_resp):
            variants = expander.expand("docker")
        assert "docker" in variants

    def test_llm_adds_variants_on_success(self):
        expander = QueryExpander(use_llm=True, api_key="sk-test-key")
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"choices":[{"message":{"content":"[\\"docker orchestration\\",\\"container management\\"]"}}]}'
        mock_resp.__enter__.return_value = mock_resp
        with patch("urllib.request.urlopen", return_value=mock_resp):
            variants = expander.expand("docker")
        assert "docker" in variants
        assert "docker orchestration" in variants
        assert "container management" in variants

    def test_llm_uses_env_var_when_no_key_arg(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-env-key")
        expander = QueryExpander(use_llm=True)
        assert expander.api_key == "sk-env-key"


class TestQueryExpanderInit:
    """Tests for QueryExpander initialization."""

    def test_default_no_llm(self):
        expander = QueryExpander()
        assert not expander.use_llm
        assert expander.api_key == ""

    def test_explicit_llm_and_key(self):
        expander = QueryExpander(use_llm=True, api_key="sk-test")
        assert expander.use_llm
        assert expander.api_key == "sk-test"

    def test_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-env-test")
        expander = QueryExpander()
        assert expander.api_key == "sk-env-test"
