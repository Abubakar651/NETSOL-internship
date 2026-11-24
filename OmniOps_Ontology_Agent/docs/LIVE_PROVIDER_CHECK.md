# Live Cloud Provider Verification (`INC-409`)

- **Checked At (UTC):** `2026-11-24T20:41:51.779089+00:00`
- **Secrets Policy:** All API keys read locally from untracked `.env`; zero keys stored or printed.

| Check | Provider | Model | Status | Elapsed | Culprit PR | Blast Score | Staged Action |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :--- |
| `live_gemini_inc_409` | `gemini` | `gemini-3.5-flash-lite` | **PASSED** | 2.2 s | `PR-882` | 30 | `TriggerSafeRollback` |
| `live_groq_inc_409` | `groq` | `openai/gpt-oss-20b` | **PASSED** | 1.19 s | `PR-882` | 30 | `TriggerSafeRollback` |

See [`LIVE_PROVIDER_CHECK.json`](LIVE_PROVIDER_CHECK.json) for redacted diagnostics.
