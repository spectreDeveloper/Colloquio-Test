# Decisioni

Diario delle ambiguità incontrate, come le ho risolte e perché. Dove rilevante indico anche cosa ho scartato e perché, e cosa farei con più tempo.

## Riconciliazione fattura → cliente

**Uso solo `cliente_id`, niente fallback sul nome.** Inizialmente avevo previsto un fallback: se `cliente_id` manca o non esiste in anagrafica, provare a matchare `cliente_nome` normalizzato contro `ragione_sociale`. Ci ho ripensato: il nome è un campo scritto a mano, e usarlo per decidere in automatico a quale cliente attribuire una fattura è un rischio di business (attribuzione economica sbagliata) che non vale il recupero di un paio di fatture su 28. Le fatture con `cliente_id` mancante o inesistente (`F0007`, `F0008`, `F0009` in questo dataset) restano esplicitamente **non riconciliate**, con motivo in chiaro nel report, per revisione umana.

**Con più tempo:** una coda di revisione con suggerimento (non applicazione automatica) del match più probabile per nome, che un umano approva o rifiuta.

## Anagrafica duplicata (stessa P.IVA, id diversi)

`C001` "Rossi S.r.l." e `C004` "Rossi SRL" hanno la stessa P.IVA. Li rilevo raggruppando per P.IVA normalizzata in `build_alias_map` e scelgo come "canonico" l'id alfabeticamente minore (criterio arbitrario ma deterministico). Il duplicato viene **segnalato** in `riepilogo.json` (`duplicati_anagrafica_rilevati`), così l'amministrazione può sistemare l'anagrafica a monte.

`build_alias_map` produce un'unica mappa `alias: id_originale → id_canonico` che copre *tutti* gli id, compresi quelli duplicati (`alias["C004"] == "C001"`). Questa stessa mappa è quella che `match_fatture` usa per risolvere `cliente_id`. Di conseguenza **la deduplica funziona automaticamente anche per il matching delle fatture**: una fattura con `cliente_id="C004"` si risolverebbe correttamente a `C001` (verificato con un test manuale), anche se nessuna fattura di questo dataset esercita davvero questo caso.

*(Nota: in una versione precedente di questo documento avevo scritto che questo caso non fosse gestito e servisse un intervento futuro. Non era corretto — l'ho verificato con un test ad-hoc e corretto qui. Lo lascio annotato perché è il tipo di errore — descrivere il codice a memoria invece di verificarlo — su cui voglio restare vigile.)*

## Normalizzazione paese

Ho scartato due librerie prima di arrivare alla soluzione finale:

- `country_converter`: comodo ma non riconosce endonimi come "Deutschland" o "España" — mi avrebbe comunque costretto a un'eccezione scritta a mano.
- `countrynames`: dipende da **PyICU**, che richiede la libreria nativa ICU compilata sul sistema — installazione fragile su Windows, non voglio rischiare la consegna per una libreria che potrebbe non installarsi sulla macchina di chi valuta.

**Soluzione adottata:** `babel` (nomi ufficiali dei territori da CLDR, in tutti i ~1100 locale disponibili, non una lista di lingue scelta da me) + `pycountry` (codici ISO 3166-1 alpha-2/alpha-3, serve per "USA", che è un codice alpha-3, non un nome). Nessun dizionario nome-per-nome scritto a mano. L'unica eccezione codificata esplicitamente è quella imposta dallo standard stesso: i prefissi P.IVA usano `EL` per la Grecia invece di `GR`.

Costruire la mappa da tutti i locale CLDR costa ~1 secondo la prima volta: la metto in cache su disco (`cache/country_lookup.json`) per non rifarlo ad ogni run.

**Limite noto:** nomi gergali non ufficiali in nessuna lingua (es. "Olanda" per Paesi Bassi) non sono coperti da nessuno standard e quindi non riconosciuti — non compaiono nei dati forniti, quindi non li ho gestiti.

**Fallback dal prefisso P.IVA:** se `paese` è vuoto o non normalizzabile (caso `C012`), provo a ricavare il paese dalle prime due lettere della P.IVA (es. `ESB87654321` → `ES`), verificando che siano un codice ISO valido. Il campo `paese` ha comunque sempre precedenza quando presente e riconoscibile: è il dato "primario" dichiarato, la P.IVA è un indizio secondario.

## Validazione P.IVA (mock VIES)

Ho introdotto un esito oltre ai quattro documentati nel mock (`valid`, `invalid`, `error`, `non_supportato`):

- **`non_applicabile`** — il cliente non ha affatto una P.IVA (es. `C007`, USA, extra-UE). Non è un'anomalia: per questi clienti VIES semplicemente non si applica, quindi non li tratto come "da verificare".

**P.IVA assente dalla mappa del mock → trattata come `invalid`.** Il mock dice "decidi tu come interpretarla"; inizialmente avevo introdotto un terzo esito dedicato (`non_trovata`, "da verificare, non presumo nulla"), poi sono tornato indietro. Due motivi: (1) il vero servizio VIES non ha un esito "non trovato" — restituisce solo un booleano valido/non valido, quindi una chiave assente dal mock rappresenta più realisticamente "una P.IVA che nella realtà risulterebbe non valida" che non un vero terzo stato; (2) prima del lookup normalizzo già il formato e completo il prefisso paese mancante, quindi le cause tecniche più comuni di un mancato match sono già escluse a monte — un mancato match residuo, dopo questa pulizia, è un segnale abbastanza forte di P.IVA davvero inesistente. In questo dataset nessuna P.IVA cade in questo caso, quindi la scelta non cambia alcun numero nel report — ma semplifica la gestione dei casi limite (un esito in meno da spiegare e da tracciare nel report).

Quando la P.IVA in anagrafica manca del prefisso paese (`C008`, `12345678903`), lo antepongo usando `paese_iso` del cliente prima di interrogare il mock.

## Conversione valuta

- **EUR**: nessuna conversione, tasso 1.0.
- **USD con `tasso_usd_contrattuale`** (`C007`, `C014`): tasso fisso applicato a **tutte** le fatture USD di quel cliente, a prescindere dalla data — come richiesto dalla nota operativa. Il contratto si applica solo a USD: una fattura EUR dello stesso cliente (`F0015`) non lo usa.
- **Tutte le altre combinazioni**: tasso BCE storico del giorno di emissione via API pubblica [Frankfurter](https://frankfurter.dev/). Quando la data cade in un giorno non lavorativo, Frankfurter risponde con l'ultimo tasso pubblicato disponibile: lo tratto come corretto (è il comportamento reale della BCE) e lo segnalo comunque in una nota, per trasparenza.
- **Valute non supportate** (`AED`, `F0016`): Frankfurter risponde 404. Non forzo alcuna conversione, la fattura resta senza `importo_eur` e viene segnalata.

I tassi vengono cachati su disco (`cache/fx_rates.json`) per idempotenza (stesso input → stesso output anche offline dopo il primo run) e per non martellare l'API ad ogni riesecuzione.

## Importi

Parsing sia del formato europeo (`1.234,56`) che anglosassone (`1500.00`) via regex, senza tentativi "creativi" su formati ambigui: se non riconosco il formato con sicurezza, l'importo resta mancante (meglio segnalare che indovinare).

**Importi negativi** (`F0017`, `-500.00`): li converto comunque (potrebbe essere una legittima nota di credito), ma flaggo la riga come da verificare — non spetta al tool decidere se è un errore o un'operazione voluta.

**Importo o valuta mancante** (`F0024`, `F0025`): interrotti subito con un motivo specifico, senza tentare comunque una chiamata all'API di cambio (bug che ho trovato e corretto in corso d'opera, vedi sotto).

## Fatture duplicate (stesso cliente/data/valuta/importo)

`F0001` e `F0027` hanno cliente, data, valuta e importo identici. **Non le tratto come lo stesso evento**: due fatture reali potrebbero legittimamente coincidere su questi campi. Le conteggio entrambe nei totali e le segnalo con una nota informativa ("possibile doppia registrazione"), senza escluderle né marcarle "non affidabili" — sono due decisioni diverse (il numero è corretto, ma l'amministrazione dovrebbe controllare se sono davvero due fatture distinte).

## Idempotenza

- `report.csv` e `riepilogo.json` vengono scritti su file temporaneo e poi rinominati (`Path.replace`, atomico): un'interruzione a metà non lascia mai un output corrotto o parziale, il file precedente resta valido finché il nuovo non è completo.
- Le cache locali (`cache/fx_rates.json`, `cache/country_lookup.json`) inizialmente scrivevano senza questa atomicità — l'ho corretto dopo essermene accorto, con lo stesso pattern, più un fallback che ricostruisce la cache se il JSON risulta illeggibile invece di far crashare il tool.
- Verificato empiricamente: run ripetuti sugli stessi dati producono output byte-per-byte identico, nessuna crescita/duplicazione.

## Formato del report

**CSV per il dettaglio** (`report.csv`): l'ufficio amministrazione lavora quasi certamente in Excel/Fogli Google, un CSV si apre e si filtra senza attrito. **JSON per il riepilogo** (`riepilogo.json`): pochi valori aggregati, più comodo da consumare anche in modo programmatico (es. un controllo automatico "se `fatture_da_verificare > 0`, manda un avviso").

Ogni riga del report ha un flag `affidabile` booleano e `motivi_flag` con il motivo in chiaro (concatenato se sono più di uno) — l'idea è che l'amministrazione possa ordinare/filtrare su `affidabile` e sapere subito cosa e perché controllare, senza dover incrociare più fonti.

## Bug trovati e corretti durante lo sviluppo

- **`pandas.Series.map()` converte i `None` restituiti in `NaN` (float)** quando la colonna è di tipo `object`. Mi ha rotto più di un controllo scritto come `if valore is None` / `if valore:` (silenziosamente falso su `NaN`, che in Python è truthy) — successo sia nella normalizzazione valuta sia nella conversione cambio (una fattura con valuta mancante ha provato a chiamare Frankfurter con `valuta="nan"`, ottenendo un 404 invece del motivo corretto "valuta mancante"). Corretto sostituendo con `pd.isna()` / `isinstance(v, str)` ovunque.
- **Frankfurter rifiutava le richieste con 403** perché blocca lo User-Agent di default di `urllib`. Risolto con un header esplicito.
- **I duplicati anagrafica venivano calcolati ma mai scritti nel report** — bug di integrazione, l'ho trovato rileggendo `main.py` prima di scrivere questa documentazione e l'ho corretto (ora sono in `riepilogo.json`).
- `requests` era in `requirements.txt` ma non veniva mai importato (uso `urllib` nello standard library) — dipendenza morta, rimossa.
- **Errore in questo stesso documento**: avevo scritto che il caso "fattura che referenzia direttamente un id anagrafica duplicato" non fosse gestito. L'ho verificato con un test manuale invece di fidarmi della mia descrizione a memoria: è già gestito correttamente da `build_alias_map` + `match_fatture`. Corretto sopra, nella sezione "Anagrafica duplicata".

## Cosa ho lasciato fuori per limiti di tempo

- **Retry/backoff sulle chiamate a Frankfurter**: un errore di rete transitorio viene trattato uguale a una valuta davvero non supportata (stesso messaggio "errore chiamata Frankfurter"). Con più tempo distinguerei errori temporanei (ritentabili) da errori permanenti (404 su valuta sconosciuta).
- **Validazione del formato/checksum della P.IVA** prima di interrogare VIES: mi affido interamente al verdetto del mock. Un'implementazione reale potrebbe scartare a monte i formati palesemente invalidi.
- **CI automatica**: i test girano solo in locale (`pytest`), nessuna pipeline configurata.
