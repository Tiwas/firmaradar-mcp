# NACE code format

`firmaradar_list_companies_in_nace` matches Norwegian industry codes stored in
the **EU NACE Rev. 2** layout used by BRREG, i.e. a 5-digit subgroup written with
a trailing zero.

## Use this format

| Want | Use |
|---|---|
| All retail trade | `47` |
| Retail in non-specialized stores | `47.1` |
| Grocery stores | `47.111` |
| Restaurants | `56.110` |
| Computer programming | `62.100` |
| IT consultancy | `62.200` |

Prefixes work — `47`, `47.1`, `47.11`, `47.110` all match by prefix. The tool
filters additionally by `status` (aktiv/konkurs/under_avvikling/avregistrert),
`kommune` (4-digit number), `min_ansatte`/`max_ansatte`, and
`stiftet_etter`/`stiftet_for` (ISO dates, for newly-founded queries).

## Do not use the old SN2007 short form

`62.01`, `62.02`, `63.01` (SN2007) are **not** stored and return 0 hits. The
backend applies a best-effort heuristic (`XX.0Y → XX.Y0`, e.g. `62.01 → 62.10`)
and, when a code is valid in the catalog but has no companies, returns a
"valid-but-unused code" note instead of a bare empty result — but you should pass
the EU format directly to avoid relying on the fallback.

## International (EU NACE) callers

The Norwegian catalog is a superset of EU NACE Rev. 2: Norway adds extra 5-digit
sub-codes under the shared 4-digit parents. An EU code like `75.000` (veterinary)
maps to Norwegian sub-codes `75.001`, `75.002`, etc. Query the 4-digit/parent
prefix to get all Norwegian sub-codes beneath it.

If unsure of a code, verify against https://www.brreg.no.
