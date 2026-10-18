import json

import pytest
from fastapi.testclient import TestClient

from task1_knowledge_brain import database
from task1_knowledge_brain.main import app
from task1_knowledge_brain.multimodal.images import describe_image_from_url
from task3_meeting_scope import approval_store


def test_ingestion_run_status_persists_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "kb.sqlite3"))
    database.initialize_database()
    run_id = database.start_ingestion_run(4)
    database.update_ingestion_run(run_id, processed=2, saved=1, failed=1, current_url="https://support.brilliantdirectories.com/a")
    status = database.get_latest_ingestion_run()
    assert status["id"] == run_id
    assert status["status"] == "running"
    assert status["processed"] == 2
    assert status["current_url"].endswith("/a")


def test_scope_approval_is_persisted_and_retrievable(tmp_path, monkeypatch):
    monkeypatch.setattr(approval_store, "DB_PATH", str(tmp_path / "scope.sqlite3"))
    scope = {"project_summary": "Store refresh", "deliverables": ["Checkout"], "approval_required": True}
    decision_id = approval_store.save_scope_decision(scope, "approved", "reviewer-test")
    assert decision_id > 0
    assert approval_store.get_latest_approved_scope()["project_summary"] == "Store refresh"
    assert approval_store.list_scope_decisions()[0]["decision"] == "approved"


def test_needs_changes_is_audited_but_never_an_approved_baseline(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(approval_store, "DB_PATH", str(tmp_path / "scope.sqlite3"))
    scope = {
        "project_summary": "Bookstore",
        "deliverables": ["Catalog"],
        "approval_required": True,
    }

    first_id = approval_store.save_scope_decision(
        scope, "needs_changes", "reviewer-1"
    )
    assert first_id > 0
    assert approval_store.get_latest_approved_scope() is None
    first_history = approval_store.list_scope_decisions()
    assert first_history[0]["decision"] == "needs_changes"
    assert first_history[0]["created_at"]
    assert json.loads(
        _scope_json(approval_store, first_history[0]["id"])
    )["approval_required"] is True

    second_id = approval_store.save_scope_decision(
        scope, "approved", "reviewer-2"
    )
    assert second_id > first_id
    assert len(approval_store.list_scope_decisions()) == 2
    approved = approval_store.get_latest_approved_scope()
    assert approved["review_status"] == "approved"
    assert approved["approval_required"] is False


def _scope_json(store, decision_id):
    import sqlite3

    with sqlite3.connect(store.DB_PATH) as conn:
        return conn.execute(
            "SELECT scope_json FROM scope_approvals WHERE id = ?",
            (decision_id,),
        ).fetchone()[0]


@pytest.mark.parametrize("reviewer", ["", "  ", "reviewer\nspoof", "x" * 121])
def test_scope_review_rejects_invalid_reviewer_identifiers(
    tmp_path, monkeypatch, reviewer
):
    monkeypatch.setattr(approval_store, "DB_PATH", str(tmp_path / "scope.sqlite3"))
    with pytest.raises(ValueError, match="(?i)reviewer"):
        approval_store.save_scope_decision(
            {"project_summary": "Bookstore"}, "needs_changes", reviewer
        )


def test_task1_ask_api_preserves_actual_source_provenance(monkeypatch):
    from fastapi.testclient import TestClient

    article_url = "https://support.example.test/article"
    monkeypatch.setattr(
        "task1_knowledge_brain.main.ask_knowledge_brain",
        lambda *_args, **_kwargs: {
            "answer": "Supported answer.",
            "sources": [{
                "source_id": article_url,
                "title": "Real article",
                "url": article_url,
                "snippet": "Real indexed article excerpt.",
                "score": 0.88,
            }],
            "needs_human_help": False,
        },
    )
    with TestClient(app) as client:
        response = client.post(
            "/knowledge/ask",
            json={"question": "How does this feature work?"},
        )

    assert response.status_code == 200
    assert response.json()["sources"] == [{
        "source_id": article_url,
        "title": "Real article",
        "url": article_url,
        "snippet": "Real indexed article excerpt.",
        "score": 0.88,
    }]


def test_image_vision_rejects_non_allowlisted_host_before_network(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    assert describe_image_from_url("https://127.0.0.1/private.png") is None
    assert describe_image_from_url("http://support.brilliantdirectories.com/image.png") is None


def test_health_and_ingestion_status_routes_are_available(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "api.sqlite3"))
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/health/ready").json()["status"] == "ready"
        assert client.get("/ingestion/status").status_code == 200
        assert client.get("/openapi.json").status_code == 200
