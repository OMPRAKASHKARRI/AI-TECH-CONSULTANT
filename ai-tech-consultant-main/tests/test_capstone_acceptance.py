"""Offline acceptance/evaluation cases. These validate deterministic contracts,
not the quality of live model-generated answers; see EVALS.md for limits.
"""
import json
import pytest

from task1_knowledge_brain import knowledge
from task2_inbox_agent import agent, learning
from task3_meeting_scope.scope_diff import compare_scopes


TASK1_CASES = [
    ("login password reset", "Login and Password Reset"),
    ("billing invoice charge", "Billing and Invoices"),
    ("domain verification", "Domain Verification"),
    ("website homepage layout", "Website Layout"),
    ("notification emails", "Email Notifications"),
    ("membership renewal", "Membership Renewal"),
    ("payment setup", "Payment Setup"),
    ("account profile", "Account Profile"),
    ("search settings", "Search Settings"),
    ("privacy settings", "Privacy Settings"),
    ("cancel subscription", "Subscription Cancellation"),
    ("refund request", "Refund Policy"),
    ("user roles permissions", "Roles and Permissions"),
    ("upload images", "Image Uploads"),
    ("custom fields", "Custom Fields"),
    ("SEO metadata", "SEO Metadata"),
    ("site backups", "Site Backups"),
    ("analytics reports", "Analytics Reports"),
    ("API integration", "API Integration"),
    ("troubleshoot error", "Troubleshooting Errors"),
]

@pytest.mark.parametrize("query,title", TASK1_CASES)
def test_task1_retrieval_returns_relevant_source(monkeypatch, query, title):
    docs = [{"url": f"https://example.test/{i}", "title": t, "content": f"Official guide about {t.lower()} and how to configure it."} for i, (_, t) in enumerate(TASK1_CASES)]
    monkeypatch.setattr(knowledge, "get_articles", lambda: docs)
    results = knowledge.search_articles(query, top_k=3)
    assert results
    assert all("url" in row and "title" in row for row in results)
    assert any(row["title"] == title for row in results), f"Expected relevant title {title!r} for {query!r}"

TASK2_CASES = [
    ("charged twice", "Billing", "High"), ("refund invoice", "Billing", "Medium"),
    ("payment failed", "Billing", "Medium"), ("cannot login", "Technical Support", "Medium"),
    ("password reset error", "Technical Support", "Medium"), ("site is down urgent", "Bug Report", "High"),
    ("feature request dashboard", "Feature Request", "Low"), ("new account setup", "Account Setup", "Low"),
    ("broken page error", "Bug Report", "Medium"), ("change billing address", "Billing", "Medium"),
    ("urgent lost access", "Technical Support", "High"), ("how to configure domain", "Technical Support", "Medium"),
    ("please add export feature", "Feature Request", "Low"), ("unexpected invoice charge", "Billing", "Medium"),
    ("app crashes on save", "Bug Report", "Medium"), ("help me set up account", "Account Setup", "Medium"),
    ("need assistance", "Other", "Low"), ("login issue blocks work", "Technical Support", "High"),
    ("billing receipt", "Billing", "Low"), ("report an error", "Bug Report", "Medium"),
]

@pytest.mark.parametrize("body,category,urgency", TASK2_CASES)
def test_task2_classifier_structured_output_contract(monkeypatch, body, category, urgency):
    monkeypatch.setattr(agent, "generate_response", lambda *a, **k: json.dumps({"category": category, "urgency": urgency, "summary": "Test case summary"}))
    result = agent.classify_email("Evaluation case", body)
    assert result["category"] == category
    assert result["urgency"] == urgency
    assert result["summary"]

TASK3_CASES = [
    ("Login", "Cart"), ("Billing", "Refunds"), ("Search", "Filters"),
    ("Reports", "Exports"), ("Notifications", "SMS"), ("Dashboard", "Analytics"),
    ("Roles", "Permissions"), ("Profile", "Avatar"), ("Domain", "DNS"),
    ("Catalog", "Wishlist"), ("Payments", "Coupons"), ("Orders", "Returns"),
    ("Membership", "Renewal"), ("Images", "Video"), ("SEO", "Sitemap"),
    ("Backups", "Restore"), ("API", "Webhooks"), ("Search", "Autocomplete"),
    ("Theme", "Dark mode"), ("Support", "Live chat"),
]

@pytest.mark.parametrize("old_item,new_item", TASK3_CASES)
def test_task3_scope_change_requires_approval(old_item, new_item):
    previous = {"meeting_analysis": {"requirements": [old_item]}, "deliverables": [], "tasks": [{"estimate_hours": 4}]}
    updated = {"meeting_analysis": {"requirements": [new_item]}, "deliverables": [], "tasks": [{"estimate_hours": 6}]}
    result = compare_scopes(previous, updated)
    assert result["possible_scope_change"] is True
    assert result["approval_required"] is True
    assert result["estimate_change_hours"] == 2


def test_autonomy_requires_twenty_consecutive_unedited_approvals(tmp_path, monkeypatch):
    monkeypatch.setattr(learning, "DB_PATH", str(tmp_path / "learning.sqlite3"))
    learning.initialize_learning_database()
    for i in range(19):
        learning.save_email_review("s", "Billing", "Low", "same", "same", "approved")
    status = {r["category"]: r for r in learning.get_autonomy_status()}["Billing"]
    assert status["consecutive_unedited_approvals"] == 19
    assert status["eligible"] == 0
    learning.save_email_review("s", "Billing", "Low", "same", "same", "approved")
    status = {r["category"]: r for r in learning.get_autonomy_status()}["Billing"]
    assert status["consecutive_unedited_approvals"] == 20
    assert status["eligible"] == 1
    learning.save_email_review("s", "Billing", "Low", "original", "edited", "approved")
    status = {r["category"]: r for r in learning.get_autonomy_status()}["Billing"]
    assert status["consecutive_unedited_approvals"] == 0
    assert status["eligible"] == 0
