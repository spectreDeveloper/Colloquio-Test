import json

import pandas as pd
import pytest

from country import country_from_vat_prefix, normalize_country
from fx import RateCache, _converti_riga, fetch_rate_to_eur, parse_amount, parse_date
from matching import build_alias_map, match_fatture, normalize_vat
from report import costruisci_report, costruisci_riepilogo
from vies import INVALID, NON_APPLICABILE, build_full_vat, valida_partita_iva


# --- country.py ---

def test_normalize_country_riconosce_varianti():
    assert normalize_country("Italia") == "IT"
    assert normalize_country("italy") == "IT"
    assert normalize_country("DE") == "DE"
    assert normalize_country("Deutschland") == "DE"
    assert normalize_country("España") == "ES"
    assert normalize_country("USA") == "US"


def test_normalize_country_vuoto_o_sconosciuto():
    assert normalize_country("") is None
    assert normalize_country(None) is None
    assert normalize_country("Narnia") is None


def test_country_from_vat_prefix():
    assert country_from_vat_prefix("ESB87654321") == "ES"
    assert country_from_vat_prefix("IT01234567890") == "IT"
    assert country_from_vat_prefix("XX12345") is None
    assert country_from_vat_prefix(None) is None


def test_country_from_vat_prefix_eccezione_grecia():
    assert country_from_vat_prefix("EL123456789") == "GR"


# --- matching.py ---

def test_normalize_vat():
    assert normalize_vat("IT 01234567.890") == "IT01234567890"
    assert normalize_vat(None) is None
    assert normalize_vat("") is None


def _clienti_df(rows):
    return pd.DataFrame(rows, columns=["id_cliente", "ragione_sociale", "partita_iva"])


def test_build_alias_map_unifica_duplicati_per_piva():
    clienti = _clienti_df(
        [
            ("C004", "Rossi SRL", "IT01234567890"),
            ("C001", "Rossi S.r.l.", "IT01234567890"),
            ("C002", "Bianchi SpA", "IT09876543210"),
        ]
    )
    alias, duplicati = build_alias_map(clienti)
    assert alias["C004"] == "C001"  # canonico = id alfabeticamente minore
    assert alias["C001"] == "C001"
    assert alias["C002"] == "C002"
    assert duplicati == [{"canonico": "C001", "duplicato": "C004", "partita_iva": "IT01234567890"}]


def test_build_alias_map_nessun_duplicato():
    clienti = _clienti_df([("C001", "Rossi", "IT01234567890"), ("C007", "Acme", None)])
    alias, duplicati = build_alias_map(clienti)
    assert alias == {"C001": "C001", "C007": "C007"}
    assert duplicati == []


def test_match_fatture_per_id_valido():
    alias = {"C001": "C001"}
    fatture = pd.DataFrame({"id_fattura": ["F1"], "cliente_id": ["C001"]})
    out = match_fatture(fatture, alias)
    assert out.loc[0, "cliente_id_risolto"] == "C001"
    assert out.loc[0, "metodo_match"] == "id"


def test_match_fatture_id_mancante_o_sconosciuto():
    alias = {"C001": "C001"}
    fatture = pd.DataFrame({"id_fattura": ["F1", "F2"], "cliente_id": [None, "C999"]})
    out = match_fatture(fatture, alias)
    assert list(out["metodo_match"]) == ["nessuno", "nessuno"]
    assert out["cliente_id_risolto"].isna().all()


# --- vies.py ---

def test_build_full_vat_con_prefisso_gia_presente():
    assert build_full_vat("IT01234567890", None) == "IT01234567890"


def test_build_full_vat_prefisso_mancante_inferito_da_paese():
    assert build_full_vat("12345678903", "IT") == "IT12345678903"


def test_build_full_vat_prefisso_mancante_senza_paese():
    assert build_full_vat("12345678903", None) == "12345678903"


def test_valida_partita_iva_esiti_dal_mock():
    vies_map = {"IT01234567890": "valid", "DE811234567": "error"}
    assert valida_partita_iva("IT01234567890", "IT", vies_map) == ("valid", "IT01234567890")
    assert valida_partita_iva("DE811234567", "DE", vies_map) == ("error", "DE811234567")


def test_valida_partita_iva_assente_dal_mock_e_invalid():
    vies_map = {"IT01234567890": "valid"}
    assert valida_partita_iva("IT00000000000", "IT", vies_map) == (INVALID, "IT00000000000")


def test_valida_partita_iva_cliente_senza_piva_e_non_applicabile():
    vies_map = {"IT01234567890": "valid"}
    esito, vat = valida_partita_iva(None, "US", vies_map)
    assert esito == NON_APPLICABILE
    assert vat is None


# --- fx.py ---

def test_parse_amount_formato_europeo_e_americano():
    assert parse_amount("1.234,56") == 1234.56
    assert parse_amount("1500.00") == 1500.0
    assert parse_amount("-500.00") == -500.0


def test_parse_amount_mancante_o_non_valido():
    assert parse_amount(None) is None
    assert parse_amount("") is None
    assert parse_amount("n/d") is None


def test_parse_date_valida_e_invalida():
    assert parse_date("2025-03-10") == "2025-03-10"
    assert parse_date("10/03/2025") is None
    assert parse_date(None) is None


def test_converti_riga_eur_diretto():
    tasso, fonte, eur, nota = _converti_riga(100.0, "EUR", "2025-03-10", None, cache=None)
    assert (tasso, fonte, eur, nota) == (1.0, "eur_diretto", 100.0, None)


def test_converti_riga_usd_con_tasso_contrattuale():
    tasso, fonte, eur, nota = _converti_riga(1000.0, "USD", "2025-03-10", 0.92, cache=None)
    assert (tasso, fonte, eur) == (0.92, "contrattuale", 920.0)


def test_converti_riga_importo_mancante():
    tasso, fonte, eur, nota = _converti_riga(None, "EUR", "2025-03-10", None, cache=None)
    assert eur is None
    assert "importo mancante" in nota


def test_converti_riga_valuta_mancante():
    tasso, fonte, eur, nota = _converti_riga(100.0, None, "2025-03-10", None, cache=None)
    assert eur is None
    assert "valuta mancante" in nota


def test_converti_riga_valuta_estera_senza_data():
    tasso, fonte, eur, nota = _converti_riga(100.0, "GBP", None, None, cache=None)
    assert eur is None
    assert "data_emissione" in nota


class _FakeResponse:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_fetch_rate_to_eur_usa_cache_e_non_richiama_la_rete_due_volte(tmp_path, monkeypatch):
    chiamate = []

    def fake_urlopen(req, timeout=10):
        chiamate.append(req.full_url)
        return _FakeResponse({"amount": 1.0, "base": "USD", "date": "2025-03-11", "rates": {"EUR": 0.9}})

    monkeypatch.setattr("fx.urllib.request.urlopen", fake_urlopen)
    cache = RateCache(tmp_path / "fx.json")

    tasso1, _ = fetch_rate_to_eur("USD", "2025-03-11", cache)
    tasso2, _ = fetch_rate_to_eur("USD", "2025-03-11", cache)

    assert tasso1 == 0.9
    assert tasso2 == 0.9
    assert len(chiamate) == 1


def test_fetch_rate_to_eur_valuta_non_supportata(tmp_path, monkeypatch):
    def fake_urlopen(req, timeout=10):
        return _FakeResponse({"amount": 1.0, "base": "AED", "date": "2025-03-11", "rates": {}})

    monkeypatch.setattr("fx.urllib.request.urlopen", fake_urlopen)
    cache = RateCache(tmp_path / "fx.json")

    tasso, nota = fetch_rate_to_eur("AED", "2025-03-11", cache)
    assert tasso is None
    assert "non supportata" in nota


def test_rate_cache_si_riprende_da_file_corrotto(tmp_path):
    path = tmp_path / "fx.json"
    path.write_text("{corrotto", encoding="utf-8")
    cache = RateCache(path)
    assert cache.get("USD", "2025-03-11") is None  # non esplode, riparte da cache vuota


# --- report.py ---

def _fattura_riga(**overrides):
    base = dict(
        id_fattura="F1",
        cliente_id="C001",
        cliente_id_risolto="C001",
        metodo_match="id",
        data_emissione="2025-03-10",
        valuta="EUR",
        importo=100.0,
        tasso_cambio=1.0,
        fonte_tasso="eur_diretto",
        importo_eur=100.0,
        nota_cambio=None,
    )
    base.update(overrides)
    return base


def _clienti_per_report():
    return pd.DataFrame(
        [{"id_cliente": "C001", "ragione_sociale": "Rossi", "partita_iva_completa": "IT01234567890", "esito_iva": "valid"}]
    )


def test_costruisci_report_riga_affidabile():
    fatture = pd.DataFrame([_fattura_riga()])
    report = costruisci_report(fatture, _clienti_per_report())
    assert report.loc[0, "affidabile"]
    assert report.loc[0, "motivi_flag"] == ""


def test_costruisci_report_nota_cambio_riportata_anche_se_affidabile():
    fatture = pd.DataFrame(
        [_fattura_riga(nota_cambio="tasso del 2025-06-13 (ultimo giorno lavorativo BCE disponibile prima del 2025-06-15)")]
    )
    report = costruisci_report(fatture, _clienti_per_report())
    assert report.loc[0, "affidabile"]
    assert "ultimo giorno lavorativo" in report.loc[0, "motivi_flag"]


def test_costruisci_report_cliente_non_identificato():
    fatture = pd.DataFrame(
        [_fattura_riga(cliente_id=None, cliente_id_risolto=None, metodo_match="nessuno")]
    )
    report = costruisci_report(fatture, _clienti_per_report())
    assert not report.loc[0, "affidabile"]
    assert "non riconciliata" in report.loc[0, "motivi_flag"]
    assert report.loc[0, "esito_iva"] == "cliente_non_identificato"


def test_costruisci_report_importo_negativo_flaggato_ma_calcolato():
    fatture = pd.DataFrame([_fattura_riga(importo=-500.0, importo_eur=-500.0)])
    report = costruisci_report(fatture, _clienti_per_report())
    assert not report.loc[0, "affidabile"]
    assert "importo negativo" in report.loc[0, "motivi_flag"]
    assert report.loc[0, "importo_eur"] == -500.0


def test_costruisci_report_segnala_doppia_registrazione_senza_escludere():
    fatture = pd.DataFrame(
        [_fattura_riga(id_fattura="F1"), _fattura_riga(id_fattura="F2")]
    )
    report = costruisci_report(fatture, _clienti_per_report())
    assert report["affidabile"].all()  # non diventa "non affidabile" solo per il duplicato
    assert "possibile doppia registrazione" in report.loc[0, "motivi_flag"]
    assert "possibile doppia registrazione" in report.loc[1, "motivi_flag"]


def test_costruisci_riepilogo():
    fatture = pd.DataFrame(
        [_fattura_riga(id_fattura="F1"), _fattura_riga(id_fattura="F2", importo=-10.0, importo_eur=-10.0)]
    )
    report = costruisci_report(fatture, _clienti_per_report())
    riepilogo = costruisci_riepilogo(report, duplicati_anagrafica=[{"canonico": "C001", "duplicato": "C004"}])
    assert riepilogo["totale_fatture"] == 2
    assert riepilogo["fatture_affidabili"] == 1
    assert riepilogo["fatture_da_verificare"] == 1
    assert riepilogo["id_fatture_da_verificare"] == ["F2"]
    assert riepilogo["duplicati_anagrafica_rilevati"] == [{"canonico": "C001", "duplicato": "C004"}]
