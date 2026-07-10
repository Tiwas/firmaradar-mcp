"""handle()-mapping for check_aml_pep — PEP-treff bærer nå verv_historikk (v14) +
verv-kontekst (embete/verv_fra/verv_til/pep_status). Verifiserer at output-modellen
parser den fulle datostemplede tidslinjen og at sanksjons-treff er upåvirket."""
from __future__ import annotations

import asyncio

from firmaradar_mcp.tools.check_aml_pep import CheckAmlPepInput, handle


class _Stub:
    def __init__(self, payload):
        self._p = payload

    async def post(self, path, json_body=None, extra_headers=None):
        return self._p


def _run(payload):
    return asyncio.run(handle(
        _Stub(payload),
        CheckAmlPepInput(name="Kari Nordmann", purpose="KYC av ny kunde"),
    ))


def test_pep_hit_carries_verv_historikk_and_context():
    tidslinje = [
        {"embete": "Statsråd/minister", "klasse": "minister",
         "tittel": "næringsminister", "pos_qid": "Q123",
         "fra": "2021-01-01", "til": "2024-01-01"},
        {"embete": "Statsråd/minister", "klasse": "minister",
         "tittel": "næringsminister", "pos_qid": "Q123",
         "fra": "2024-01-01", "til": None},
    ]
    payload = {
        "query_name": "Kari Nordmann", "query_birth_year": None, "hit_count": 1,
        "hits": [{
            "primart_navn": "Kari Nordmann", "kategori": "pep",
            "entitet_type": "person", "kilder": ["pep_wikidata"],
            "match_ratio": 1.0, "match_type": "eksakt", "weak_match": False,
            "ekstern_id": "kan-1", "pep_status": "aktiv",
            "embete": "Statsråd/minister", "verv_fra": "2021-01-01",
            "verv_til": None, "verv_historikk": tidslinje,
        }],
    }
    out = _run(payload)
    hit = out.hits[0]
    assert hit.pep_status == "aktiv"
    assert hit.embete == "Statsråd/minister"
    assert hit.verv_historikk == tidslinje
    assert hit.verv_historikk[0]["tittel"] == "næringsminister"


def test_sanksjon_hit_defaults_empty_verv_historikk():
    """Sanksjons-treff har ingen verv-felter i payloaden → modellen defaulter trygt."""
    payload = {
        "query_name": "ACME LLC", "query_birth_year": None, "hit_count": 1,
        "hits": [{
            "primart_navn": "ACME LLC", "kategori": "sanksjon",
            "entitet_type": "organisasjon", "kilder": ["ofac"],
            "match_ratio": 0.95, "match_type": "fuzzy", "weak_match": False,
            "ekstern_id": "ofac-9",
        }],
    }
    out = _run(payload)
    hit = out.hits[0]
    assert hit.verv_historikk == []
    assert hit.pep_status is None
    assert hit.embete is None
