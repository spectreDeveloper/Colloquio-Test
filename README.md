# Tool di riconciliazione clienti e fatture

Tool batch che associa le fatture ai clienti in anagrafica, valida le partite IVA (via mock VIES), converte gli importi in EUR e produce un report di riconciliazione per l'ufficio amministrazione.

## Requisiti

- Python 3.11+
- Connessione internet al primo utilizzo (per interrogare l'API [Frankfurter](https://frankfurter.dev/) e scaricare i dati paese di Babel/CLDR — dopo la prima esecuzione tutto viene messo in cache localmente in `cache/`, gitignorata, e le esecuzioni successive funzionano anche offline)

## Setup

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
```

## Esecuzione

```bash
python src/main.py
```

Di default legge i file da `data/` e scrive l'output in `output/`. Entrambi i percorsi sono configurabili:

```bash
python src/main.py --data-dir path/ai/dati --output-dir path/output
```

Il comando è idempotente: può essere rieseguito quante volte si vuole, l'output viene sempre sovrascritto per intero (scrittura atomica, mai un file a metà) e a parità di dati di input produce sempre lo stesso risultato.

## Output

- **`output/report.csv`** — una riga per fattura: cliente associato, esito validazione IVA, importo originale, tasso e importo in EUR, e un flag `affidabile` (`True`/`False`) con `motivi_flag` che spiega perché una riga non è affidabile.
- **`output/riepilogo.json`** — totali aggregati: numero di fatture affidabili/da verificare, totale EUR (solo sulle fatture affidabili), conteggio per esito IVA, elenco degli id da verificare, e i duplicati rilevati in anagrafica.

Vedi [`DECISIONI.md`](DECISIONI.md) per il ragionamento dietro ogni scelta.

## Test

```bash
pytest
```

I test non fanno mai chiamate di rete reali (l'accesso a Frankfurter è mockato).

## Struttura del progetto

```
data/       file di input (clienti.csv, fatture.csv, vies_mock.json)
src/        codice sorgente, un modulo per responsabilità
  main.py       orchestrazione della pipeline (entrypoint)
  country.py    normalizzazione paese (babel/CLDR + pycountry) e prefisso P.IVA
  matching.py   deduplica anagrafica + riconciliazione fattura-cliente
  vies.py       validazione P.IVA via mock VIES
  fx.py         parsing importi/date, conversione EUR, cache tassi di cambio
  report.py     costruzione report + riepilogo, scrittura output
tests/      test automatici (pytest)
output/     report generati (creata automaticamente)
cache/      cache locale (tassi di cambio, lookup paesi) — rigenerabile, gitignorata
```
