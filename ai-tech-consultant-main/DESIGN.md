# Design Document — AI Tech Consultant

## 1. Goal and boundaries

This repository implements three connected workflows for a generic software/service business. Task 1 owns knowledge ingestion and retrieval. Task 2 and Task 3 are clients of the Task 1 HTTP API; neither is allowed to copy the retrieval pipeline. The prototype emphasizes grounded output, human review, auditability, and honest offline behavior over unapproved automation.

## 2. Architecture

```text
Help-center sitemap
        |
        v
Task 1 crawler -> SQLite articles + ingestion checkpoints
        |                         |
        v                         v
 screenshot alt/captions     TF-IDF retrieval + token normalization
 optional Claude vision             |
                                    v
                           FastAPI /knowledge/ask
                             /             \
                            v               v
                 Task 2 Inbox Agent   Task 3 Meeting Scope
                 classify/draft      extract/estimate/diff
                      |                    |
                 human review         persistent decision log
                      |                    |
                 feedback/streak      approved baseline review
```

**Knowledge Brain:** `crawler.py` reads the Brilliant Directories Solution Center sitemap, expands a sitemap index, fetches article HTML with a descriptive user agent, removes navigation/boilerplate, and stores article title, text, image alt text/captions, and image URLs. When `ANTHROPIC_API_KEY` is available and Anthropic is selected, up to two images per article are offered to Claude vision for support-relevant description. Images without supported content types, oversized downloads, or vision failures do not stop article ingestion. SQLite upserts each saved article. Ingestion runs store progress and the last processed URL so a restarted run can resume from the last checkpoint. A daily APScheduler job is registered by the API process.

**Retrieval and answering:** article content is indexed per query with TF-IDF and lightweight suffix normalization. Approved expert answers are also searchable. The API sends retrieved excerpts, conversation history, and citation rules to the configured LLM adapter. If no evidence is found, the service abstains and requests human help. Real article citations include the URL-backed source ID, title, excerpt, and retrieval score. Retrieval is a lexical baseline, not a production-grade vector database; this limitation is explicit.

**LLM adapter:** `shared/llm.py` defaults to Groq and `openai/gpt-oss-120b`; provider, model, token cap, and credentials are environment-configurable. Anthropic and Ollama remain explicit alternatives; offline mode supports deterministic non-scope smoke tests but never fabricates a scope when a provider is unavailable. Provider failures are mapped to sanitized configuration, authentication, rate-limit, temporary, and service errors.

**Inbox Agent:** the Python UI classifies a customer email, requests knowledge via `POST /knowledge/ask`, and drafts a reply using the returned evidence. API failures and missing evidence trigger human review. Drafts are not sent. Human decisions are recorded in SQLite. Per-category streaks count only consecutive approvals whose draft text was not edited; any edit, rejection, escalation, or other non-approval resets the streak. Twenty approvals set an eligibility flag only; no sending capability is wired to that flag.

**Meeting to Scope:** the agent retrieves product knowledge via the same HTTP endpoint, validates structured draft scopes, normalizes per-task low/likely/high estimates and their totals, and requires human approval. If Task 1 has no indexed evidence, the source list stays empty and human verification is flagged; citations include only actual Task 1 results. `scope_diff.py` compares requirements and deliverables against the latest approved baseline; drafts and `needs_changes` decisions never become baselines. Reviewer decisions are appended to the persistent history with a serialized scope snapshot.

## 3. Data and interfaces

SQLite is used for articles, expert feedback, ingestion runs, email reviews, autonomy streaks, and scope approval records. The `DATABASE_PATH` environment variable controls the shared project database. SQL statements use parameters for user-provided values. API clients use explicit timeouts and treat unavailable knowledge as an escalation rather than inventing product instructions.

Core endpoints: `POST /knowledge/ask` (`/query` alias), `POST /knowledge/sync` (`/ingestion/run` alias), `GET /ingestion/status`, `GET /health`, `GET /health/ready`, and feedback/escalation list-create-resolve routes. FastAPI exposes an OpenAPI schema at `/docs`.

## 4. Reliability and safety

- Ingestion saves each article separately and records checkpoints; retrying an article is safe because the URL is the primary key.
- API consumers have finite request timeouts and return human-review flags on failure.
- Email content is treated as untrusted prompt input. Historical edits are style examples, not factual sources.
- No email-send integration exists; no auto-send action is taken after reaching an approval streak.
- Generated scope estimates and proposals are drafts. Scope-change detection forces review.
- The multimodal helper accepts only common image MIME types and limits downloads to 5 MiB. It is an optional enrichment step; alt text/captions are retained as a fallback.
- Secrets belong in local `.env` and must not be committed. `.env.example` contains placeholders only.

## 5. Trade-offs and limitations

Hybrid retrieval combines TF-IDF with optional SentenceTransformer embeddings (`all-MiniLM-L6-v2`) when model weights are installed; it falls back to TF-IDF in offline environments. This is not a persistent vector database and it can miss paraphrases or require a first-run model download. The current article extractor is generic and needs validation against the actual help-center DOM. The scheduler is in-process, so production deployments should use a dedicated worker/cron and distributed locking. Feedback and approval records are local SQLite records without user authentication; this is a demonstration application, not a multi-tenant production system. The optional vision path and live Claude calls require API credentials and network access. Model comparisons must be run in an environment with credentials and their output retained; no live results are claimed by this repository's offline tests.

## 6. Running and validating

Use `python run_all.py` to start the API and three Streamlit apps. Run `python -m pytest -q` for offline deterministic tests. `evaluations/` contains 20 cases per task, and `scripts/evaluate_models.py` can run the same cases against two configurable Groq or Anthropic model IDs and records structured-output pass rate, JSON validity, latency, token usage, and cost when per-model price variables are configured. The harness makes live provider calls only when explicitly run and does not replace end-to-end app tests or human review.
