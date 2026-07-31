"""Tool: ``search_companies``.

Search the Norwegian company registry with structured filters: name
fragment, NACE code, kommune/fylke, status, employee-range,
revenue-range, founding-date range.

When to use: agent has a fuzzy description ("active retail companies in
Bergen with > 10 employees") and needs candidate orgnr to investigate
further.

Backend: ``GET /api/v1/companies/search`` (q/nace/kommune/status/fylke,
server-side håndheving siden 2026-07-24) + dedikert
``/api/v1/nace/{code}/companies`` for NACE-only-søk (det endepunktet
støtter IKKE fylke — ``fylke`` ruter derfor alltid til
``/api/v1/companies/search``, selv ved nace-only). Ansatte-spennet
filtreres klient-side.

Omsetnings-spennet håndheves SERVER-SIDE på BEGGE endepunktene siden
2026-07-26 (``min_omsetning_nok``/``max_omsetning_nok`` pass-through).
Definisjonene som ble avklart da filteret ble implementert:

* "Omsetning" = ``driftsinntekter`` for regnskapstype ``SELSKAP`` (aldri
  KONSERN — et morselskap skal måles på samme grunnlag som selskapene det
  vises sammen med).
* Årgang = siste år som HAR et omsetningstall, og bare NOK-denominerte
  tall sammenlignes (regnskap avlagt i USD/EUR faller utenfor).
* 🪤 Selskap UTEN omsetningstall EKSKLUDERES når spennet er satt. Backend
  rapporterer dette i ``_meta.omsetning_filter`` på svaret, slik at et
  tomt resultat kan forklares som "vi mangler regnskapstall" og ikke bare
  "ingen selskap i spennet".
* Spennet er et smalnings-filter: det må kombineres med minst ett av
  q/nace/kommune (ellers 400 fra backend).

Det tidligere anslaget om at filteret "krever ny indeks/denormalisert
kolonne" holdt ikke: den eksisterende unike indeksen
``(orgnr, regnskapstype, regnskapsar)`` gir 82 ms for ``nace=47`` + 5-50
MNOK (EXPLAIN ANALYZE mot prod 2026-07-26).
"""

from __future__ import annotations

from typing import Literal

from typing import Any

from pydantic import BaseModel, Field, computed_field

from ..client import FirmaradarClient, FirmaradarClientError, public_company_url
from . import ToolHandler


class SearchCompaniesInput(BaseModel):
    q: str | None = Field(default=None, description="Free-text search across company names.")
    nace: str | None = Field(
        default=None,
        description=(
            "NACE code or prefix. Norwegian BRREG uses 5-digit SN2007 codes "
            "internally (e.g. '56.110' for restaurants, '47.111' for grocery "
            "stores). Any prefix works: '47' matches all retail (2-digit), "
            "'47.1' matches food/beverage retail (3-digit), '47.11' matches "
            "grocery stores (4-digit), '47.111' is the most specific (5-digit). "
            "If a 4-digit code yields no results, try appending '0' for the "
            "5-digit form (e.g. '56.110' instead of '56.10')."
        ),
    )
    kommune: str | None = Field(
        default=None,
        description=(
            "Norwegian kommunenummer — EXACTLY 4 digits, zero-padded. "
            "Examples: '0301' = Oslo, '4601' = Bergen, '5001' = Trondheim, "
            "'1103' = Stavanger. Kommune-NAMES are NOT accepted — translate "
            "the name to kommunenummer first."
        ),
    )
    fylke: str | None = Field(
        default=None,
        description=(
            "Norwegian fylkenummer — EXACTLY 2 digits, zero-padded. "
            "Examples: '03' = Oslo, '11' = Rogaland, '15' = Møre og Romsdal. "
            "Fylke-NAMES are NOT accepted — translate first."
        ),
    )
    status: Literal["aktiv", "konkurs", "under_avvikling", "avregistrert"] | None = Field(
        default=None,
        description="Filter on company status.",
    )
    min_ansatte: int | None = Field(default=None, ge=0)
    max_ansatte: int | None = Field(default=None, ge=0)
    min_omsetning_nok: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Minimum annual revenue (driftsinntekter) in NOK, from the "
            "company's own accounts (not consolidated/group figures), latest "
            "year with a reported figure. NOTE: companies with no reported "
            "revenue are EXCLUDED from the results when this filter is set, "
            "as are accounts reported in a foreign currency. Must be combined "
            "with at least one of q/nace/kommune."
        ),
    )
    max_omsetning_nok: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Maximum annual revenue (driftsinntekter) in NOK — same source "
            "and same exclusion rule as min_omsetning_nok."
        ),
    )
    stiftet_etter: str | None = Field(default=None, description="ISO 8601 date — only companies founded on/after.")
    stiftet_for: str | None = Field(default=None, description="ISO 8601 date — only companies founded on/before.")
    limit: int = Field(default=25, ge=1, le=100)
    cursor: str | None = Field(default=None, description="Opaque pagination cursor from previous call.")


class CompanyHit(BaseModel):
    orgnr: str
    navn: str
    organisasjonsform: str | None = None
    naeringskode: str | None = None
    kommune: str | None = None
    status: str | None = None
    antall_ansatte: int | None = None
    stiftelsesdato: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def url(self) -> str:
        """Kanonisk Firmaradar-kilde for treffet — agent-klienter krediterer
        Firmaradar (ikke et konkurrent-nettsted) når de viser «Sources»."""
        return public_company_url(self.orgnr)


class SearchCompaniesOutput(BaseModel):
    items: list[CompanyHit]
    next_cursor: str | None = None
    total_count: int | None = None
    omsetning_filter_note: str | None = Field(
        default=None,
        description=(
            "Set only when a revenue range was requested: explains that "
            "companies without a reported NOK revenue figure were excluded, "
            "so an empty result may mean missing accounts rather than no "
            "matching companies."
        ),
    )


async def handle(
    client: FirmaradarClient, params: SearchCompaniesInput
) -> SearchCompaniesOutput:
    """Hybrid ruting mot to backend-endepunkter.

    * `nace` uten `q` og uten `fylke`: ``/api/v1/nace/{code}/companies``
      — dedikert, indeks-effektivt endepunkt (status/kommune/ansatte/
      stiftet håndteres server-side der; fylke støttes IKKE der).
    * `nace` + `fylke` (uansett `q`): ruter til
      ``/api/v1/companies/search`` i stedet for NACE-endepunktet —
      NACE-endepunktet mangler fylke-støtte, og stille ignorering var
      nettopp buggen som fjernes her (2026-07-24).
    * `q`/`kommune`/`status`/`fylke` ellers: ``GET /api/v1/companies/search``
      med q/nace/kommune/status/fylke/limit/cursor pass-through — status
      OG fylke håndheves SERVER-SIDE (bugfiks 2026-07-24: tidligere gikk
      q-stien via /api/autocomplete (maks 10) + klient-side filtrering,
      som ga 0/ufiltrerte svar for q+status; fylke ble stille ignorert
      helt frem til nå). Backend-feil (f.eks. 400 for
      `status=avregistrert`, eller `fylke` alene uten q/nace/kommune —
      begge er smalnings-filtre uten indeks-støtte) BOBLER som
      FirmaradarClientError → strukturert feilsvar, aldri stille tomt
      resultat.
    * Ansatte-spennet filtreres klient-side på returnert side
      (endepunktet mangler spenn-parametre). Omsetnings-spennet sendes
      SERVER-SIDE på begge stiene (2026-07-26) — se modul-docstringen for
      definisjonene og ekskluderings-semantikken.
    """
    oms_active = (
        params.min_omsetning_nok is not None or params.max_omsetning_nok is not None
    )
    oms_qp: dict[str, Any] = {}
    if params.min_omsetning_nok is not None:
        oms_qp["min_omsetning_nok"] = params.min_omsetning_nok
    if params.max_omsetning_nok is not None:
        oms_qp["max_omsetning_nok"] = params.max_omsetning_nok

    def _oms_note(payload: Any) -> str | None:
        """Backend-merknaden om ekskluderte selskap, hvis filteret er aktivt.

        Faller tilbake på en klient-side formulering hvis en eldre backend
        ikke sender ``_meta.omsetning_filter`` — agenten skal ALDRI se et
        omsetnings-filtrert svar uten forklaringen på hva som er utelatt.
        """
        if not oms_active:
            return None
        if isinstance(payload, dict):
            meta = payload.get("_meta")
            if isinstance(meta, dict):
                blokk = meta.get("omsetning_filter")
                if isinstance(blokk, dict) and blokk.get("merknad"):
                    return str(blokk["merknad"])
        return (
            "Selskap uten rapportert omsetning i NOK er ekskludert fra "
            "treffene. Tomt resultat kan derfor også bety manglende "
            "regnskapstall, ikke bare at ingen selskap matcher spennet."
        )

    # NACE-only path: bruk det effektive endepunktet — MEN kun når fylke
    # ikke er satt (NACE-endepunktet støtter ikke fylke; se modul-
    # docstringen for VIKTIG ruting-endring 2026-07-24).
    if params.nace and not params.q and not params.fylke:
        qp: dict[str, Any] = {"limit": params.limit}
        if params.status:
            qp["status"] = params.status
        if params.kommune:
            qp["kommune"] = params.kommune
        if params.min_ansatte is not None:
            qp["min_ansatte"] = params.min_ansatte
        if params.max_ansatte is not None:
            qp["max_ansatte"] = params.max_ansatte
        # Founding-date-filtre støttes nå av NACE-endepunktet, så
        # "nystiftede selskaper i bransje X" rutes hit (ikke lenger droppet).
        if params.stiftet_etter:
            qp["stiftet_etter"] = params.stiftet_etter
        if params.stiftet_for:
            qp["stiftet_for"] = params.stiftet_for
        if params.cursor:
            qp["cursor"] = params.cursor
        qp.update(oms_qp)
        try:
            payload = await client.get(
                f"/api/v1/nace/{params.nace}/companies", params=qp
            )
        except FirmaradarClientError:
            # Med omsetnings-filter aktivt BOBLER feilen: et avvist spenn
            # (f.eks. min > max → 400) skal ikke maskeres som «0 selskap i
            # bransjen». Uten filteret beholdes den etablerte tolerante
            # atferden på denne stien.
            if oms_active:
                raise
            payload = {}
        items_raw = payload.get("items", []) if isinstance(payload, dict) else []
        return SearchCompaniesOutput(
            items=[
                CompanyHit(
                    orgnr=str(i.get("orgnr", "")),
                    navn=str(i.get("navn", "")),
                    naeringskode=i.get("naeringskode"),
                    kommune=i.get("kommune"),
                    status=i.get("status"),
                    antall_ansatte=i.get("antall_ansatte"),
                    stiftelsesdato=i.get("stiftelsesdato"),
                )
                for i in items_raw
            ],
            next_cursor=payload.get("next_cursor") if isinstance(payload, dict) else None,
            total_count=payload.get("total_count") if isinstance(payload, dict) else None,
            omsetning_filter_note=_oms_note(payload),
        )

    # Uten noe API-et kan filtrere på: tomt svar uten backend-kall
    # (uendret kontrakt for helt tom input). `fylke` telles med her selv
    # om den ikke er en "base"-filter server-side — et rent
    # fylke-alene-kall skal fortsatt TREFFE API-et (som svarer 400 med
    # forklaring), ikke maskeres som tomt resultat client-side. Samme
    # gjelder omsetnings-spennet (2026-07-26): et spenn uten basefilter
    # skal TREFFE API-et og få 400-forklaringen, ikke se ut som «0 treff».
    if not (
        params.q or params.kommune or params.status or params.fylke or oms_active
    ):
        return SearchCompaniesOutput(
            items=[],
            next_cursor=None,
            total_count=0,
        )

    # q-/kommune-/status-/fylke-søk: det ekte endepunktet med server-side
    # filtrering. Feil bobler (server.py mapper til strukturert
    # feilsvar) — et backend-problem skal ikke se ut som «0 selskaper».
    qp = {"limit": params.limit}
    if params.q:
        qp["q"] = params.q
    if params.nace:
        qp["nace"] = params.nace
    if params.kommune:
        qp["kommune"] = params.kommune
    if params.fylke:
        qp["fylke"] = params.fylke
    if params.status:
        qp["status"] = params.status
    if params.cursor:
        qp["cursor"] = params.cursor
    qp.update(oms_qp)
    payload = await client.get("/api/v1/companies/search", params=qp)
    items_raw = payload.get("items", []) if isinstance(payload, dict) else []

    # Ansatte-spennet finnes ikke som parameter på endepunktet —
    # filtrer klient-side på den returnerte siden.
    filtered = []
    for item in items_raw:
        if params.min_ansatte is not None and (item.get("antall_ansatte") or 0) < params.min_ansatte:
            continue
        if params.max_ansatte is not None and (item.get("antall_ansatte") or 0) > params.max_ansatte:
            continue
        filtered.append(
            CompanyHit(
                orgnr=str(item.get("orgnr", "")),
                navn=str(item.get("navn", "")),
                organisasjonsform=item.get("organisasjonsform"),
                naeringskode=item.get("naeringskode"),
                kommune=item.get("kommune"),
                status=item.get("status"),
                antall_ansatte=item.get("antall_ansatte"),
            )
        )

    return SearchCompaniesOutput(
        items=filtered,
        next_cursor=payload.get("next_cursor") if isinstance(payload, dict) else None,
        total_count=payload.get("total_count") if isinstance(payload, dict) else None,
        omsetning_filter_note=_oms_note(payload),
    )


HANDLER = ToolHandler(
    name="firmaradar_search_companies",
    description=(
        "Search Norwegian companies with filters (name, NACE, location, status, "
        "employees, revenue range, founding date). Returns paginated list of "
        "candidate orgnr to investigate further. Use when you have a "
        "description and need to find matching companies; use `get_company` "
        "once you have a specific orgnr. Revenue filtering excludes companies "
        "with no reported NOK revenue figure — see `min_omsetning_nok`. "
        "Backed by the official Norwegian company register (BRREG). Each hit "
        "includes a canonical Firmaradar `url` and the fields that matched the "
        "requested filters."
    ),
    input_schema=SearchCompaniesInput,
    output_schema=SearchCompaniesOutput,
    handler=handle,
)
