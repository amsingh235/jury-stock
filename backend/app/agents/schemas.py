"""JSON output schemas for the six agents (spec §4 table).

Every agent also returns the common fields the Judge needs: a 0-100 ``score``
(for the Devil's Advocate, ``risk_score``), a confidence level, cited reasoning
and data gaps.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Confidence = Literal["LOW", "MEDIUM", "HIGH"]
Score = Field(ge=0, le=100)


class Common(BaseModel):
    """Fields shared by every agent output."""

    confidence: Confidence
    reasoning: str = Field(description="Interpretation citing retrieved research as (Author, Year)")
    citations: list[str] = Field(default_factory=list, description="(Author, Year) strings actually used")
    data_gaps: list[str] = Field(default_factory=list)
    disconfirming_evidence: list[str] = Field(
        default_factory=list, description="Evidence in the inputs that cuts against your own reading")


class FundamentalScores(BaseModel):
    """Sub-scores for the fundamentals agent."""

    value: int = Score
    quality: int = Score
    growth: int = Score


class FundamentalsOut(Common):
    """Agent 1: is this business good and cheap?"""

    score: int = Score
    scores: FundamentalScores
    thesis: str
    red_flags: list[str] = Field(default_factory=list)
    peer_rank: str = Field(description="Position vs sector peers, e.g. 'top quartile of 6 peers' or 'no peer data'")


class QuantOut(Common):
    """Agent 2: what do the statistical factors say?"""

    score: int = Score
    factor_scores: dict[str, int] = Field(description="0-100 per factor: momentum_12_1, reversal_1m, high_52w, beta, idio_vol, size, liquidity")
    regime: str = Field(description="e.g. 'trending, high vol' or 'mean-reverting, low vol'")


class PatternRead(BaseModel):
    """One chart pattern as interpreted by the chart agent."""

    pattern: str
    status: str
    failure_rate_pct: float | None = None
    reliability: str = Field(description="Grade from Bulkowski's stats, flagged if unverified")


class ChartOut(Common):
    """Agent 3: what does price action itself say?"""

    score: int = Score
    patterns_found: list[PatternRead] = Field(default_factory=list)
    indicators: dict[str, str] = Field(description="Indicator name -> one-line reading of the engine's value")
    trend: str
    support_resistance: list[str] = Field(default_factory=list)
    pattern_reliability: str
    edge: Literal["edge", "no edge"] = Field(description="'no edge' when fewer than 2 independent signals agree")


class SentimentOut(Common):
    """Agent 4: what is the crowd's mood and is it shifting?"""

    score: int = Score
    sentiment_score: int = Field(ge=-100, le=100, description="-100 very negative .. +100 very positive")
    tone_shift: Literal["improving", "deteriorating", "stable", "unknown"]
    key_phrases: list[str] = Field(default_factory=list)
    hype_risk: Literal["LOW", "MEDIUM", "HIGH"]
    independent_sources: int = Field(ge=0)


class EventRead(BaseModel):
    """One event as scored by the news agent."""

    event: str
    date: str | None = None
    kind: Literal["scheduled", "unscheduled", "rumor"]
    verified: bool
    expected_impact: Literal["positive", "negative", "neutral", "uncertain"]
    rumor_risk: bool = False


class NewsOut(Common):
    """Agent 5: what just happened that reprices this?"""

    score: int = Score
    events: list[EventRead] = Field(default_factory=list)
    expected_impact: Literal["positive", "negative", "neutral", "uncertain"]
    drift_signal: Literal["positive_drift", "negative_drift", "none", "gap_risk"]


class Bias(BaseModel):
    """A bias the devil's advocate spotted in another agent."""

    agent: str
    bias: str
    why: str


class DevilsAdvocateOut(Common):
    """Agent 6: why is everyone else wrong?"""

    risk_score: int = Field(ge=0, le=100, description="0 = evidence survives the audit, 100 = thesis collapses")
    counter_thesis: str
    biases_spotted: list[Bias] = Field(default_factory=list)
    failure_scenarios: list[str] = Field(default_factory=list)
    what_would_change_my_mind: str
    where_analysis_could_be_wrong: str


SCHEMAS: dict[str, type[Common]] = {
    "fundamentals": FundamentalsOut,
    "quant": QuantOut,
    "chart": ChartOut,
    "sentiment": SentimentOut,
    "news": NewsOut,
    "devils_advocate": DevilsAdvocateOut,
}
