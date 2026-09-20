from __future__ import annotations

import pandas as pd

from matching import normalize_vat

VALID = "valid"
INVALID = "invalid"
ERROR = "error"
NON_SUPPORTATO = "non_supportato"
NON_APPLICABILE = "non_applicabile"  # cliente senza P.IVA (es. extra-UE)


def build_full_vat(partita_iva: str | None, paese_iso: str | None) -> str | None:
    # Se la P.IVA ha gia' il prefisso paese la lascia com'e'; se manca (es. "12345678903")
    # lo antepone usando il paese del cliente, per poterla cercare nel mock VIES.
    vat = normalize_vat(partita_iva)
    if vat is None:
        return None
    if vat[:2].isalpha():
        return vat
    if isinstance(paese_iso, str):
        return f"{paese_iso}{vat}"
    return vat


def valida_partita_iva(partita_iva: str | None, paese_iso: str | None, vies_map: dict[str, str]) -> tuple[str, str | None]:
    # Cerca la P.IVA completa nel mock VIES. Nessuna P.IVA -> non_applicabile (es. cliente
    # extra-UE). P.IVA assente dal mock -> invalid (il vero VIES non ha uno stato "non trovato").
    vat = build_full_vat(partita_iva, paese_iso)
    if vat is None:
        return NON_APPLICABILE, None
    return vies_map.get(vat, INVALID), vat


def valida_clienti(clienti: pd.DataFrame, vies_map: dict[str, str]) -> pd.DataFrame:
    # Applica valida_partita_iva a ogni cliente, aggiungendo le colonne esito_iva
    # e partita_iva_completa al DataFrame.
    out = clienti.copy()
    risultati = [
        valida_partita_iva(piva, paese_iso, vies_map)
        for piva, paese_iso in zip(out["partita_iva"], out["paese_iso"])
    ]
    out["esito_iva"], out["partita_iva_completa"] = zip(*risultati)
    return out
