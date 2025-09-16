# Patch GUI – Diff Applier (PySide6)

Applicazione desktop (GUI) in **Python + PySide6/Qt** per applicare patch **unified diff** (anche `*** Begin Patch` / `*** Update File`) a file di progetto.

Caratteristiche principali:

* Caricamento da **file**, **clipboard** o **textarea**
* Ricerca ricorsiva dei file target
* Modalità **dry‑run** con anteprima
* Matching **esatto → fuzzy** con soglia configurabile
* Risoluzione **interattiva** delle ambiguità
* **Backup** automatici e **report** dettagliati
* Modalità **CLI** (`patch-gui apply`) con opzioni `--dry-run`, `--threshold`, `--backup`

---

## Indice

* [Requisiti](#requisiti)
* [Installazione](#installazione-consigliata-con-virtualenv)
* [Avvio rapido](#avvio-rapido)
* [Guida all'uso](#guida-alluso)
* [Opzioni/Dettagli tecnici](#opzionidettagli-tecnici)
* [Risoluzione problemi](#risoluzione-problemi)
* [Struttura backup/report](#struttura-backupreport)
* [Note](#note)
* [Licenza](#licenza)

## Requisiti

* **WSL Ubuntu** (consigliato; funziona anche su Linux nativo/macOS)
* **Python 3.10+**
* Dipendenze Python testate: **PySide6 6.7.3**, **unidiff 0.7.5** (vedi [Manutenzione dipendenze](#manutenzione-dipendenze))
* **WSLg** abilitato (per mostrare la GUI Qt su Windows 11/10 21H2+)

Pacchetti di sistema utili su Ubuntu/WSL:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git \
                    libgl1 libegl1 libxkbcommon-x11-0 libxcb-xinerama0
```

> I pacchetti `libgl1`/`libegl1`/`libxkbcommon-x11-0`/`libxcb-xinerama0` risolvono i tipici errori Qt (plugin `xcb`) in ambienti WSL.

---

## Installazione (consigliata con virtualenv)

Nella root del progetto:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install .
```

> Il comando `pip install .` usa il `pyproject.toml` del progetto per installare automaticamente dipendenze e entry point CLI.

### VS Code – selezione interprete (WSL)

1. Apri la cartella del progetto **dentro WSL** (`code .`).
2. `Ctrl+Shift+P` → **Python: Select Interpreter** → scegli `.venv/bin/python`.
3. (Consigliato) Aggiungi `.vscode/settings.json`:

```json
{
  "python.defaultInterpreterPath": ".venv/bin/python",
  "python.analysis.typeCheckingMode": "basic",
  "cSpell.language": "en,it",
  "cSpell.words": ["hunk", "fuzzy", "dry-run", "ripristino", "anteprima", "PySide6", "unidiff", "WSLg"]
}
```

> Se il pulsante **Run** di VS Code continua a usare `/usr/bin/env python3`, verifica che l’estensione/runner sia configurata per usare l’interprete selezionato o lancia lo script da terminale con l’ambiente attivato.

---

## Avvio rapido

```bash
source .venv/bin/activate
patch-gui
# oppure
python -m patch_gui
```

### Modalità CLI (senza GUI)

```bash
patch-gui apply --root /percorso/al/progetto diff.patch
# oppure
python -m patch_gui apply --root /percorso/al/progetto diff.patch

# Esempi di opzioni
patch-gui apply --root . --dry-run --threshold 0.90 diff.patch
git diff | patch-gui apply --root . --backup ~/diff_backups -
```

* `--dry-run` esegue solo l'analisi lasciando i file invariati.
* `--threshold` imposta la soglia fuzzy (default 0.85).
* `--backup` permette di scegliere la cartella base dei backup (di default `<root>/.diff_backups`).
* L'uscita riassume i risultati e restituisce codice `0` solo se tutti gli hunk vengono applicati.

---

## Test

Per eseguire la suite automatizzata del progetto:

```bash
pytest
```

---

## Guida all'uso

1. **Root progetto** → seleziona la cartella base: i percorsi nei diff saranno risolti relativamente a questa root.
2. **Carica diff**:

   * **Apri .diff** (file), oppure **Incolla da appunti**, oppure incolla nel riquadro e clicca **Analizza testo diff**.
   * Supporta: unified diff standard (`git diff`, `git format-patch`) e blocchi `*** Begin Patch` del tipo:

     ```
     *** Begin Patch
     *** Update File: path/file.js
     @@
     -linea vecchia
     +linea nuova
     *** End Patch
     ```
3. **Analizza diff**: nel pannello sinistro compaiono i file e gli hunk.
4. **Dry‑run** (default abilitato): imposta la **Soglia fuzzy** (es. 0.85) e clicca **Applica patch** per simulare.
5. **Applica realmente**: disabilita Dry‑run → **Applica patch**.

   * Matching: **esatto** → **fuzzy**.
   * **Ambiguità**: se esistono più posizioni plausibili, si apre un dialog con **tutte** le opzioni e contesto; scegli manualmente.
   * File mancanti: se non trovati sotto la root, **vengono saltati** (come da preferenza).
6. **Backup & Report**: ogni run reale crea `./.diff_backups/<timestamp>/` con copie originali e genera:

   * `apply-report.json` (strutturato),
   * `apply-report.txt` (leggibile).
7. **Ripristino**: pulsante **Ripristina da backup…** → seleziona il timestamp → i file vengono ripristinati.
Per una guida passo-passo con esempi consulta [USAGE.md](USAGE.md).

---

## Opzioni/Dettagli tecnici

* **Soglia fuzzy**: regola la tolleranza nel confronto del contesto (Algorithm: `difflib.SequenceMatcher`).
* **EOL**: preserva lo stile originale del file (LF/CRLF) al salvataggio.
* **Ricerca file**: tenta prima il percorso relativo esatto (ripulendo prefissi `a/`/`b/`), altrimenti ricerca **per nome** in modo ricorsivo; in caso di multipli chiede quale usare.
* **Formati supportati**: file di testo in generale (JS, TS, HTML, CSS, MD, Rust, …).

---

## Risoluzione problemi

### `ModuleNotFoundError: No module named 'unidiff'`

* Assicurati di aver **attivato il virtualenv** prima di lanciare:

  ```bash
  source .venv/bin/activate
  python -c "import sys; print(sys.executable)"
  pip show unidiff
  ```

  Se `pip show` non trova il pacchetto:

  ```bash
  pip install unidiff
  ```
* In **VS Code**, seleziona l’interprete `.venv/bin/python` (vedi sopra). Se il runner usa ancora `/usr/bin/env python3`, esegui dallo **Integrated Terminal** con venv attivo.

### Errori Qt (plugin `xcb`, display, ecc.) su WSL

* Installa i pacchetti di sistema elencati in **Requisiti**.
* Verifica che **WSLg** sia attivo (su Windows 11 lo è di default). In ambienti senza WSLg puoi usare un X‑Server esterno, ma non è consigliato.

### Avvisi Pylance/typing

* Il progetto è già tipizzato per ridurre i warning. Se desideri modalità più permissiva:

  ```jsonc
  // .vscode/settings.json
  {
    "python.analysis.typeCheckingMode": "basic"
  }
  ```
* In caso di falsi positivi su librerie senza type stubs (es. `unidiff`), il codice usa annotazioni conservative (`Any`) dove necessario.

### Code Spell Checker (cSpell) e testo in italiano

Aggiungi l’italiano e alcune parole tecniche:

```json
{
  "cSpell.language": "en,it",
  "cSpell.words": ["hunk", "ripristino", "anteprima", "ricorsiva", "similarità", "WSLg", "PySide6", "unidiff"]
}
```

---

## Struttura backup/report

```
.diff_backups/
  2025YYYYMMDD-HHMMSS/
    path/del/file/originale.ext
    apply-report.json
    apply-report.txt
```

---

## Manutenzione dipendenze

Le versioni correnti verificate per l'applicazione sono:

* `PySide6==6.7.3` (Qt for Python 6.7 LTS, compatibile con Python 3.10–3.12 e con fix di stabilità per i dialoghi su Linux)
* `unidiff==0.7.5`

### Procedura per aggiornare PySide6 / unidiff

1. **Studia la compatibilità**
   * Consulta le note di rilascio di Qt for Python per verificare il supporto delle nuove versioni rispetto alla baseline del progetto (`Python 3.10+`).
   * Controlla il changelog di `unidiff` (GitHub/PyPI) per breaking changes e versioni di Python supportate.
2. **Prepara un ambiente pulito**
   ```bash
   python3 -m venv .venv-upgrade
   source .venv-upgrade/bin/activate
   python -m pip install --upgrade pip
   ```
3. **Installa le versioni candidate** (sostituisci `<versione>` con la release da testare)
   ```bash
   pip install PySide6==<versione> unidiff==<versione>
   ```
4. **Esegui gli smoke test**
   * Compila i moduli del progetto per intercettare errori di import: `python -m compileall patch_gui`.
   * Avvia l'app (`python -m patch_gui`) e verifica con un diff di esempio: caricamento, dry-run, applicazione reale, ripristino da backup.
5. **Aggiorna i file di progetto**
   * Aggiorna le versioni in `requirements.txt` (e nel `pyproject.toml` se inserisci vincoli più stretti).
   * Esegui `pip freeze` o aggiorna la documentazione se necessario.
6. **Documenta il cambiamento**
   * Aggiorna questa sezione del README con le nuove versioni supportate e i test eseguiti.

Quando hai finito, chiudi la sessione di prova con `deactivate` e rimuovi la virtualenv temporanea.

---

## Note

* L’app **non** modifica file binari.
* Per patch molto grandi, l’anteprima/ricerca potrebbe richiedere più tempo.

---

## Licenza

Il progetto è distribuito con licenza [MIT](LICENSE). Vedi il file `LICENSE` per il testo completo.
