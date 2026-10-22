# JURY — multi-agent stock analysis engine

## The One Rule

JURY is an **analysis and education tool**. It never tells anyone to buy or sell, never promises
returns, and never predicts that a price will move by some amount. Every verdict is an analysis
score out of 100 with one of three labels, **STRONG POSITIVE SIGNALS**, **MIXED** or **WEAK SIGNALS**,
a "Where this analysis could be wrong" section from the Devil's Advocate, and this disclaimer:

> Analysis for education only. Not investment advice.

Owner revision (2026-10-22): the nightly brief may name next-day picks, each with a measured
base-rate probability, entry, stop, target and horizon. See `docs/CLAUDE_PROMPT.md` §0a.

## Nightly run (free DeepSeek step + Opus brief)

```
venv/Scripts/python backend/scripts/nightly.py prepare            # writes data/deepseek/<date>_prompt.md
#   paste it into chat.deepseek.com (Search + DeepThink on), save the reply to data/deepseek/<date>_reply.md
venv/Scripts/python backend/scripts/nightly.py run                # agents + Judge + Opus brief -> data/briefs/<date>.md
venv/Scripts/python backend/scripts/nightly.py review             # how past picks actually did
```

## What it does

Six specialist agents (fundamentals, quant, chart, sentiment, news, devil's advocate), each grounded
in its own slice of a research knowledge base, analyse one NSE stock priced under ₹200. A
deterministic Judge fuses their scores (`config/judge_weights.yaml`). The full spec is in
`docs/CLAUDE_PROMPT.md`.

## Setup (Windows)

```
python -m venv venv
venv/Scripts/python -m pip install -r requirements.txt
copy .env.example .env
venv/Scripts/python backend/scripts/build_kb.py
venv/Scripts/python -m pytest tests
```

## Layout

```
backend/app/kb/        knowledge base store + scoped retriever (M1)
backend/app/data/      market data, NSE screener (M2)
backend/app/services/  chart engine (M2)
backend/app/agents/   prompts (spec §12), schemas, runner, One Rule guard, grounding auditor (M3)
backend/app/llm/      Groq -> Gemini router with JSON validation and repair (M3)
backend/scripts/       build_kb.py, test_retrieval.py, screen.py, chart_report.py, run_jury.py
config/                judge weights, screen filters
knowledge/raw/<collection>/  source documents and placeholder notes
```

## Milestones

M0 scaffold · M1 knowledge base · M2 data layer · M3 agents · M4 judge + API · M5 frontend ·
M6 scheduler, alerts, backtest · M7 Opus layer · M8 polish and deploy
