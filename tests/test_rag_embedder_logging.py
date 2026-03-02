import importlib
import logging
import sys
import types

import pytest


def test_embed_query_logs_warning_when_reraising(monkeypatch, caplog):
    fake_genai = types.SimpleNamespace(
        configure=lambda **kwargs: None,
        embed_content=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    fake_google = types.ModuleType("google")
    fake_google.generativeai = fake_genai
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.generativeai", fake_genai)

    embedder_module = importlib.import_module("src.meta_mcp.rag.embedding.embedder")
    embedder_module = importlib.reload(embedder_module)

    adapter = embedder_module.GeminiEmbedderAdapter(api_key="test-key")
    with caplog.at_level(logging.WARNING, logger=embedder_module.__name__), pytest.raises(
        RuntimeError
    ):
        adapter.embed_query("hello")

    assert any(
        record.levelno == logging.WARNING and "Query embedding failed" in record.message
        for record in caplog.records
    )
