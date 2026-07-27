"""handle()-mapping for search_companies — q-stien over på det ekte endepunktet.

Bugfiks 2026-07-24: q-stien brukte ``/api/autocomplete`` (maks 10 treff)
+ klient-side status-filtrering — ``q``+``status`` ga derfor 0/ufiltrerte
svar selv etter at ``GET /api/v1/companies/search`` fikk server-side
status-håndheving. Nå: q-stien kaller ``/api/v1/companies/search`` med
q/nace/kommune/status/limit/cursor pass-through; ansatte-spennet
filtreres fortsatt klient-side (endepunktet mangler kolonnespennene);
backend-feil BOBLER som ``FirmaradarClientError`` (server.py mapper til
strukturert feilsvar) i stedet for å maskeres som tomt resultat.
NACE-only-stien er uendret (indeks-effektivt dedikert endepunkt) —
MEN kun når ``fylke`` ikke også er satt (se Group 2 under: fylke-fiks
2026-07-24 — ``/api/v1/nace/{code}/companies`` støtter ikke fylke, så
``fylke`` tvinger ruting til ``/api/v1/companies/search`` selv ved
nace-only, i stedet for å bli stille ignorert slik den ble før).
"""
from __future__ import annotations

import asyncio

import pytest

from firmaradar_mcp.client import FirmaradarClientError
from firmaradar_mcp.tools.search_companies import (
    SearchCompaniesInput,
    handle,
)


class _Stub:
    """Klient-stub som logger kall og svarer med forhåndssatt payload."""

    def __init__(self, payload=None, error: Exception | None = None):
        self.calls: list[tuple[str, dict | None]] = []
        self._payload = payload if payload is not None else {"items": []}
        self._error = error

    async def get(self, path, params=None):
        self.calls.append((path, params))
        if self._error is not None:
            raise self._error
        return self._payload


def _api_item(**overrides):
    d = {
        "orgnr": "913663586",
        "navn": "SCANDIC WORK NORWAY AS",
        "organisasjonsform": "AS",
        "naeringskode": "41.000",
        "kommune": "3324",
        "antall_ansatte": 17,
        "status": "konkurs",
    }
    d.update(overrides)
    return d


def test_q_path_uses_companies_search_endpoint_with_status():
    stub = _Stub({"items": [_api_item()], "next_cursor": None, "total_count": 371})
    out = asyncio.run(handle(stub, SearchCompaniesInput(q="bygg", status="konkurs", limit=5)))

    assert len(stub.calls) == 1
    path, params = stub.calls[0]
    assert path == "/api/v1/companies/search"
    assert params["q"] == "bygg"
    assert params["status"] == "konkurs"
    assert params["limit"] == 5
    # Server-side filtrering er fasit — treffet beholdes som levert.
    assert [i.orgnr for i in out.items] == ["913663586"]
    assert out.items[0].status == "konkurs"
    assert out.total_count == 371


def test_q_path_passes_nace_kommune_and_cursor():
    stub = _Stub({"items": [], "next_cursor": "abc", "total_count": 0})
    out = asyncio.run(handle(stub, SearchCompaniesInput(
        q="ek", nace="47.11", kommune="0301", cursor="prev", limit=10,
    )))
    _, params = stub.calls[0]
    assert params["nace"] == "47.11"
    assert params["kommune"] == "0301"
    assert params["cursor"] == "prev"
    assert out.next_cursor == "abc"


def test_q_path_maps_fields_and_url():
    stub = _Stub({"items": [_api_item()], "total_count": 1})
    out = asyncio.run(handle(stub, SearchCompaniesInput(q="scandic")))
    hit = out.items[0]
    assert hit.navn == "SCANDIC WORK NORWAY AS"
    assert hit.organisasjonsform == "AS"
    assert hit.naeringskode == "41.000"
    assert hit.kommune == "3324"
    assert hit.antall_ansatte == 17
    assert "913663586" in hit.url


def test_q_path_ansatte_range_filters_client_side():
    stub = _Stub({"items": [
        _api_item(orgnr="111111111", antall_ansatte=3),
        _api_item(orgnr="222222222", antall_ansatte=25),
    ], "total_count": 2})
    out = asyncio.run(handle(stub, SearchCompaniesInput(q="bygg", min_ansatte=10)))
    assert [i.orgnr for i in out.items] == ["222222222"]


def test_q_path_backend_error_bubbles_not_empty():
    """400 (f.eks. status=avregistrert) skal bli synlig feil, ikke stille 0."""
    stub = _Stub(error=FirmaradarClientError(
        "Ugyldig status", status_code=400, error_code="bad_request",
    ))
    with pytest.raises(FirmaradarClientError):
        asyncio.run(handle(stub, SearchCompaniesInput(q="bygg", status="avregistrert")))


def test_nace_only_path_still_uses_nace_endpoint():
    stub = _Stub({"items": [], "total_count": 0})
    asyncio.run(handle(stub, SearchCompaniesInput(nace="47", status="konkurs")))
    path, params = stub.calls[0]
    assert path == "/api/v1/nace/47/companies"
    assert params["status"] == "konkurs"


def test_kommune_only_routes_to_search_endpoint():
    """kommune uten q/nace ga tidligere stille tomt svar — nå ekte søk."""
    stub = _Stub({"items": [_api_item()], "total_count": 1})
    out = asyncio.run(handle(stub, SearchCompaniesInput(kommune="0301")))
    path, params = stub.calls[0]
    assert path == "/api/v1/companies/search"
    assert params["kommune"] == "0301"
    assert "q" not in params
    assert len(out.items) == 1


def test_status_only_routes_to_endpoint_for_explicit_400():
    """status alene skal treffe API-et (som svarer 400 med forklaring),
    ikke maskeres som tomt resultat."""
    stub = _Stub(error=FirmaradarClientError(
        "status kan kun brukes sammen med minst ett av q/nace/kommune",
        status_code=400,
    ))
    with pytest.raises(FirmaradarClientError):
        asyncio.run(handle(stub, SearchCompaniesInput(status="konkurs")))
    assert stub.calls[0][0] == "/api/v1/companies/search"


def test_no_filters_returns_empty_without_calls():
    stub = _Stub()
    out = asyncio.run(handle(stub, SearchCompaniesInput()))
    assert out.items == []
    assert stub.calls == []


# ════════════════════════════════════════════════════════════════════════════
# Group 2 — fylke-fiks (2026-07-24): skjemaet lovet fylke siden v0.2, men
# verken ruten eller MCP-verktøyet sendte den videre (stille ignorert).
# ════════════════════════════════════════════════════════════════════════════


def test_q_path_passes_fylke():
    """fylke passthrough på q-stien — samme mønster som nace/kommune."""
    stub = _Stub({"items": [_api_item()], "total_count": 1})
    out = asyncio.run(handle(stub, SearchCompaniesInput(q="ek", fylke="03")))
    path, params = stub.calls[0]
    assert path == "/api/v1/companies/search"
    assert params["fylke"] == "03"
    assert len(out.items) == 1


def test_nace_with_fylke_routes_to_companies_search():
    """VIKTIG ruting-endring 2026-07-24: fylke tvinger companies/search
    selv med nace satt (og uten q) — NACE-endepunktet mangler
    fylke-støtte, og stille ignorering var nettopp buggen som fjernes."""
    stub = _Stub({"items": [_api_item()], "total_count": 1})
    out = asyncio.run(handle(stub, SearchCompaniesInput(nace="47", fylke="03")))
    path, params = stub.calls[0]
    assert path == "/api/v1/companies/search"
    assert params["nace"] == "47"
    assert params["fylke"] == "03"
    assert "q" not in params
    assert len(out.items) == 1


def test_nace_without_fylke_still_uses_nace_endpoint():
    """Regresjon: nace uten fylke skal fortsatt bruke det dedikerte,
    indeks-effektive NACE-endepunktet — uendret av fylke-ruting-fiksen."""
    stub = _Stub({"items": [], "total_count": 0})
    asyncio.run(handle(stub, SearchCompaniesInput(nace="47")))
    path, params = stub.calls[0]
    assert path == "/api/v1/nace/47/companies"
    assert "fylke" not in params


def test_fylke_only_routes_to_endpoint_for_explicit_400():
    """fylke alene (uten q/nace/kommune) skal treffe API-et (som svarer
    400 med forklaring — smalnings-filter uten indeks-støtte, samme
    mønster som status), ikke maskeres som tomt resultat."""
    stub = _Stub(error=FirmaradarClientError(
        "fylke kan kun brukes sammen med minst ett av q/nace/kommune",
        status_code=400,
    ))
    with pytest.raises(FirmaradarClientError):
        asyncio.run(handle(stub, SearchCompaniesInput(fylke="03")))
    assert stub.calls[0][0] == "/api/v1/companies/search"


# ════════════════════════════════════════════════════════════════════════════
# Group 3 — omsetnings-spennet (2026-07-26): skjemaet har lovet
# min/max_omsetning_nok siden v0.1, men ingen backend håndhevet dem. Nå
# implementert server-side på BEGGE endepunktene, med eksplisitt
# ekskludering av selskap uten omsetningstall (rapportert til agenten).
# ════════════════════════════════════════════════════════════════════════════


def test_q_path_passes_omsetning_range():
    stub = _Stub({"items": [_api_item()], "total_count": 1})
    out = asyncio.run(handle(stub, SearchCompaniesInput(
        q="ek", min_omsetning_nok=5_000_000, max_omsetning_nok=50_000_000,
    )))
    path, params = stub.calls[0]
    assert path == "/api/v1/companies/search"
    assert params["min_omsetning_nok"] == 5_000_000
    assert params["max_omsetning_nok"] == 50_000_000
    assert len(out.items) == 1


def test_nace_path_passes_omsetning_range():
    """NACE-only-stien MÅ sende spennet videre — verktøyet ruter
    nace-only-søk til det dedikerte endepunktet, så et filter som bare
    var implementert på companies/search ville fortsatt blitt ignorert."""
    stub = _Stub({"items": [], "total_count": 0})
    asyncio.run(handle(stub, SearchCompaniesInput(
        nace="56.110", min_omsetning_nok=1_000_000,
    )))
    path, params = stub.calls[0]
    assert path == "/api/v1/nace/56.110/companies"
    assert params["min_omsetning_nok"] == 1_000_000
    assert "max_omsetning_nok" not in params


def test_omsetning_only_routes_to_endpoint_for_explicit_400():
    """Spenn uten basefilter skal treffe API-et (som svarer 400 med
    forklaring), ikke maskeres som tomt resultat — samme mønster som
    status/fylke alene."""
    stub = _Stub(error=FirmaradarClientError(
        "min_omsetning_nok/max_omsetning_nok kan kun brukes sammen med "
        "minst ett av q/nace/kommune",
        status_code=400,
    ))
    with pytest.raises(FirmaradarClientError):
        asyncio.run(handle(stub, SearchCompaniesInput(min_omsetning_nok=1)))
    assert stub.calls[0][0] == "/api/v1/companies/search"


def test_nace_path_omsetning_error_bubbles_instead_of_empty():
    """Med spenn aktivt skal en backend-feil på NACE-stien BOBLE — den
    tolerante «tomt resultat»-atferden ville ellers presentert et avvist
    filter som «0 selskap i bransjen»."""
    stub = _Stub(error=FirmaradarClientError("min > max", status_code=400))
    with pytest.raises(FirmaradarClientError):
        asyncio.run(handle(stub, SearchCompaniesInput(
            nace="47", min_omsetning_nok=50, max_omsetning_nok=5,
        )))


def test_nace_path_without_omsetning_still_tolerates_error():
    """Regresjon: uten spenn beholdes den etablerte tolerante atferden."""
    stub = _Stub(error=FirmaradarClientError("boom", status_code=500))
    out = asyncio.run(handle(stub, SearchCompaniesInput(nace="47")))
    assert out.items == []


def test_omsetning_note_uses_backend_meta():
    """Ekskluderings-merknaden fra backend videreformidles til agenten."""
    stub = _Stub({
        "items": [],
        "total_count": 0,
        "_meta": {"omsetning_filter": {"merknad": "Backend-forklaringen."}},
    })
    out = asyncio.run(handle(stub, SearchCompaniesInput(
        q="ek", min_omsetning_nok=1,
    )))
    assert out.omsetning_filter_note == "Backend-forklaringen."


def test_omsetning_note_falls_back_when_meta_missing():
    """Eldre backend uten _meta: agenten skal ALDRI se et
    omsetnings-filtrert svar uten forklaringen på hva som er utelatt."""
    stub = _Stub({"items": [], "total_count": 0})
    out = asyncio.run(handle(stub, SearchCompaniesInput(
        q="ek", min_omsetning_nok=1,
    )))
    assert out.omsetning_filter_note
    assert "ekskludert" in out.omsetning_filter_note


def test_no_omsetning_note_without_filter():
    stub = _Stub({"items": [], "total_count": 0})
    out = asyncio.run(handle(stub, SearchCompaniesInput(q="ek")))
    assert out.omsetning_filter_note is None
