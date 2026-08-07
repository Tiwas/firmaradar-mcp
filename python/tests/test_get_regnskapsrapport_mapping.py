"""handle()-mapping for get_regnskapsrapport.

Verifiserer at verktøyet former riktig GET-path/params mot
``/api/v1/regnskapsrapport/<orgnr>`` og leser backend-konvolutten
(``download_url``, ``antall_aar``, ``kilde``, ``valuta``, …) korrekt —
uten å røre ekte konto/fakturering (stub-klient, selvkontrollert input).
"""
from __future__ import annotations

import asyncio

from firmaradar_mcp.tools.get_regnskapsrapport import (
    GetRegnskapsrapportInput,
    handle,
)


class _Stub:
    def __init__(self, payload):
        self._p = payload
        self.calls = []

    async def get(self, path, params=None):
        self.calls.append(("GET", path, params))
        return self._p


def test_sends_format_regnskapstype_and_years_as_query_params():
    stub = _Stub({
        "orgnr": "923609016", "regnskapstype": "SELSKAP", "format": "xlsx",
        "antall_aar": 5, "maks_aar": 5, "aar": [2025, 2024, 2023, 2022, 2021],
        "kilde": "BRREG · digital", "valuta": "NOK",
        "download_url": "https://api.firmaradar.no/api/v1/regnskapsrapport/download/xyz",
        "expires_in": 900,
    })
    out = asyncio.run(handle(
        stub,
        GetRegnskapsrapportInput(orgnr="923609016", format="xlsx",
                                 regnskapstype="SELSKAP", years=5),
    ))
    assert stub.calls[0][:2] == ("GET", "/api/v1/regnskapsrapport/923609016")
    assert stub.calls[0][2] == {"format": "xlsx", "regnskapstype": "SELSKAP", "years": 5}
    assert out.antall_aar == 5
    assert out.download_url.endswith("/xyz")
    assert out.expires_in == 900
    assert out.kilde == "BRREG · digital"
    assert out.valuta == "NOK"


def test_defaults_are_pdf_selskap_five_years():
    stub = _Stub({"orgnr": "111111111", "download_url": "https://x/y", "antall_aar": 3})
    asyncio.run(handle(stub, GetRegnskapsrapportInput(orgnr="111111111")))
    assert stub.calls[0][2] == {"format": "pdf", "regnskapstype": "SELSKAP", "years": 5}


def test_missing_optional_fields_default_to_none_or_zero():
    stub = _Stub({"orgnr": "111111111", "download_url": "https://x/y"})
    out = asyncio.run(handle(stub, GetRegnskapsrapportInput(orgnr="111111111")))
    assert out.antall_aar == 0
    assert out.maks_aar is None
    assert out.aar is None
    assert out.kilde is None
    assert out.valuta is None
    assert out.expires_in == 0


def test_non_dict_payload_does_not_crash():
    out = asyncio.run(handle(_Stub(None), GetRegnskapsrapportInput(orgnr="111111111")))
    assert out.orgnr == "111111111"
    assert out.download_url == ""
    assert out.antall_aar == 0
