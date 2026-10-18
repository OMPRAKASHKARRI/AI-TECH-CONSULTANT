
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
from sklearn.metrics.pairwise import cosine_similarity

from shared.llm import generate_response
from task1_knowledge_brain.database import (
    get_articles,
    get_connection,
    initialize_database,
)
from task1_knowledge_brain.crawler import sync_articles
import re
from functools import lru_cache


def _normalize_token(token: str) -> str:
    # Small deterministic suffix normalization improves common support-query
    # variants without requiring an additional NLP model.
    if len(token) > 5 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 6 and token.endswith("ing"):
        token = token[:-3]
    elif len(token) > 5 and token.endswith("ed"):
        token = token[:-2]
    if len(token) > 4 and token.endswith("s"):
        token = token[:-1]
    return token


def _tokenize(text: str) -> list[str]:
    stop_words = set(ENGLISH_STOP_WORDS)
    return [normalized for token in re.findall(r"[a-z0-9]+", text.lower())
            if (normalized := _normalize_token(token)) not in stop_words]


@lru_cache(maxsize=1)
def _embedding_model():
    """Load the optional local embedding model once per process."""
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("all-MiniLM-L6-v2")


def _semantic_scores(documents: list[str], question: str) -> list[float] | None:
    """Return normalized cosine similarities, or None if embeddings unavailable."""
    try:
        import numpy as np
        model = _embedding_model()
        vectors = model.encode(documents + [question], normalize_embeddings=True)
        scores = np.asarray(vectors[:-1]) @ np.asarray(vectors[-1])
        scores = np.clip(scores, 0.0, 1.0)
        maximum = float(scores.max()) if len(scores) else 0.0
        return (scores / maximum).tolist() if maximum > 0 else scores.tolist()
    except Exception:
        # Model weights may not be installed/downloadable in offline environments.
        return None


def search_articles(question: str, top_k: int = 3) -> list[dict]:
    """Hybrid lexical + embedding retrieval, with a TF-IDF-only fallback."""
    articles = [dict(article) for article in get_articles()]

    if not articles:
        return []

    documents = [
        f"{article['title']} {article['content']}"
        for article in articles
    ]

    vectorizer = TfidfVectorizer(tokenizer=_tokenize, token_pattern=None, ngram_range=(1, 2))
    matrix = vectorizer.fit_transform(documents + [question])

    lexical = cosine_similarity(matrix[-1], matrix[:-1]).flatten()
    lexical_max = float(lexical.max()) if len(lexical) else 0.0
    lexical_norm = lexical / lexical_max if lexical_max > 0 else lexical
    semantic = _semantic_scores(documents, question)
    if semantic is not None and len(semantic) == len(articles):
        import numpy as np
        semantic_scores = np.asarray(semantic, dtype=float)
        similarities = 0.65 * lexical_norm + 0.35 * semantic_scores
        # Do not return semantically similar but wholly unsupported matches.
        supported = (lexical > 0) | (semantic_scores >= 0.45)
    else:
        similarities = lexical
        supported = lexical > 0

    ranked_indices = similarities.argsort()[::-1][:top_k]
    results = []
    for index in ranked_indices:
        if supported[index] and similarities[index] > 0:
            article = articles[index]
            article["score"] = float(similarities[index])
            results.append(article)

    return results


def search_approved_feedback(
    question: str,
    top_k: int = 2,
) -> list[dict]:
    """Find relevant approved expert answers.

    Explicit test entries are excluded from retrieval.
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, question, expert_answer, created_at
            FROM expert_feedback
            WHERE status = 'approved'
              AND expert_answer NOT LIKE 'TEST ONLY:%'
            """
        ).fetchall()

    feedback = [dict(row) for row in rows]

    if not feedback:
        return []

    documents = [
        f"{item['question']} {item['expert_answer']}"
        for item in feedback
    ]

    vectorizer = TfidfVectorizer(tokenizer=_tokenize, token_pattern=None, ngram_range=(1, 2))
    matrix = vectorizer.fit_transform(documents + [question])

    similarities = cosine_similarity(
        matrix[-1],
        matrix[:-1],
    ).flatten()

    ranked_indices = similarities.argsort()[::-1][:top_k]

    results = []

    for index in ranked_indices:
        if similarities[index] > 0:
            item = feedback[index]
            item["score"] = float(similarities[index])
            results.append(item)

    return results



def ask_knowledge_brain(
    question: str,
    history: list | None = None,
) -> dict:
    """Answer questions using knowledge and conversation history."""
    history = history or []

    history_lines = []
    previous_user_questions = []

    for message in history[-8:]:
        if isinstance(message, dict):
            role = message.get("role", "")
            content = message.get("content", "")
        else:
            role = getattr(message, "role", "")
            content = getattr(message, "content", "")

        if not isinstance(content, str) or not content.strip():
            continue

        if role in {"user", "assistant"}:
            history_lines.append(f"{role.upper()}: {content.strip()}")

        if role == "user":
            previous_user_questions.append(content.strip())

    retrieval_query = " ".join(
        previous_user_questions[-2:] + [question]
    )

    articles = search_articles(retrieval_query, top_k=1)
    expert_answers = search_approved_feedback(retrieval_query)

    if not articles and not expert_answers:
        return {
            "answer": (
                "I couldn't find relevant information in the indexed "
                "help articles or approved expert answers. "
                "Please ask a human expert for help."
            ),
            "sources": [],
            "needs_human_help": True,
        }

    context_parts = []

    for article in articles:
        context_parts.append(
            "Source type: Official help-center article\n"
            f"Title: {article['title']}\n"
            f"URL: {article['url']}\n"
            f"Content: {article['content'][:1500]}"
        )

    for item in expert_answers:
        context_parts.append(
            "Source type: Approved expert answer\n"
            f"Question: {item['question']}\n"
            f"Answer: {item['expert_answer']}"
        )

    context = "\n\n".join(context_parts)
    conversation = "\n".join(history_lines) or "(No previous messages)"

    prompt = f"""
Answer the latest user question using the retrieved context.

Rules:
- Use conversation history to understand follow-up questions.
- Treat history as context, not proof of product facts.
- Do not invent product features, instructions, or facts.
- If the retrieved context cannot answer the question, say so.
- Recommend human review when evidence is insufficient.
- Cite official articles using their exact URLs.
- Never invent citations for expert answers.
- Include only sources that support your answer.

CONVERSATION HISTORY:
{conversation}

RETRIEVED CONTEXT:
{context}

LATEST USER QUESTION:
{question}
"""

    answer = generate_response(
        prompt,
        system_prompt=(
            "You are a careful product-support assistant. "
            "Use the supplied evidence for factual claims, understand "
            "conversation context, and never invent citations."
        ),
    )

    lowered_answer = answer.lower()

    uncertainty_phrases = (
        "i don't know",
        "i do not know",
        "couldn't find relevant information",
        "cannot answer from the provided context",
        "not enough information",
        "insufficient information",
        "unable to determine",
    )

    needs_human_help = any(
        phrase in lowered_answer
        for phrase in uncertainty_phrases
    )

    sources = [
        {
            "source_id": article["url"],
            "title": article["title"],
            "url": article["url"],
            "snippet": article["content"][:500],
            "score": float(article.get("score", 0.0)),
        }
        for article in articles
        if article.get("score", 0) > 0
    ]

    return {
        "answer": answer,
        "sources": sources,
        "needs_human_help": needs_human_help,
    }

def initialize_knowledge_brain() -> None:
    """Initialize the database tables."""
    initialize_database()


def sync_knowledge_brain(
    max_pages: int = 20,
    delay_seconds: float = 1.0,
) -> dict:
    """Synchronize help-center articles into the database."""
    initialize_database()

    return sync_articles(
        max_pages=max_pages,
        delay_seconds=delay_seconds,
    )
