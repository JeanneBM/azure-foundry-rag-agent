"""Validate RAG smoke verdicts using SDK substitutes; no Azure calls."""

import importlib.util
import json
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SEARCH = "https://example.search.windows.net/indexes/demo-docs/docs"
RETURNS_URL = f"{SEARCH}/returns?$select=title%2Ccontent%2Cid&api-version=2026-08-01-preview"
SUPPORT_URL = f"{SEARCH}/support?$select=title%2Ccontent%2Cid&api-version=2026-08-01-preview"


def load_adapter(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "rag_smoke_adapter", ROOT / "scripts" / "cloud_validation.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_expected_returns_document_matches_lab_documents(monkeypatch):
    module = load_adapter(monkeypatch)
    documents = json.loads((ROOT / "examples/lab-documents.json").read_text(encoding="utf-8"))
    returns = next(doc for doc in documents if doc["id"] == module.RETURNS_DOCUMENT_ID)
    assert returns["title"] == module.RETURNS_DOCUMENT_TITLE
    assert "30 days" in returns["content"]


@pytest.mark.parametrize(
    "sources,expected",
    [
        (({"ref_id": "a", "url": RETURNS_URL},), True),
        (({"ref_id": "0", "title": "Demo return policy"},), True),
        (({"ref_id": "a", "url": SUPPORT_URL}, {"ref_id": "b", "url": RETURNS_URL}), True),
        (({"ref_id": "a", "url": SUPPORT_URL},), False),
        (({"ref_id": "a", "url": f"{SEARCH}/returns-archive"},), False),
        (({"ref_id": "0"},), False),
        ((), False),
    ],
)
def test_cites_document_matches_url_key_or_title(monkeypatch, sources, expected):
    module = load_adapter(monkeypatch)
    assert module.cites_document(sources, "returns", "Demo return policy") is expected


@pytest.mark.parametrize(
    "problem,expected",
    [
        (None, "PASS"),
        ("wrong_answer", "FAIL"),
        ("unknown_not_refused", "FAIL"),
        ("missing_citations", "FAIL"),
        ("wrong_source", "FAIL"),
        ("retrieval_failed", "INCONCLUSIVE"),
    ],
)
def test_rag_smoke_checks_known_answer_citations_and_abstention(
    tmp_path, monkeypatch, problem, expected
):
    module = load_adapter(monkeypatch)
    adapter = module.CloudLab(tmp_path, "rag", "rg-demo")
    import rag_foundry.clients
    import rag_foundry.config
    import rag_foundry.deployment
    import rag_foundry.session
    from rag_foundry.grounding import GroundingError

    settings = SimpleNamespace(agent_name="demo")
    project = SimpleNamespace(agents=SimpleNamespace(get_version=lambda *args: None))
    monkeypatch.setattr(rag_foundry.config.Settings, "from_env", lambda: settings)
    monkeypatch.setattr(rag_foundry.deployment, "resolve_version", lambda cfg: "1")
    monkeypatch.setattr(rag_foundry.clients, "project_client", lambda cfg: nullcontext(project))
    monkeypatch.setattr(
        rag_foundry.clients, "responses_client", lambda *args: nullcontext(object())
    )

    class Session:
        def __init__(self, *args):
            pass

        def ask(self, question):
            if problem == "retrieval_failed":
                raise GroundingError("retrieval_failed")
            known = question.startswith("What is the product")
            if problem == "missing_citations":
                sources = ()
            elif problem == "wrong_source":
                sources = ({"ref_id": "a", "url": SUPPORT_URL},)
            else:
                sources = ({"ref_id": "a", "url": RETURNS_URL},)
            return SimpleNamespace(
                text="90 days" if problem == "wrong_answer" else "30 days",
                sources=sources,
                unknown=not known and problem != "unknown_not_refused",
            )

    monkeypatch.setattr(rag_foundry.session, "RagSession", Session)
    assert adapter.rag_smoke(tmp_path, {}).verdict == expected
