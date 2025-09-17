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
   - Ogni esecuzione reale crea una cartella `~/.diff_backups/<timestamp>/` con copie dei file originali (a meno di impostare un percorso diverso con `--backup`).
   - I report `apply-report.json` e `apply-report.txt` vengono salvati in `patch_gui/reports/results/<timestamp>/`
     accanto all'applicazione (anche in dry‑run, se non disattivati) per documentare l'esito della simulazione.
8. **Ripristina da backup**
   - Usa il pulsante **Ripristina da backup…** e seleziona il timestamp desiderato per ripristinare i file originali.

## Suggerimenti utili

- La soglia fuzzy più alta aumenta la precisione ma potrebbe non trovare patch leggermente disallineate.
- I file binari vengono ignorati automaticamente.
- Per diff molto grandi l'analisi può richiedere tempo; attendi il completamento prima di chiudere la finestra.

Per una panoramica delle opzioni tecniche e delle dipendenze consulta il [README](README.md).
