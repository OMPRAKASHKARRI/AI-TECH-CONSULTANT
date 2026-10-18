# AI Assistance Log

This repository was repaired with an AI assistant during the current work session. This is a concise summary of the engineering instructions and decisions; it is **not a Claude Code transcript**. Preserve the actual tool conversation required by the capstone separately if the submission process requires a specific coding assistant.

## Representative instructions used

1. Inspect the existing architecture, `.env` without displaying credentials, tests, and submission documents before making edits.
2. Make the configured Groq provider work with the installed SDK and sanitize auth, quota, model, and network errors.
3. Preserve the meeting transcript, validate structured scope JSON, and calculate low/likely/high effort from task estimates.
4. Keep Task 1 retrieval over HTTP; preserve real source IDs, excerpts, URLs, and human abstention when the index is empty.
5. Compare follow-up scopes only with explicitly approved baselines; keep `needs_changes` unapproved and preserve audit history.

## Rejected approach / decision

**Rejected:** treating an empty Task 1 index as evidence for product capabilities, or substituting offline-generated scope content when a live provider fails. **Reason:** this would fabricate citations or client requirements. Groq request behavior is tested with mocks; no live model quality, cost, or latency result is claimed.

## Human verification still required

The developer should rotate any API key exposed during local inspection, perform a real sitemap sync, review a live Groq-generated scope, run the optional provider integration test and model evaluation if desired, preserve actual results, and rehearse the demo including an unsupported-question and approved-baseline scope-change path.
