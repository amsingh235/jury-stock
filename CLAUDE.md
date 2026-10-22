# JURY — notes for Claude

- Spec: `docs/CLAUDE_PROMPT.md` is the single source of truth. Verdict labels are renamed to
  STRONG POSITIVE SIGNALS / MIXED / WEAK SIGNALS (see `config/judge_weights.yaml`).
- The One Rule: never write advice phrasing (buy/sell recommendations, guaranteed returns,
  price targets) in code, UI strings or comments. Use score-signal framing and the disclaimer.
- Build milestone by milestone; stop after each, report, and wait for "go".
- Python 3.13. On Windows use `venv/Scripts/python`.
- Docstrings on every function.
- KB: one Chroma collection `jury_kb` (cosine), MiniLM embeddings, 240/50 token chunks
  (MiniLM truncates at 256). Agent scope lives in `backend/app/kb/store.py`.
- Chart agent never sees raw prices; it gets `services/chart_engine.py` output only.
- Agent outputs pass through `agents/guard.py` (One Rule redaction) and `agents/auditor.py`
  (numbers and citations must be grounded; else `[UNSOURCED]`). Feed text is untrusted: wrap it
  with `Untrusted(...)` in an agent's inputs. See `docs/FINANCE_AGENTS_INTEGRATION.md`.
