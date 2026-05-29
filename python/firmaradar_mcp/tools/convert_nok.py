"""Tool: ``convert_nok``.

Convert a NOK amount to a foreign currency (EUR/USD/GBP/SEK/DKK) using
daily exchange rates from Norges Bank (the Norwegian central bank). Useful
for international consumers who want Firmaradar's NOK financials expressed
in their own currency. The NOK original is always preserved.

Backend: ``GET /api/v1/currency/convert?amount=<nok>&to=<ISO4217>``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..client import FirmaradarClient
from . import ToolHandler


class ConvertNokInput(BaseModel):
    amount_nok: float | None = Field(
        default=None,
        description=(
            "Amount in NOK to convert. Omit to fetch only the current rate "
            "(the response 'amount' will be null)."
        ),
    )
    to_currency: str = Field(
        description=(
            "Target ISO 4217 currency code. Supported: EUR, USD, GBP, SEK, DKK."
        ),
    )


class ConvertNokOutput(BaseModel):
    amount_nok: float | None = Field(
        default=None, description="The original NOK amount (preserved, unchanged)."
    )
    amount: float | None = Field(
        default=None, description="Converted amount in the target currency."
    )
    currency: str = Field(description="Target currency (ISO 4217).")
    rate: float = Field(
        description="Multiplier applied: amount = amount_nok * rate (target units per NOK)."
    )
    rate_date: str | None = Field(
        default=None, description="ISO date of the Norges Bank observation."
    )
    source: str = Field(default="norges_bank", description="Rate source.")


async def handle(
    client: FirmaradarClient, params: ConvertNokInput
) -> ConvertNokOutput:
    qp: dict[str, Any] = {"to": params.to_currency}
    if params.amount_nok is not None:
        qp["amount"] = params.amount_nok
    payload = await client.get("/api/v1/currency/convert", params=qp)
    if not isinstance(payload, dict):
        payload = {}
    return ConvertNokOutput(
        amount_nok=payload.get("amount_nok"),
        amount=payload.get("amount"),
        currency=str(payload.get("currency", params.to_currency)),
        rate=float(payload.get("rate", 0.0) or 0.0),
        rate_date=payload.get("rate_date"),
        source=str(payload.get("source", "norges_bank")),
    )


HANDLER = ToolHandler(
    name="firmaradar_convert_nok",
    description=(
        "Convert a NOK amount to a foreign currency (EUR, USD, GBP, SEK, DKK) "
        "using daily exchange rates from Norges Bank (the Norwegian central "
        "bank). Firmaradar's financial figures are reported in NOK; use this to "
        "express them in another currency for international workflows. The NOK "
        "original is always preserved in the response. Omit amount_nok to fetch "
        "just the current rate."
    ),
    input_schema=ConvertNokInput,
    output_schema=ConvertNokOutput,
    handler=handle,
)
