from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from vies import ERROR, INVALID, NON_APPLICABILE, NON_SUPPORTATO, VALID

CLIENTE_NON_IDENTIFICATO = "cliente_non_identificato"

_ETICHETTE_IVA = {
    INVALID: "P.IVA non valida secondo VIES",
    ERROR: "VIES non ha risposto (errore/timeout) per questa P.IVA",
    NON_SUPPORTATO: "paese del cliente fuori dall'area coperta da VIES",
    CLIENTE_NON_IDENTIFICATO: "impossibile validare la P.IVA: cliente non identificato",
}


def _valuta_riga(row) -> tuple[bool, list[str]]:
    # Decide se una fattura e' "affidabile" controllando in ordine: matching, esito IVA,
    # data valida, importo EUR calcolabile, importo negativo. Ritorna (affidabile, motivi).
    motivi = []

    if row.metodo_match != "id":
        motivi.append("fattura non riconciliata con un cliente in anagrafica")

    if row.esito_iva not in (VALID, NON_APPLICABILE):
        motivi.append(_ETICHETTE_IVA.get(row.esito_iva, f"esito IVA non affidabile: {row.esito_iva}"))

    if pd.isna(row.data_emissione):
        motivi.append("data_emissione mancante o non valida")

    if pd.isna(row.importo_eur):
        dettaglio = f": {row.nota_cambio}" if pd.notna(row.nota_cambio) else ""
        motivi.append(f"importo in EUR non calcolabile{dettaglio}")
    elif row.importo < 0:
        motivi.append("importo negativo: verificare se e' una nota di credito")

    return len(motivi) == 0, motivi


def _segnala_note_cambio(out: pd.DataFrame) -> None:
    # Riporta la nota di conversione (es. "tasso preso dall'ultimo giorno lavorativo") anche
    # sulle righe gia' affidabili, come nota informativa: senza questo, l'informazione
    # esisterebbe solo internamente e non arriverebbe mai all'amministrazione.
    for idx, row in out.iterrows():
        if row["affidabile"] and pd.notna(row["nota_cambio"]):
            out.at[idx, "motivi_flag"].append(row["nota_cambio"])


def _segnala_doppie_registrazioni(out: pd.DataFrame) -> None:
    # Aggiunge una nota informativa alle fatture con stesso cliente/data/valuta/importo di
    # un'altra: non le esclude ne' le marca automaticamente inaffidabili, potrebbero essere
    # due fatture reali coincidenti - segnala solo, la decisione resta all'amministrazione.
    chiavi = ["cliente_id_risolto", "data_emissione", "valuta", "importo"]
    gruppi = out.dropna(subset=["cliente_id_risolto", "importo"]).groupby(chiavi)["id_fattura"]
    for _, id_fatture in gruppi:
        if len(id_fatture) < 2:
            continue
        for id_fattura in id_fatture:
            idx = out.index[out["id_fattura"] == id_fattura][0]
            altre = ", ".join(f for f in id_fatture if f != id_fattura)
            out.at[idx, "motivi_flag"].append(
                f"possibile doppia registrazione: stesso cliente/data/valuta/importo di {altre}"
            )


def costruisci_report(fatture: pd.DataFrame, clienti: pd.DataFrame) -> pd.DataFrame:
    # Unisce fatture + dati cliente (nome, P.IVA, esito IVA), calcola affidabile/motivi_flag
    # per ogni riga e aggiunge le segnalazioni di possibile doppia registrazione.
    info_cliente = clienti.set_index("id_cliente")[
        ["ragione_sociale", "partita_iva_completa", "esito_iva"]
    ]
    out = fatture.join(info_cliente, on="cliente_id_risolto")
    out["esito_iva"] = out["esito_iva"].fillna(CLIENTE_NON_IDENTIFICATO)

    risultati = [_valuta_riga(row) for row in out.itertuples()]
    out["affidabile"], out["motivi_flag"] = zip(*risultati)
    out["motivi_flag"] = [list(m) for m in out["motivi_flag"]]

    _segnala_note_cambio(out)
    _segnala_doppie_registrazioni(out)
    out["motivi_flag"] = out["motivi_flag"].map("; ".join)

    return out


def costruisci_riepilogo(report: pd.DataFrame, duplicati_anagrafica: list[dict] | None = None) -> dict:
    # Calcola i totali aggregati (fatture affidabili/da verificare, totale EUR, conteggi
    # per esito IVA) da mostrare in riepilogo.json.
    affidabili = report[report["affidabile"]]
    return {
        "totale_fatture": len(report),
        "fatture_affidabili": len(affidabili),
        "fatture_da_verificare": len(report) - len(affidabili),
        "totale_eur_fatture_affidabili": round(affidabili["importo_eur"].sum(), 2),
        "conteggio_per_esito_iva": report["esito_iva"].value_counts().to_dict(),
        "id_fatture_da_verificare": report.loc[~report["affidabile"], "id_fattura"].tolist(),
        "duplicati_anagrafica_rilevati": duplicati_anagrafica or [],
    }


_COLONNE_REPORT = [
    "id_fattura",
    "cliente_id",
    "cliente_id_risolto",
    "ragione_sociale",
    "metodo_match",
    "partita_iva_completa",
    "esito_iva",
    "data_emissione",
    "valuta",
    "importo",
    "tasso_cambio",
    "fonte_tasso",
    "importo_eur",
    "affidabile",
    "motivi_flag",
]


def scrivi_output(report: pd.DataFrame, riepilogo: dict, output_dir: Path) -> None:
    # Scrive report.csv e riepilogo.json con scrittura atomica (file temporaneo + rename),
    # cosi' un'interruzione a meta' non corrompe mai l'output di run precedenti.
    output_dir.mkdir(parents=True, exist_ok=True)

    report_path = output_dir / "report.csv"
    tmp = report_path.with_suffix(".csv.tmp")
    report[_COLONNE_REPORT].to_csv(tmp, index=False)
    tmp.replace(report_path)

    riepilogo_path = output_dir / "riepilogo.json"
    tmp_json = riepilogo_path.with_suffix(".json.tmp")
    tmp_json.write_text(json.dumps(riepilogo, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp_json.replace(riepilogo_path)
