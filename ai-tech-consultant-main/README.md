# AI Tech Consultant

A three-workflow support operations prototype for the BusinessLabs capstone. It combines a product knowledge service, an AI-assisted inbox workflow, and a meeting-to-scope workflow in a Python application.

> **Project status:** This is a local capstone prototype, not a production-ready service. Live model calls and knowledge-base ingestion require network access and appropriate credentials.

## Workflows

| Workflow | Purpose | Interface |
| --- | --- | --- |
| **Knowledge Brain** | Syncs and searches product-support content, answers questions using retrieved evidence, and supports human escalation and feedback. | FastAPI and Streamlit |
| **Inbox Agent** | Assists with support-message classification, prioritization, and reply drafting. | Streamlit |
| **Meeting to Scope** | Turns a meeting transcript into a structured scope proposal with deliverables, implementation tasks, effort ranges, assumptions, risks, dependencies, and open questions. | Streamlit |

Tasks 2 and 3 access Task 1 through its HTTP API rather than importing its retrieval implementation. Task 3 preserves product knowledge citations when the Knowledge Brain returns evidence.

## Architecture

- **Python 3.11+** (tested with Python 3.13)
- **FastAPI** and **Uvicorn** for the Knowledge Brain API
- **Streamlit** for the three workflow interfaces
- **SQLite** for local application data
- **Groq** as the default language-model provider; Anthropic and Ollama are optional provider choices
- **scikit-learn** for knowledge retrieval

The default Groq model is `openai/gpt-oss-120b`. Provider configuration is handled through environment variables; credentials should never be committed to source control.

## Getting started

### Windows PowerShell

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and set `GROQ_API_KEY` to use live Groq generation. Then start the application:

```powershell
python run_all.py
```

### macOS or Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Set `GROQ_API_KEY` in `.env`, then run:

```bash
python run_all.py
```

`run_all.py` starts the API and all three Streamlit applications. Stop the services with **Ctrl+C**.

## Local application URLs

| Service | URL |
| --- | --- |
| Knowledge Brain API documentation | <http://127.0.0.1:8000/docs> |
| Knowledge Brain interface | <http://127.0.0.1:8501> |
| Inbox Agent interface | <http://127.0.0.1:8502> |
| Meeting to Scope interface | <http://127.0.0.1:8503> |

To run only the Knowledge Brain API:

```powershell
python -m uvicorn task1_knowledge_brain.main:app --reload
```

## Configuration

The `.env.example` file documents the available settings:

| Variable | Purpose |
| --- | --- |
| `LLM_PROVIDER` | Provider selection: `groq` (default), `anthropic`, `ollama`, or `offline` |
| `GROQ_API_KEY` | Credential for live Groq requests |
| `GROQ_MODEL` | Groq model identifier; defaults to `openai/gpt-oss-120b` |
| `ANTHROPIC_API_KEY` | Credential when Anthropic is selected |
| `ANTHROPIC_MODEL` | Anthropic model identifier |
| `OLLAMA_MODEL` | Model name when using a local Ollama server |
| `LLM_MAX_TOKENS` | Maximum generated tokens |
| `DATABASE_PATH` | SQLite database path; defaults to `data/jd4.sqlite3` |
| `KNOWLEDGE_API_URL` | Knowledge Brain API base URL; defaults to `http://127.0.0.1:8000` |

Do not commit `.env` or share provider credentials. Offline mode is useful for local development and smoke checks; it is not evidence of live model quality.

## Knowledge-base setup

Start the application, then trigger a knowledge sync from the Knowledge Brain interface or API. The first automatic refresh is scheduled after startup; it does not run immediately. Until content is indexed, the Knowledge Brain may abstain and return no product sources. Task 3 reports that state rather than inventing citations.

## Scope review and safety

- Generated scopes remain **drafts** until a human reviewer explicitly records a decision.
- Low, likely, and high effort totals are calculated from task-level estimates. They are planning ranges, not commitments.
- An unavailable model or invalid generated response is surfaced as an error; the application does not substitute fabricated scope content.
- Email messages are never sent by this application. Approval-streak tracking does not enable sending.
- Screenshot analysis uses Anthropic vision only when Anthropic is explicitly selected and configured.
- Live model requests and knowledge-base crawling require network access and may consume provider quota.

## API overview

The Knowledge Brain exposes these primary endpoints:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Basic service health |
| `GET` | `/health/ready` | Readiness check |
| `POST` | `/knowledge/ask` | Ask a product-support question |
| `POST` | `/knowledge/sync` | Start knowledge ingestion |
| `GET` | `/ingestion/status` | Check ingestion status |
| `POST` | `/knowledge/feedback` | Submit feedback or escalation |
| `GET` | `/knowledge/feedback` | List feedback or escalations |
| `PATCH` | `/knowledge/feedback/{id}` | Update a feedback or escalation record |

Interactive request and response documentation is available at <http://127.0.0.1:8000/docs> while the API is running. Compatibility aliases are also available for several endpoints.

## Development and tests

Run the test suite and Python syntax check from the project root:

```powershell
python -m pytest -q
python -m compileall -q shared task1_knowledge_brain task2_inbox_agent task3_meeting_scope tests scripts
```

Unit tests mock provider and HTTP calls; they do not require paid model requests or a live crawl. An optional Groq integration test is available for environments configured to make a real request:

```powershell
$env:RUN_GROQ_INTEGRATION = "1"
python -m pytest tests\test_groq_integration.py -q
```

The model-evaluation script also makes live provider calls when explicitly run:

```powershell
python scripts/evaluate_models.py
```

Review its provider/model configuration before running because live evaluation may consume API quota.
