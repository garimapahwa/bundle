"""Pydantic models for the Bundle exposure audit.

Three kinds of models live here:
- What the agent must write (`AuditDraft`): the headline, the summary, and the top 5 fixes with
  why each matters.
- What the user pays for (`AuditReport`): the draft plus the numbers the code computes itself
  (score, rank, industry average, findings), so the LLM can never invent them.
- One dataset row per finding (`FindingRow`).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Fix(BaseModel):
    """One of the top fixes, in priority order."""

    title: str = Field(description='Short imperative title, for example "Stop sending PAN numbers to the profile page".')
    fix: str = Field(description='What the engineering team should change, in one or two sentences.')
    why_it_matters: str = Field(
        description='Why it matters for the business: the risk, and where relevant the DPDP Act, 2023 duty it touches '
        '(reasonable security safeguards, data minimisation, purpose limitation). Say "may", not legal certainty.'
    )
    related: list[str] = Field(description='The field_or_key values of the findings this fix addresses, copied exactly.')


class AuditDraft(BaseModel):
    """The structured answer the agent returns at the end of the loop."""

    company: str = Field(description='The company name, for example "Groww".')
    headline: str = Field(description='One sentence: the most important exposure, and how the site compares with its peers.')
    summary: str = Field(description='Three or four sentences for a founder or CISO: what is exposed, how bad it is, and what to do first.')
    top_fixes: list[Fix] = Field(description='Up to 5 fixes, most important first, each tied to real findings.')
    caveats: list[str] = Field(description='Two or three honest limits, for example that only public pages were checked.')


class PeerStat(BaseModel):
    """One peer, anonymous."""

    label: str
    exposure_score: int
    overexposed_per_page: float
    high_severity: int


class AuditReport(BaseModel):
    """The full report, saved as REPORT, report.md, and report.html in the key-value store."""

    target: str
    company: str
    industry: str
    headline: str
    summary: str
    exposure_score: int = Field(description='0 (nothing exposed) to 100.')
    rank: str | None = Field(description='For example "2 of 5 (1 = least exposed)". None without peers.')
    you: dict[str, Any]
    industry_average: dict[str, Any] | None
    peers: list[PeerStat]
    top_fixes: list[Fix]
    findings_by_category: dict[str, int]
    findings: list[dict[str, Any]] = Field(default_factory=list, description='The main findings, grouped, most serious first.')
    stats: dict[str, Any]
    caveats: list[str]
    scanned_at: str | None = None
    report_url: str | None = None


class FindingRow(BaseModel):
    """One dataset row per finding. Never contains a field value."""

    finding: str
    category: str
    severity: Literal['high', 'medium', 'low']
    field_or_key: str
    evidence_url: str
    peer_benchmark: str
    fix: str
