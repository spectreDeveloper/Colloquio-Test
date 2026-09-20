from __future__ import annotations

import json
import unicodedata
from pathlib import Path

import pycountry
from babel import Locale, localedata

_CACHE_PATH = Path(__file__).resolve().parents[1] / "cache" / "country_lookup.json"
_VAT_PREFIX_EXCEPTIONS = {"EL": "GR"}  # la Grecia usa EL nei prefissi P.IVA, non GR
_VALID_ISO2 = {c.alpha_2 for c in pycountry.countries}

def _fold(text: str) -> str:
    # Normalizza una stringa per confronti tolleranti: minuscolo e senza accenti (es. "España" -> "espana").
    text = text.strip().lower()
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c))


def _build_lookup() -> dict[str, str]:
    # Costruisce la mappa nome/codice -> ISO2 da babel (nomi paese in ~1100 lingue/locale)
    # e da pycountry (codici alpha-2/alpha-3 e nomi ufficiali inglesi).
    lookup: dict[str, str] = {}
    for locale_id in localedata.locale_identifiers():
        try:
            locale = Locale.parse(locale_id)
        except Exception:
            continue
        for code, name in locale.territories.items():
            if len(code) == 2 and code.isalpha():
                lookup.setdefault(_fold(name), code.upper())
    for country in pycountry.countries:
        lookup.setdefault(_fold(country.alpha_2), country.alpha_2)
        lookup.setdefault(_fold(country.alpha_3), country.alpha_2)
        lookup.setdefault(_fold(country.name), country.alpha_2)
        if hasattr(country, "official_name"):
            lookup.setdefault(_fold(country.official_name), country.alpha_2)
    return lookup


def _load_lookup() -> dict[str, str]:
    # Legge la mappa dalla cache su disco se esiste ed e' valida; altrimenti la ricostruisce
    # (costosa, ~1 secondo) e la salva per i run successivi, con scrittura atomica.
    if _CACHE_PATH.exists():
        try:
            return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass  # cache corrotta (es. scrittura interrotta): la ricostruiamo
    lookup = _build_lookup()  # ~1100 locale CLDR: costoso, per questo va in cache
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _CACHE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(lookup, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_CACHE_PATH)
    return lookup

_LOOKUP = _load_lookup()

def normalize_country(paese: str | None) -> str | None:
    # Converte un nome paese scritto a mano (qualsiasi lingua/formato) nel codice ISO2.
    # Ritorna None se vuoto o non riconosciuto (mai un codice inventato).
    if not isinstance(paese, str) or not paese.strip():
        return None
    return _LOOKUP.get(_fold(paese))

def country_from_vat_prefix(partita_iva: str | None) -> str | None:
    # Ricava il paese dalle prime due lettere della P.IVA (es. "ESB87654321" -> "ES"),
    # gestendo l'eccezione greca. Ritorna None se il prefisso non e' un codice ISO valido.
    if not isinstance(partita_iva, str):
        return None
    prefix = partita_iva.strip().upper()[:2]
    prefix = _VAT_PREFIX_EXCEPTIONS.get(prefix, prefix)
    return prefix if prefix in _VALID_ISO2 else None
