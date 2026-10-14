"""Validate RAG smoke verdicts using SDK substitutes; no Azure calls."""

import importlib.util
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize(
    "problem,expected",
    [
        (None, "PASS"),
        ("wrong_answer", "FAIL"),
        ("unknown_not_refused", "FAIL"),
        ("missing_citations", "FAIL"),
        ("retrieval_failed", "INCONCLUSIVE"),
    ],
)
def test_rag_smoke_checks_known_answer_citations_and_abstention(
    tmp_path, monkeypatch, problem, expected
):
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location(
        "rag_smoke_adapter", scripts / "cloud_validation.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    adapter = module.CloudLab(tmp_path, "rag", "rg-demo", "rag")
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
            return SimpleNamespace(
                text="90 days" if problem == "wrong_answer" else "30 days",
                sources=() if problem == "missing_citations" else ({"ref_id": "0"},),
                unknown=not known and problem != "unknown_not_refused",
            )

    monkeypatch.setattr(rag_foundry.session, "RagSession", Session)
    assert adapter.rag_smoke(tmp_path, {}).verdict == expected
