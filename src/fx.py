from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

import pandas as pd

FRANKFURTER_URL = "https://api.frankfurter.dev/v1/{date}?base={valuta}&symbols=EUR"
CACHE_PATH = Path(__file__).resolve().parents[1] / "cache" / "fx_rates.json"

_AMOUNT_RE_EU = re.compile(r"^-?\d{1,3}(\.\d{3})*(,\d+)?$")
_AMOUNT_RE_US = re.compile(r"^-?\d{1,3}(,\d{3})*(\.\d+)?$")


def parse_amount(raw: str | None) -> float | None:
    # Converte un importo in formato europeo ("1.234,56") o anglosassone ("1500.00") in float.
    # Ritorna None se vuoto o non riconoscibile con sicurezza (mai un tentativo "creativo").
    if not isinstance(raw, str) or not raw.strip():
        return None
    raw = raw.strip()
    if _AMOUNT_RE_EU.match(raw) and "," in raw:
        cleaned = raw.replace(".", "").replace(",", ".")
    elif _AMOUNT_RE_US.match(raw):
        cleaned = raw.replace(",", "")
    else:
        cleaned = raw
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_date(raw: str | None) -> str | None:
    # Valida che la data sia in formato YYYY-MM-DD. Ritorna None se mancante o malformata.
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        datetime.strptime(raw.strip(), "%Y-%m-%d")
    except ValueError:
        return None
    return raw.strip()


class RateCache:
    # Cache su disco dei tassi di cambio, chiave "valuta_data" (il tasso dipende da entrambi:
    # e' storico, cambia giorno per giorno). Garantisce idempotenza e riduce le chiamate API.
    def __init__(self, path: Path = CACHE_PATH):
        self.path = path
        try:
            self._data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except json.JSONDecodeError:
            self._data = {}  # cache corrotta (es. scrittura interrotta): la ricostruiamo

    def get(self, valuta: str, data: str) -> dict | None:
        return self._data.get(f"{valuta}_{data}")

    def set(self, valuta: str, data: str, entry: dict) -> None:
        # Scrittura atomica (file temporaneo + rename): un'interruzione a meta' non corrompe la cache.
        self._data[f"{valuta}_{data}"] = entry
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        tmp.replace(self.path)


def fetch_rate_to_eur(valuta: str, data: str, cache: RateCache) -> tuple[float | None, str | None]:
    # Recupera (da cache o dall'API Frankfurter) il tasso BCE storico valuta->EUR per quella data.
    # Se la data cade in un giorno non lavorativo, Frankfurter risponde con l'ultimo tasso
    # disponibile: lo segnaliamo in una nota, senza considerarlo un errore.
    cached = cache.get(valuta, data)
    if cached is not None:
        return cached["tasso"], cached.get("nota")

    url = FRANKFURTER_URL.format(date=data, valuta=valuta)
    req = urllib.request.Request(url, headers={"User-Agent": "colloquio-test-reconcile/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError) as exc:
        nota = f"errore chiamata Frankfurter: {exc}"
        cache.set(valuta, data, {"tasso": None, "nota": nota})
        return None, nota

    rate = (payload.get("rates") or {}).get("EUR")
    nota = None
    if rate is None:
        nota = f"valuta {valuta} non supportata da Frankfurter/BCE"
    else:
        data_effettiva = payload.get("date")
        if data_effettiva and data_effettiva != data:
            nota = f"tasso del {data_effettiva} (ultimo giorno lavorativo BCE disponibile prima del {data})"

    cache.set(valuta, data, {"tasso": rate, "nota": nota})
    return rate, nota


def _converti_riga(importo, valuta, data, tasso_contrattuale, cache):
    # Le tre regole di conversione, in ordine di priorita': EUR diretto -> tasso contrattuale
    # fisso (se USD e il cliente ne ha uno) -> tasso BCE storico via API per tutto il resto.
    if pd.isna(importo):
        return None, None, None, "importo mancante o non interpretabile"
    if pd.isna(valuta):
        return None, None, None, "valuta mancante"
    if valuta == "EUR":
        return 1.0, "eur_diretto", importo, None
    if valuta == "USD" and pd.notna(tasso_contrattuale):
        tasso = tasso_contrattuale
        return tasso, "contrattuale", round(importo * tasso, 2), None
    if pd.isna(data):
        return None, None, None, "data_emissione mancante o non valida: impossibile recuperare il tasso di cambio"

    tasso, nota = fetch_rate_to_eur(valuta, data, cache)
    importo_eur = round(importo * tasso, 2) if tasso is not None else None
    return tasso, "bce", importo_eur, nota


def converti_in_eur(fatture: pd.DataFrame, clienti: pd.DataFrame) -> pd.DataFrame:
    # Pulisce importo/data/valuta delle fatture, poi applica _converti_riga a ognuna,
    # aggiungendo tasso_cambio, fonte_tasso, importo_eur e nota_cambio.
    out = fatture.copy()
    out["importo"] = out["importo"].map(parse_amount)
    out["data_emissione"] = out["data_emissione"].map(parse_date)
    out["valuta"] = out["valuta"].map(lambda v: v.strip().upper() if isinstance(v, str) and v.strip() else None)

    tasso_per_cliente = pd.to_numeric(
        clienti.set_index("id_cliente")["tasso_usd_contrattuale"], errors="coerce"
    )
    cache = RateCache()

    risultati = [
        _converti_riga(
            row.importo,
            row.valuta,
            row.data_emissione,
            tasso_per_cliente.get(row.cliente_id_risolto),
            cache,
        )
        for row in out.itertuples()
    ]
    out["tasso_cambio"], out["fonte_tasso"], out["importo_eur"], out["nota_cambio"] = zip(*risultati)
    return out
