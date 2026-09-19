from __future__ import annotations

import pandas as pd

from matching import normalize_vat

VALID = "valid"
INVALID = "invalid"
ERROR = "error"
NON_SUPPORTATO = "non_supportato"
NON_APPLICABILE = "non_applicabile"  # cliente senza P.IVA (es. extra-UE)


def build_full_vat(partita_iva: str | None, paese_iso: str | None) -> str | None:
    vat = normalize_vat(partita_iva)
    if vat is None:
        return None
    if vat[:2].isalpha():
        return vat
    if isinstance(paese_iso, str):
        return f"{paese_iso}{vat}"
    return vat


def valida_partita_iva(partita_iva: str | None, paese_iso: str | None, vies_map: dict[str, str]) -> tuple[str, str | None]:
    vat = build_full_vat(partita_iva, paese_iso)
    if vat is None:
        return NON_APPLICABILE, None
    return vies_map.get(vat, INVALID), vat


def valida_clienti(clienti: pd.DataFrame, vies_map: dict[str, str]) -> pd.DataFrame:
    out = clienti.copy()
    risultati = [
        valida_partita_iva(piva, paese_iso, vies_map)
        for piva, paese_iso in zip(out["partita_iva"], out["paese_iso"])
    ]
    out["esito_iva"], out["partita_iva_completa"] = zip(*risultati)
    return out
