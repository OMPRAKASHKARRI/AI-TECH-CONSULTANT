# Evaluation Report

## Test inventory

The repository contains 20 task-specific evaluation cases per task in `evaluations/task1_cases.json`, `evaluations/task2_cases.json`, and `evaluations/task3_cases.json`. The pytest suite includes 20 Task 1 retrieval relevance cases, 20 Task 2 structured-classification contract cases, 20 Task 3 scope-change/approval cases, and an autonomy-streak boundary test. These are deterministic tests with mocked model output where appropriate; they **do not measure live LLM accuracy**.

## Latest local test run

Executed in the project directory with `python -m pytest -q` after repairs:

- **132 passed, 2 skipped** in the full suite; **64 passed** in the focused Task 3/Task 1 regression set.
- Unit tests mock provider and Task 1 HTTP calls; they do not call a paid model or crawl the public sitemap.
- Python `compileall` completed successfully. Task 3 returned HTTP 200 for both `/_stcore/health` and the app page on a temporary local port.
- The skipped cases include the opt-in live provider test; no live Groq request was made.

Run `python -m pip install -r requirements.txt`, then `python -m pytest -q` before submission. `python -m compileall -q shared task1_knowledge_brain task2_inbox_agent task3_meeting_scope` provides a syntax check.

## Metrics and model comparison

The live model comparison and optional Groq integration test have **not been executed**. No quality, latency, or cost figures are fabricated. The default primary provider is Groq; tests mock its API requests. To opt in to a real test call:

```powershell
$env:RUN_GROQ_INTEGRATION = "1"
python -m pytest tests\test_groq_integration.py -q
```

To run the live 120-request comparison, set `EVAL_PROVIDER=groq` (or `anthropic`) and a comma-separated `EVAL_MODELS` list of supported models before running `python scripts/evaluate_models.py`. This consumes provider quota. The script records task-level contract pass rate, JSON-valid rate, mean latency, input/output token usage, and estimated cost only if per-model price variables are set. Verify provider model IDs and pricing before running. Its pass-rate criteria are deliberately narrow and are not full answer-quality evaluations.

## Coverage focus

- **Task 1:** relevant source retrieval, empty/missing evidence behavior in the implementation, citation payload shape, screenshot alt/caption retention, optional Claude vision enrichment, ingestion status/checkpoints.
- **Task 2:** valid/invalid model JSON, allowed category/urgency values, review persistence, category-specific human edits, and the 19-to-20 approval boundary and reset condition.
- **Task 3:** JSON parsing/validation, per-task low/likely/high values and calculated totals, Task 1 HTTP citations and abstention states, scope additions/modifications/removals, explicit approval, `needs_changes` audit history, and approved-baseline comparisons.

## Limitations / pending validation

- Live crawl of `https://support.brilliantdirectories.com/support/sitemap.xml` has not been verified from this environment.
- Live Groq generation has not been verified; no real API request was made.
- Current local Task 1 API health is healthy, but its SQLite index has zero articles and no ingestion runs. The ask endpoint correctly abstains with no citations until a knowledge sync completes.
- Claude vision ingestion requires Anthropic credentials and has not been measured here.
- End-to-end browser/UI workflows and clean install of all UI dependencies must be run by the submitter.
- TF-IDF retrieval is a lexical baseline; scope-change aliases are finite; low/high estimates are heuristic bands.
- Model-only evaluations are not a substitute for 20+ human-reviewed quality cases per task or a full end-to-end evaluation. Retain the generated comparison JSON and record human review results before claiming those validations are complete.
