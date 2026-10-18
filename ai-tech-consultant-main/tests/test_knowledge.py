
import pytest

from task1_knowledge_brain import database, knowledge


@pytest.fixture
def temporary_database(tmp_path, monkeypatch):
    """Use a separate temporary database for each test."""
    db_file = tmp_path / "test.sqlite3"
    monkeypatch.setattr(database, "DB_PATH", str(db_file))
    database.initialize_database()
    return db_file


def test_initialize_database_creates_tables(temporary_database):
    connection = database.get_connection()

    try:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        table_names = {row["name"] for row in rows}

        assert "articles" in table_names
        assert "expert_feedback" in table_names
    finally:
        connection.close()


def test_save_and_find_article(temporary_database):
    url = "https://example.com/help/login"
    database.save_article(url, "Login Help", "Instructions for logging in.")

    article = database.find_article_by_url(url)

    assert article is not None
    assert article["title"] == "Login Help"
    assert "logging in" in article["content"]


def test_saving_same_url_updates_article(temporary_database):
    url = "https://example.com/help/login"

    database.save_article(url, "Old Title", "Old content")
    database.save_article(url, "Updated Title", "Updated content")

    article = database.find_article_by_url(url)

    assert article["title"] == "Updated Title"
    assert article["content"] == "Updated content"


def test_get_articles_returns_saved_articles(temporary_database):
    database.save_article(
        "https://example.com/help/a", "Article A", "Content A"
    )
    database.save_article(
        "https://example.com/help/b", "Article B", "Content B"
    )

    articles = database.get_articles()

    assert len(articles) == 2
    assert {article["title"] for article in articles} == {
        "Article A",
        "Article B",
    }


def test_find_missing_article_returns_none(temporary_database):
    article = database.find_article_by_url(
        "https://example.com/not-found"
    )

    assert article is None


def test_search_articles_blends_list_of_semantic_scores(monkeypatch):
    articles = [
        {
            "url": "https://example.test/first",
            "title": "Topic guide first",
            "content": "A guide about this topic.",
        },
        {
            "url": "https://example.test/second",
            "title": "Topic guide second",
            "content": "A guide about this topic.",
        },
    ]
    monkeypatch.setattr(knowledge, "get_articles", lambda: articles)
    monkeypatch.setattr(
        knowledge, "_semantic_scores", lambda _documents, _question: [1.0, 0.0]
    )

    results = knowledge.search_articles("topic")

    assert results
    assert results[0]["url"] == "https://example.test/first"


def test_save_expert_feedback(temporary_database):
    feedback_id = database.save_expert_feedback(
        "How do I change my domain?",
        "Open domain settings and update the domain.",
    )

    assert feedback_id > 0

    feedback = database.get_expert_feedback(status="pending")

    assert len(feedback) == 1
    assert feedback[0]["question"] == "How do I change my domain?"
    assert feedback[0]["expert_answer"] == (
        "Open domain settings and update the domain."
    )
