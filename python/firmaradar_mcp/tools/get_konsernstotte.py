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


class SelskapStotte(BaseModel):
    """Støtte gitt direkte til *ett* selskap.

    SkatteFUNN/Innovasjon Norge gir aldri støtte til konsern, kun til
    individuelle selskap (#134, 2026-05-27). Aggregeringen på tvers av
    konsernhierarkiet finner du i :class:`KonsernAggregat`.
    """

    innovasjon_norge: int = 0
    skattefunn: int = 0
    andre: int = 0
    # Primær-KPI: SkatteFUNN rapporterer aldri beløp, så total_belop_nok
    # alene gir et skjevt aktivitetsbilde — antall_prosjekter er bedre.
    antall_prosjekter: int = 0
    total_belop_nok: float = 0.0


class KonsernAggregat(BaseModel):
    """Aggregert sum av selskapsstøtte for alle selskap i konsernet.

    "Konsernstøtte" er per definisjon en utledet KPI — ingen kilde gir
    støtte til et konsern direkte. Aggregatet summerer
    :class:`SelskapStotte` for hvert selskap i hierarkiet.
    """

    innovasjon_norge: int = 0
    skattefunn: int = 0
    andre: int = 0
    antall_prosjekter: int = 0
    total_belop_nok: float = 0.0
    antall_selskaper: int = 0


class KonsernNode(BaseModel):
    orgnr: str
    navn: str
    antall_underselskaper: int = 0
    selskap_stotte: SelskapStotte = Field(default_factory=SelskapStotte)
    barn: list[Any] = Field(default_factory=list)


class GetKonsernstotteOutput(BaseModel):
    orgnr: str
    navn: str
    antall_underselskaper: int = 0
    selskap_stotte: SelskapStotte = Field(default_factory=SelskapStotte)
    konsern_aggregat: KonsernAggregat = Field(default_factory=KonsernAggregat)
    barn: list[KonsernNode] = Field(default_factory=list)
    raw: dict[str, Any] | None = None


async def handle(
    client: FirmaradarClient, params: GetKonsernstotteInput
) -> GetKonsernstotteOutput:
    payload = await client.get(f"/api/v1/konsernstotte/oversikt/{params.orgnr}")
    if not isinstance(payload, dict):
        payload = {}

    def _parse_selskap(d: dict | None) -> SelskapStotte:
        d = d or {}
        return SelskapStotte(
            innovasjon_norge=int(d.get("innovasjon_norge", 0) or 0),
            skattefunn=int(d.get("skattefunn", 0) or 0),
            andre=int(d.get("andre", 0) or 0),
            antall_prosjekter=int(d.get("antall_prosjekter", 0) or 0),
            total_belop_nok=float(d.get("total_belop_nok", 0) or 0),
        )

    def _parse_aggregat(d: dict | None) -> KonsernAggregat:
        d = d or {}
        return KonsernAggregat(
            innovasjon_norge=int(d.get("innovasjon_norge", 0) or 0),
            skattefunn=int(d.get("skattefunn", 0) or 0),
            andre=int(d.get("andre", 0) or 0),
            antall_prosjekter=int(d.get("antall_prosjekter", 0) or 0),
            total_belop_nok=float(d.get("total_belop_nok", 0) or 0),
            antall_selskaper=int(d.get("antall_selskaper", 0) or 0),
        )

    def _parse_node(d: dict) -> KonsernNode:
        # ``selskap_stotte`` er det nye nøkkelnavnet (post #134, 2026-05-27);
        # ``stotte`` aksepteres som fallback for kompatibilitet med eldre
        # API-versjoner.
        selskap_payload = d.get("selskap_stotte") or d.get("stotte")
        return KonsernNode(
            orgnr=str(d.get("orgnr", "")),
            navn=str(d.get("navn", "")),
            antall_underselskaper=int(d.get("antall_underselskaper", 0) or 0),
            selskap_stotte=_parse_selskap(selskap_payload),
            barn=[_parse_node(b) for b in (d.get("barn") or []) if isinstance(b, dict)],
        )

    # API-responsen pakker treet inn under ``tre``-nøkkelen og legger
    # konsern-aggregatet (KPI-er på tvers av hele konsernet) på rot-nivå.
    tre = payload.get("tre") if isinstance(payload.get("tre"), dict) else {}
    root_node = _parse_node(tre or {"orgnr": params.orgnr, "navn": ""})
    aggregat = _parse_aggregat(payload.get("konsern_aggregat"))

    return GetKonsernstotteOutput(
        orgnr=root_node.orgnr or params.orgnr,
        navn=root_node.navn,
        antall_underselskaper=root_node.antall_underselskaper,
        selskap_stotte=root_node.selskap_stotte,
        konsern_aggregat=aggregat,
        barn=root_node.barn,
        raw=payload,
    )


HANDLER = ToolHandler(
    name="firmaradar_get_konsernstotte",
    description=(
        "Tree-structured overview of public grants (Innovasjon Norge, "
        "SkatteFUNN, BRREG støtteregister, Prosjektbanken) for a "
        "Norwegian company and its konsern. Returns ``selskap_stotte`` "
        "per node (støtte to that specific company) and ``konsern_aggregat`` "
        "(sum across the full hierarchy). NOTE: SkatteFUNN never reports "
        "amounts — use ``antall_prosjekter`` as the primary activity KPI "
        "since ``total_belop_nok`` excludes SkatteFUNN by source design. "
        "Use for due-diligence, state-aid compliance checks, or "
        "competitive intelligence."
    ),
    input_schema=GetKonsernstotteInput,
    output_schema=GetKonsernstotteOutput,
    handler=handle,
)
