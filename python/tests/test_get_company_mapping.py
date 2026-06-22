"""get_company-mapping — additivt oppstillingsplan_forklaring-felt så LLM-klienter
ikke forveksler BRREG-regnskapsformatet («store») med selskapsstørrelse (QA-funn
2026-06-22, ChatGPT)."""
from __future__ import annotations

from firmaradar_mcp.tools.get_company import _annotate_oppstillingsplan


def test_store_oppstillingsplan_gets_size_disambiguation():
    fm = {"oppstillingsplan": "store", "driftsinntekter": 2_325_646}
    out = _annotate_oppstillingsplan(fm)
    assert out["oppstillingsplan"] == "store"  # rå-verdi uendret
    assert "IKKE selskapsstørrelse" in out["oppstillingsplan_forklaring"]
    assert out["oppstillingsplan_forklaring"].startswith("Stor oppstillingsplan")
    # Ikke-muterende: original urørt.
    assert "oppstillingsplan_forklaring" not in fm


def test_smaa_and_full_variants():
    assert _annotate_oppstillingsplan({"oppstillingsplan": "smaa"})[
        "oppstillingsplan_forklaring"
    ].startswith("Liten oppstillingsplan")
    assert _annotate_oppstillingsplan({"oppstillingsplan": "full"})[
        "oppstillingsplan_forklaring"
    ].startswith("Full oppstillingsplan")


def test_no_oppstillingsplan_is_passthrough():
    fm = {"driftsinntekter": 100}
    assert _annotate_oppstillingsplan(fm) is fm
    assert _annotate_oppstillingsplan(None) is None


def test_unknown_value_still_disambiguates():
    out = _annotate_oppstillingsplan({"oppstillingsplan": "noe-rart"})
    assert "IKKE selskapsstørrelse" in out["oppstillingsplan_forklaring"]
