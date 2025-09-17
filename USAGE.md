# Guida all'uso di Patch GUI

Questa guida passo‑passo descrive il workflow tipico per applicare una patch con l'interfaccia grafica.

## Avvio dell'applicazione

1. Attiva l'ambiente virtuale (se usato):
   ```bash
   source .venv/bin/activate
   ```
2. Avvia la GUI (tramite entry point installato):
   ```bash
   patch-gui
   # oppure
   python -m patch_gui
   ```

   > La GUI richiede l'installazione con l'extra `gui` (`pip install .[gui]` oppure `pip install patch-gui[gui]`).

## Workflow dettagliato

1. **Seleziona la root del progetto**
   - Clicca su **Sfoglia** accanto al campo *Root progetto* e scegli la cartella che contiene i file da patchare.
   - Tutti i percorsi presenti nei diff verranno risolti relativamente a questa root.
2. **Carica il diff**
   - Usa **Apri .diff** per scegliere un file contenente il diff,
   - Oppure **Incolla da appunti**,
   - Oppure incolla manualmente il testo nel riquadro e clicca **Analizza testo diff**.
   - Sono supportati sia i diff standard di Git sia i blocchi `*** Begin Patch` / `*** Update File`.
3. **Analizza il diff**
   - Nel pannello sinistro vengono elencati i file e gli hunk trovati.
   - Selezionando un elemento puoi vedere il contesto e le modifiche.
4. **Configura l'esecuzione**
   - La modalità **Dry‑run** è abilitata di default e consente di simulare l'applicazione senza modificare i file.
   - Imposta la **Soglia fuzzy** (es. `0.85`) per controllare la tolleranza nel matching del contesto.
5. **Applica la patch**
   - Con Dry‑run attivo clicca **Applica patch** per vedere l'anteprima dei risultati.
   - Quando sei soddisfatto, disattiva Dry‑run e premi nuovamente **Applica patch** per modificare realmente i file.
   - Durante l'esecuzione la barra di stato mostra una barra di avanzamento numerica con la percentuale di file/hunk già elaborati.
6. **Gestisci eventuali ambiguità**
   - Se la patch può essere applicata in più punti plausibili, viene aperto un dialog che mostra tutte le opzioni con il relativo contesto.
   - Scegli manualmente il posizionamento corretto.
7. **Consulta backup e report**
   - Ogni esecuzione reale crea una cartella `~/.diff_backups/<timestamp-ms>/` con copie dei file originali (a meno di impostare un percorso diverso con `--backup`). Il suffisso `<timestamp-ms>` usa il formato `YYYYMMDD-HHMMSS-fff`, includendo i millisecondi per evitare collisioni.
   - I report `apply-report.json` e `apply-report.txt` vengono salvati in `~/.diff_backups/reports/results/<timestamp-ms>/`
     (anche in dry‑run, se non disattivati) per documentare l'esito della simulazione.
8. **Ripristina da backup**
   - Usa il pulsante **Ripristina da backup…** e seleziona il timestamp desiderato per ripristinare i file originali.

## Suggerimenti utili

- La soglia fuzzy più alta aumenta la precisione ma potrebbe non trovare patch leggermente disallineate.
- I file binari vengono ignorati automaticamente.
- Per diff molto grandi l'analisi può richiedere tempo; attendi il completamento prima di chiudere la finestra.

Per una panoramica delle opzioni tecniche e delle dipendenze consulta il [README](README.md).

## Suggerimento CLI: includere directory normalmente escluse

Quando usi la modalità `patch-gui apply`, per impostazione predefinita vengono ignorate directory come `.git`, `.venv`, `node_modules` e `.diff_backups`. Se devi patchare file posizionati lì dentro:

- aggiungi `--no-default-exclude` per disabilitare la lista automatica di esclusioni;
- opzionalmente specifica `--exclude-dir` più volte (o con valori separati da virgole) per costruire un elenco personalizzato di directory da ignorare.

Esempio:

```bash
patch-gui apply --root . --no-default-exclude fix.diff
```

## Gestione della configurazione via CLI

Oltre a usare la GUI, puoi ispezionare e modificare le impostazioni persistenti tramite il sottocomando `patch-gui config`:

- `patch-gui config show` stampa la configurazione corrente in formato JSON;
- `patch-gui config set <chiave> <valori…>` aggiorna un parametro (ad esempio `threshold`, `exclude_dirs`, `backup_base`, `log_level`);
- `patch-gui config reset [chiave]` ripristina un singolo valore o l'intera configurazione ai default.

Se vuoi operare su un file alternativo (per test o ambienti portabili) aggiungi `--config-path /percorso/custom/settings.toml` dopo il nome del sottocomando.
