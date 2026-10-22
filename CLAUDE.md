# JURY — notes for Claude

- Spec: `docs/CLAUDE_PROMPT.md` is the single source of truth. Verdict labels are renamed to
  STRONG POSITIVE SIGNALS / MIXED / WEAK SIGNALS (see `config/judge_weights.yaml`).
- The One Rule: agents, Judge, UI and comments never use advice phrasing (buy/sell
  recommendations, guaranteed returns, price targets); use score-signal framing and the disclaimer.
  Owner revision 2026-10-22 (spec §0a): only the nightly brief may name picks, each with a measured
  base-rate probability (Opus may adjust by at most +/-10 pts, cap 80%), stop, target, horizon and
  disclaimer. No hype or certainty claims anywhere (guard level "brief").
- DeepSeek is used manually and free: `nightly.py prepare` writes a prompt, the owner pastes
  DeepSeek's reply into data/deepseek/<date>_reply.md; it is UNVERIFIED input to the agents.
- Build milestone by milestone; stop after each, report, and wait for "go".
- Python 3.13. On Windows use `venv/Scripts/python`.
- Docstrings on every function.
- KB: one Chroma collection `jury_kb` (cosine), MiniLM embeddings, 240/50 token chunks
  (MiniLM truncates at 256). Agent scope lives in `backend/app/kb/store.py`.
- Chart agent never sees raw prices; it gets `services/chart_engine.py` output only.
- Agent outputs pass through `agents/guard.py` (One Rule redaction) and `agents/auditor.py`
  (numbers and citations must be grounded; else `[UNSOURCED]`). Feed text is untrusted: wrap it
  with `Untrusted(...)` in an agent's inputs. See `docs/FINANCE_AGENTS_INTEGRATION.md`.
- Pipeline per stock: 5 analysts (parallel) -> Bull vs Bear debate (`agents/debate.py`, default 2
  rounds, Bull opens) -> Devil's Advocate (audits analysts + debate) -> Judge (deterministic score,
  LLM chart study) -> nightly brief. The debate never enters the score formula.
