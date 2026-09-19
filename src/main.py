
import argparse
import json
from pathlib import Path

import pandas as pd

from country import country_from_vat_prefix, normalize_country
from fx import converti_in_eur
from matching import build_alias_map, match_fatture
from report import costruisci_report, costruisci_riepilogo, scrivi_output
from vies import valida_clienti

ROOT = Path(__file__).resolve().parents[1]


def load_clienti_raw(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])

def load_fatture_raw(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])

def load_vies_mock(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return data.get("risposte", {})


def main() -> None:
    parser = argparse.ArgumentParser(description="Riconciliazione clienti/fatture")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output")
    args = parser.parse_args()

    clienti = load_clienti_raw(args.data_dir / "clienti.csv")
    fatture = load_fatture_raw(args.data_dir / "fatture.csv")
    vies_map = load_vies_mock(args.data_dir / "vies_mock.json")

    clienti["paese_iso"] = clienti["paese"].map(normalize_country)
    fallback = clienti["partita_iva"].map(country_from_vat_prefix)
    clienti["paese_iso"] = clienti["paese_iso"].fillna(fallback)

    alias, duplicati = build_alias_map(clienti)
    fatture = match_fatture(fatture, alias)
    clienti = valida_clienti(clienti, vies_map)
    fatture = converti_in_eur(fatture, clienti)

    report = costruisci_report(fatture, clienti)
    riepilogo = costruisci_riepilogo(report, duplicati)
    scrivi_output(report, riepilogo, args.output_dir)

    print(f"Fatture elaborate: {riepilogo['totale_fatture']}")
    print(f"  affidabili: {riepilogo['fatture_affidabili']}")
    print(f"  da verificare: {riepilogo['fatture_da_verificare']}")
    print(f"  totale EUR (solo affidabili): {riepilogo['totale_eur_fatture_affidabili']}")
    print(f"Report scritto in: {args.output_dir / 'report.csv'}")
    print(f"Riepilogo scritto in: {args.output_dir / 'riepilogo.json'}")


if __name__ == "__main__":
    main()
