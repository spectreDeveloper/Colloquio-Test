# Decisioni

*Nota: i contenuti e le decisioni di questo documento sono miei; mi sono fatto aiutare da Claude a riformulare il testo per renderlo più chiaro e leggibile.*

## Caricamento dati

Ho iniziato il progetto usando pandas per caricare i CSV. Carico i dati in formato stringa, essendo sporchi è meglio non usare l'auto-detection.

## Normalizzazione paese

Per il primo step, ovvero i paesi sporchi, ho scelto di utilizzare due librerie in combinazione (`babel` e `pycountry`) per determinare lo standard corretto del paese, con fallback sulla partita IVA — per norma europea è strettamente legata al paese dell'azienda, con eccezione della Grecia che usa `EL` come formato.

## Matching e duplicati anagrafica

Per il matching ho utilizzato solo il `cliente_id`, perché è l'unico dato realmente sicuro per determinare un vero cliente. Avrei potuto utilizzare il nome cliente, ma non è un dato sicuro e quindi ho preferito segnalarlo come non valido.

Per quanto riguarda la duplicazione dei clienti, ho utilizzato la partita IVA per determinarla, e una volta raggruppati scelgo il primo in ordine alfabetico.

## Validazione P.IVA

Ho inoltre aggiunto un controllo per completare la partita IVA, quindi aggiungere il paese sfruttando la logica dello step 1 — essendo già pulito e corretto, posso sfruttarlo per validare la P.IVA.

Per le P.IVA che non risultano proprio nel mock, ho deciso di trattarle come non valide invece di inventare uno stato a parte tipo "non trovata". Il vero VIES funziona così: o è valida o non lo è, non esiste un "non so risponderti". E dato che prima del controllo ho già ripulito il formato e completato il paese quando mancava, se dopo tutto questo una P.IVA ancora non combacia con niente, per me è più corretto considerarla non valida che lasciarla in un limbo.

## Cambio valuta

Per il cambio valuta ho usato un'API dove necessaria, quindi per valute non EUR. Per EUR ho utilizzato un tasso standard di uno; per le altre ho utilizzato l'API di Frankfurter con la data della fattura, per avere un dato reale.

C'è anche un terzo caso, con priorità sull'API: se la valuta è USD e il cliente ha un `tasso_usd_contrattuale` in anagrafica, uso quel tasso fisso, a prescindere dalla data della fattura — niente chiamata API in questo caso, perché il tasso è un accordo commerciale concordato col cliente, non un valore che dipende dal giorno.

Nel dataset c'è anche una fattura in una valuta che l'API non gestisce (AED). In quel caso non invento nessun tasso: lascio l'importo in EUR vuoto e segnalo la fattura, perché un numero sbagliato in un report finanziario è peggio di un numero mancante. Stessa logica per le fatture con importo o valuta mancanti nel file originale: mi fermo subito e segnalo il motivo, invece di provare comunque a calcolare qualcosa.

## Affidabilità del report

Per ogni fattura calcolo un flag `affidabile` (sì/no) controllando: se è stata riconciliata con un cliente, se la P.IVA del cliente è valida (o non applicabile), se importo/data/valuta sono presenti e interpretabili, se l'importo è negativo. Una fattura "non affidabile" **non viene esclusa dal report** — resta visibile con l'importo calcolato quando possibile e il motivo in chiaro, perché il report deve far sapere all'amministrazione dove intervenire, non nascondere il problema.

## Fatture duplicate

Due fatture (F0001 e F0027) hanno stesso cliente, data, valuta e importo. Non le tratto come lo stesso evento: potrebbero essere due fatture reali coincidenti. Le conteggio entrambe e le segnalo con una nota informativa, senza escluderle né marcarle automaticamente come non affidabili.

## Formato del report

Esporto in CSV il dettaglio (`report.csv`), per rendere facile l'analisi a un operatore umano. Esporto in JSON il riepilogo (`riepilogo.json`), pensando a un'eventuale futura implementazione macchina (un altro programma che legge i totali e agisce di conseguenza, senza dover parsare un CSV).

## Cosa ho lasciato fuori per limiti di tempo

- **Una vera integrazione con l'API VIES**, al posto del mock.
- **Una dashboard o una UI locale** per rendere più semplice l'utilizzo del tool a un operatore non tecnico, invece del solo output su file.
- **Un'API locale** per poter integrare il tool in un eventuale gestionale esistente, invece del solo utilizzo da riga di comando.
