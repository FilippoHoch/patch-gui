# Patch GUI – Diff Applier (PySide6)

Applicazione desktop (GUI) in **Python + PySide6/Qt** per applicare patch **unified diff** (anche `*** Begin Patch` / `*** Update File`) a file di progetto.

Caratteristiche principali:

* Caricamento da **file**, **clipboard** o **textarea**
* Ricerca ricorsiva dei file target
* Modalità **dry‑run** con anteprima
* Matching **esatto → fuzzy** con soglia configurabile
* Risoluzione **interattiva** delle ambiguità
* **Backup** automatici e **report** dettagliati

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
pip install -r requirements.txt
```

Se non usi `requirements.txt`, installa direttamente:

```bash
pip install PySide6 unidiff
```

Crea/aggiorna `requirements.txt` (opzionale):

```txt
PySide6
unidiff
```

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
python diff_applier_gui.py
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

## Note

* L’app **non** modifica file binari.
* Per patch molto grandi, l’anteprima/ricerca potrebbe richiedere più tempo.

---

## Licenza

Il progetto è distribuito con licenza [MIT](LICENSE). Vedi il file `LICENSE` per il testo completo.
