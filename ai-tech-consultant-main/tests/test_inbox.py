
import pytest

from task2_inbox_agent import agent, learning


@pytest.fixture
def temporary_learning_database(tmp_path, monkeypatch):
    """Keep test data separate from the real project database."""
    test_db = tmp_path / "test_learning.sqlite3"
    monkeypatch.setattr(learning, "DB_PATH", str(test_db))
    learning.initialize_learning_database()
    return test_db


def test_classify_email_valid_json(monkeypatch):
    """Valid model output should produce a valid classification."""
    monkeypatch.setattr(
        agent,
        "generate_response",
        lambda *args, **kwargs: (
            '{"category": "Billing", '
            '"urgency": "High", '
            '"summary": "Customer was charged twice"}'
        ),
    )

    result = agent.classify_email(
        "Duplicate charge",
        "I was charged twice this month.",
    )

    assert result["category"] == "Billing"
    assert result["urgency"] == "High"
    assert "charged twice" in result["summary"]


def test_classify_email_invalid_json(monkeypatch):
    """Invalid model output should fall back safely."""
    monkeypatch.setattr(
        agent,
        "generate_response",
        lambda *args, **kwargs: "This is not valid JSON",
    )

    result = agent.classify_email("Help", "I need support.")

    assert result["category"] == "Other"
    assert result["urgency"] == "Medium"


def test_classify_email_invalid_category_is_rejected(monkeypatch):
    """Unknown categories should be replaced with Other."""
    monkeypatch.setattr(
        agent,
        "generate_response",
        lambda *args, **kwargs: (
            '{"category": "Unknown Category", '
            '"urgency": "High", "summary": "Test"}'
        ),
    )

    result = agent.classify_email("Test", "Test body")

    assert result["category"] == "Other"
    assert result["urgency"] == "High"


def test_save_email_review_detects_human_edit(
    temporary_learning_database,
):
    review_id = learning.save_email_review(
        subject="Login problem",
        category="Technical Support",
        urgency="Medium",
        original_draft="Please reset your password.",
        reviewed_draft="Please use the password reset link.",
    )

    reviews = learning.get_email_reviews()

    assert review_id > 0
    assert len(reviews) == 1
    assert reviews[0]["human_edited"] == 1
    assert reviews[0]["reviewed_draft"] == (
        "Please use the password reset link."
    )


def test_save_email_review_detects_unchanged_draft(
    temporary_learning_database,
):
    learning.save_email_review(
        subject="Billing question",
        category="Billing",
        urgency="Low",
        original_draft="Thank you for contacting support.",
        reviewed_draft=" Thank you for contacting support. ",
    )

    reviews = learning.get_email_reviews()

    assert len(reviews) == 1
    assert reviews[0]["human_edited"] == 0


def test_get_similar_review_examples_filters_by_category(
    temporary_learning_database,
):
    learning.save_email_review(
        subject="Billing question",
        category="Billing",
        urgency="Low",
        original_draft="Original billing reply",
        reviewed_draft="Reviewed billing reply",
    )
    learning.save_email_review(
        subject="Login problem",
        category="Technical Support",
        urgency="High",
        original_draft="Original technical reply",
        reviewed_draft="Reviewed technical reply",
    )

    examples = learning.get_similar_review_examples(
        category="Billing",
        limit=3,
    )

    assert len(examples) == 1
    assert examples[0]["category"] == "Billing"
    assert examples[0]["reviewed_draft"] == "Reviewed billing reply"


def test_get_email_reviews_respects_limit(
    temporary_learning_database,
):
    for number in range(3):
        learning.save_email_review(
            subject=f"Email {number}",
            category="Other",
            urgency="Low",
            original_draft="Original",
            reviewed_draft="Reviewed",
        )

    reviews = learning.get_email_reviews(limit=2)

    assert len(reviews) == 2
    assert reviews[0]["subject"] == "Email 2"
