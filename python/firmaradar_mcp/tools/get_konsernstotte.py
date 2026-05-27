"""Tool: ``get_konsernstotte``.

Oversikt over offentlig støtte (NAV-tildelinger, koronastøtte,
Innovasjon Norge, SkatteFUNN) for et selskap og dets konsernhierarki.

Backend: ``GET /api/v1/konsernstotte/oversikt/<orgnr>`` (#130, 2026-05-27).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..client import FirmaradarClient
from . import ToolHandler


class GetKonsernstotteInput(BaseModel):
    orgnr: str = Field(description="9-digit norwegian organization number (typically konsern-toppen).")


class StotteSummary(BaseModel):
    innovasjon_norge: int = 0
    skattefunn: int = 0
    andre: int = 0
    total_belop_nok: float = 0.0


class KonsernNode(BaseModel):
    orgnr: str
    navn: str
    antall_underselskaper: int = 0
    stotte: StotteSummary = Field(default_factory=StotteSummary)
    barn: list[Any] = Field(default_factory=list)


class GetKonsernstotteOutput(BaseModel):
    orgnr: str
    navn: str
    antall_underselskaper: int = 0
    stotte: StotteSummary = Field(default_factory=StotteSummary)
    barn: list[KonsernNode] = Field(default_factory=list)
    raw: dict[str, Any] | None = None


async def handle(
    client: FirmaradarClient, params: GetKonsernstotteInput
) -> GetKonsernstotteOutput:
    payload = await client.get(f"/api/v1/konsernstotte/oversikt/{params.orgnr}")
    if not isinstance(payload, dict):
        payload = {}

    def _parse_summary(d: dict | None) -> StotteSummary:
        d = d or {}
        return StotteSummary(
            innovasjon_norge=int(d.get("innovasjon_norge", 0) or 0),
            skattefunn=int(d.get("skattefunn", 0) or 0),
            andre=int(d.get("andre", 0) or 0),
            total_belop_nok=float(d.get("total_belop_nok", 0) or 0),
        )

    def _parse_node(d: dict) -> KonsernNode:
        return KonsernNode(
            orgnr=str(d.get("orgnr", "")),
            navn=str(d.get("navn", "")),
            antall_underselskaper=int(d.get("antall_underselskaper", 0) or 0),
            stotte=_parse_summary(d.get("stotte")),
            barn=[_parse_node(b) for b in (d.get("barn") or []) if isinstance(b, dict)],
        )

    return GetKonsernstotteOutput(
        orgnr=str(payload.get("orgnr", params.orgnr)),
        navn=str(payload.get("navn", "")),
        antall_underselskaper=int(payload.get("antall_underselskaper", 0) or 0),
        stotte=_parse_summary(payload.get("stotte")),
        barn=[_parse_node(b) for b in (payload.get("barn") or []) if isinstance(b, dict)],
        raw=payload,
    )


HANDLER = ToolHandler(
    name="firmaradar_get_konsernstotte",
    description=(
        "Tree-structured overview of public grants (NAV, Innovasjon Norge, "
        "SkatteFUNN, corona-støtte, other) for a Norwegian company and its "
        "konsern. Returns per-source counters + total NOK amount aggregated "
        "across the group hierarchy. Use for due-diligence, state-aid "
        "compliance checks, or competitive intelligence."
    ),
    input_schema=GetKonsernstotteInput,
    output_schema=GetKonsernstotteOutput,
    handler=handle,
)
