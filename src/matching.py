from __future__ import annotations

import re

import pandas as pd


def normalize_vat(vat: str | None) -> str | None:
    if not isinstance(vat, str) or not vat.strip():
        return None
    return re.sub(r"[\s.\-]", "", vat).upper()


def build_alias_map(clienti: pd.DataFrame) -> tuple[dict[str, str], list[dict]]:
    vat_norm = clienti["partita_iva"].map(normalize_vat)
    alias = {id_: id_ for id_ in clienti["id_cliente"]}
    duplicati = []

    for vat, gruppo in clienti.assign(_vat=vat_norm).groupby("_vat"):
        if vat is None or len(gruppo) < 2:
            continue
        ids_ordinati = sorted(gruppo["id_cliente"])
        canonico = ids_ordinati[0]
        for id_dup in ids_ordinati[1:]:
            alias[id_dup] = canonico
            duplicati.append({"canonico": canonico, "duplicato": id_dup, "partita_iva": vat})

    return alias, duplicati


def match_fatture(fatture: pd.DataFrame, alias: dict[str, str]) -> pd.DataFrame:
    out = fatture.copy()
    out["cliente_id_risolto"] = out["cliente_id"].map(alias)
    out["metodo_match"] = out["cliente_id_risolto"].map(lambda v: "id" if pd.notna(v) else "nessuno")
    return out
