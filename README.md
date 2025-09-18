<h1 align="center">Patch GUI – Diff Applier</h1>

<p align="center">
  <strong>Patch GUI è l'interfaccia elegante per applicare patch <em>unified diff</em> con la stessa cura con cui revisi il codice.</strong>
</p>

<p align="center">
  <a href="https://www.python.org/">
    <img src="https://img.shields.io/badge/python-3.10%2B-3776ab?logo=python&logoColor=white" alt="Python 3.10+" />
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/license-MIT-00b894" alt="MIT License" />
  </a>
  <a href="USAGE.md">
    <img src="https://img.shields.io/badge/docs-uso%20avanzato-6c5ce7" alt="Guida all'uso" />
  </a>
</p>

<p align="center">
  <em>GUI luminosa, CLI precisa e report istantanei per tenere ogni diff sotto controllo.</em>
</p>

---

## 🌈 Esperienza d'uso in breve

Patch GUI riprende la pulizia dell'interfaccia per accompagnarti dal caricamento all'applicazione del diff senza stacchi:

- **Dashboard reattiva** con tre colonne: file, hunk selezionato e anteprima colorata come nell'editor.
- **Toolbar contestuale** per scegliere soglia fuzzy, dry‑run, percorso di backup e lingua senza aprire menu nascosti.
- **Dialoghi chiari** quando il patching richiede la tua scelta (ambiguità, conflitti, file mancanti).
- **Report finali** coerenti con i badge della GUI: json, testo e backup ordinati per timestamp millisecondo.
- **CLI integrata** che replica le impostazioni chiave così da allineare automazione e uso interattivo.

> 💡 Una guida con screenshot e flussi completi è disponibile in [USAGE.md](USAGE.md).

---

## 📚 Indice

1. [Requisiti e dipendenze](#-requisiti-e-dipendenze)
2. [Installazione passo-passo](#-installazione-passo-passo)
3. [Primo avvio](#-primo-avvio)
4. [Modalità CLI](#-modalità-cli)
5. [Feature tour della GUI](#-feature-tour-della-gui)
6. [Test e pre-commit](#-test-e-pre-commit)
7. [Internazionalizzazione](#-internazionalizzazione)
8. [Opzioni tecniche](#-opzioni-tecniche)
9. [Risoluzione problemi](#-risoluzione-problemi)
10. [Backup & report](#-backup--report)
11. [Note sulla manutenzione](#-note-sulla-manutenzione)

---

## 🧰 Requisiti e dipendenze

- **Python 3.10+**.
- **PySide6 6.7.3** (inclusa con l'extra `gui`) e **unidiff 0.7.5**.
- **WSL Ubuntu** consigliato su Windows. L'app funziona anche su Linux nativo e macOS.
- **WSLg** attivo su Windows 11/10 21H2+ per visualizzare la GUI.

Pacchetti utili per Ubuntu/WSL:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git libgl1 libegl1 libxkbcommon-x11-0 libxcb-xinerama0
```

> ℹ️ I pacchetti Qt (`libgl1`, `libegl1`, `libxkbcommon-x11-0`, `libxcb-xinerama0`) eliminano l'errore del plugin `xcb` nelle installazioni WSL.

---

## 🧪 Installazione passo-passo

1. **Crea il virtualenv** nella root del progetto:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install --upgrade pip
   ```

2. **Installa Patch GUI** nella modalità che preferisci:

   ```bash
   pip install .        # solo CLI, ideale per server/headless
   pip install .[gui]   # CLI + interfaccia grafica PySide6
   ```

3. **(Opzionale) Setup per VS Code** dentro WSL:
   - `code .` dalla root del progetto.
   - `Ctrl+Shift+P` → **Python: Select Interpreter** → `.venv/bin/python`.
   - Suggerito `.vscode/settings.json`:

     ```json
     {
       "python.defaultInterpreterPath": ".venv/bin/python",
       "python.analysis.typeCheckingMode": "basic",
       "cSpell.language": "en,it",
       "cSpell.words": [
         "hunk",
         "fuzzy",
         "dry-run",
         "ripristino",
         "anteprima",
         "PySide6",
         "unidiff",
         "WSLg"
       ]
     }
     ```

> Se il pulsante **Run** usa ancora `/usr/bin/env python3`, esegui gli script dal terminale con l'ambiente attivo o aggiorna l'interprete nelle impostazioni dell'estensione Python.

---

## ⚡ Primo avvio

```bash
source .venv/bin/activate
patch-gui        # richiede l'extra "gui"
# oppure, in modalità modulo
python -m patch_gui
```

Senza l'extra grafico puoi comunque applicare patch:

```bash
patch-gui apply --root /percorso/al/progetto diff.patch
```

---

## 🧾 Modalità CLI

La CLI riproduce le stesse impostazioni principali della GUI. Tutti i comandi accettano anche input da `stdin`.

```bash
patch-gui apply --root . diff.patch
patch-gui apply --root . --dry-run --threshold 0.90 diff.patch
git diff | patch-gui apply --root . --backup ~/diff_backups -
patch-gui apply --root . --dry-run --log-level debug diff.patch
patch-gui apply --root . --non-interactive diff.patch
# per accettare automaticamente il candidato migliore senza prompt
patch-gui apply --root . --auto-accept diff.patch
```

- `--dry-run` simula l'applicazione mantenendo i file intatti e produce comunque i report (se non disabilitati).
- `--threshold` imposta la soglia fuzzy (default `0.85`).
- `--backup` personalizza la cartella in cui vengono salvati gli originali prima della patch.
- `--report-json` / `--report-txt` definiscono percorsi precisi per i report; per default vengono creati sotto `~/.diff_backups/reports/results/<timestamp-ms>/`.
- `--no-report` disattiva entrambi i file di report.
- `--exclude-dir NAME` permette di aggiungere directory personalizzate all'elenco di esclusione (puoi passare l'opzione più volte o separare i valori con virgole).
- `--no-default-exclude` disabilita la lista predefinita di esclusioni (es. `.git`, `.venv`, `node_modules`, `.diff_backups`) così da poter patchare anche file normalmente ignorati.
- `--non-interactive` mantiene il comportamento storico: se il percorso è ambiguo il file viene saltato senza prompt.
- `--auto-accept` sceglie autonomamente il candidato migliore per file e hunk ambigui, includendo i casi fuzzy: nessun input richiesto, ma la patch viene comunque applicata.
- `--log-level` imposta la verbosità del logger (`debug`, `info`, `warning`, `error`, `critical`; default `warning`). La variabile `PATCH_GUI_LOG_LEVEL` fornisce lo stesso controllo.
- L'uscita termina con codice `0` solo se tutti gli hunk vengono applicati.
- `--exclude-dir` aggiunge cartelle personalizzate agli esclusi. Usa l'opzione più volte o separa con virgole.
- `--no-default-exclude` toglie `.git`, `.venv`, `node_modules`, `.diff_backups` dagli esclusi standard.
- `--non-interactive` replica il comportamento tradizionale: i file ambigui vengono saltati senza prompt.
- `--log-level` controlla la verbosità (`debug`, `info`, `warning`, `error`, `critical`). La variabile `PATCH_GUI_LOG_LEVEL` offre lo stesso controllo.
Il comando termina con `0` solo se tutti gli hunk vengono applicati.

---

## 🖥️ Feature tour della GUI

1. **Layout a tre colonne**: elenco file a sinistra, hunk centrali con indicatori di stato, anteprima diff con colori neutri e badge coerenti con i pulsanti principali.
2. **Selettore root progetto** sempre visibile per cambiare rapidamente il contesto dei percorsi.
3. **Caricamento diff**:
   - Apri file `.diff` o `.patch`.
   - Incolla direttamente dagli appunti.
   - Incolla testo nel pannello e premi **Analizza testo diff** (supporta `git diff`, `git format-patch`, blocchi `*** Begin Patch`).
4. **Dry‑run come default**: la barra superiore evidenzia quando la patch è solo simulata.
5. **Applicazione reale**: disattiva Dry‑run e premi **Applica patch** per scrivere i file.
6. **Gestione ambiguità**: dialoghi modali mostrano tutte le opzioni con il contesto a colori; puoi decidere hunk per hunk.
7. **Feedback immediato**: barra di avanzamento in status bar, notifiche toast e riepilogo finale coerente con lo stile dell'interfaccia.
8. **Backup & report**: ogni run reale genera `~/.diff_backups/<timestamp-ms>/` con file originali e crea `apply-report.json` + `apply-report.txt`. In dry‑run vengono comunque generati report senza backup per documentare la simulazione.
9. **Ripristino**: dal menu **File → Ripristina da backup…** scegli il timestamp da cui recuperare i file.

Per i flussi completi, scorciatoie e screenshot dettagliati fai riferimento a [USAGE.md](USAGE.md).

---

## 🧪 Test e pre-commit

Esegui la suite automatizzata con:

```bash
pytest
```

> La CI ufficiale verifica la suite con Python 3.10+, in linea con il requisito minimo.

Per applicare gli stessi controlli della pipeline locale:

```bash
pip install pre-commit
pre-commit install
pre-commit run --all-files
```

### 🔎 Verifica manuale della barra di avanzamento

1. Avvia `patch-gui` e analizza un diff con più file/hunk.
2. Premi **Applica patch** (anche in dry‑run) per osservare la barra di stato con la **QProgressBar**.
3. Attendi la fine per verificare che la barra arrivi al 100 % e scompaia.

---

## 🌍 Internazionalizzazione

- I file Qt `.ts` risiedono in `patch_gui/translations/`.
- L'interfaccia testuale usa `gettext` (`patch_gui/localization.py`) con inglese di default.
- Durante `pip install .` o `python -m build` viene invocato `python -m build_translations`, che utilizza `lrelease`/`pyside6-lrelease` per produrre i `.qm`.
- Se gli strumenti Qt mancano, la GUI ricompila i `.qm` al volo nella cache Qt.
- Lingue incluse: **italiano** e **inglese**. Se il sistema non propone una lingua supportata, l'app resta in inglese.

### ➕ Aggiungere una nuova lingua

1. Copia `patch_gui/translations/patch_gui_en.ts` in `patch_gui/translations/patch_gui_<codice>.ts`.
2. Aggiorna i blocchi `<translation>` rispettando i placeholder (es. `{app_name}`).
3. Esegui `python -m build_translations` (richiede `lrelease` o `pyside6-lrelease` nel `PATH`).
4. I `.qm` risultanti sono ignorati dal VCS ma inclusi nei pacchetti distribuiti.

Forza una lingua senza cambiare il locale di sistema:

```bash
export PATCH_GUI_LANG=it
patch-gui
# oppure
PATCH_GUI_LANG=it patch-gui apply --root . diff.patch
```

---

## 🧩 Opzioni tecniche

- **Soglia fuzzy**: regola la tolleranza nel confronto del contesto (`difflib.SequenceMatcher`).
- **EOL**: preserva lo stile originale (LF/CRLF) al salvataggio.
- **Ricerca file**: tenta prima il percorso relativo esatto (ripulendo prefissi `a/`/`b/`), poi ricerca per nome in modo ricorsivo; in caso di multipli chiede quale usare. Con `--non-interactive` i file ambigui vengono saltati, mentre `--auto-accept` seleziona automaticamente il match con punteggio più alto.
- **Formati supportati**: qualsiasi file di testo (JS, TS, HTML, CSS, MD, Rust, …).
- **Soglia fuzzy**: controlla la tolleranza del contesto (basata su `difflib.SequenceMatcher`).
- **Fine linea (EOL)**: i file vengono salvati rispettando lo stile originale (LF/CRLF).
- **Ricerca file**: tenta prima il percorso relativo esatto (ripulendo prefissi `a/`/`b/`), poi ricerca ricorsiva per nome. In modalità interattiva ti chiede quale percorso usare; con `--non-interactive` salta i conflitti.
- **Formati supportati**: qualsiasi file di testo (JavaScript, TypeScript, HTML, CSS, Markdown, Rust, …).

- **Logging**:
  - `PATCH_GUI_LOG_LEVEL` controlla la verbosità (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` o valori numerici).
  - `PATCH_GUI_LOG_FILE` definisce il percorso del log (default `~/.patch_gui.log`).

```bash
# Avvio GUI con log dettagliati nel percorso di default (~/.patch_gui.log)
PATCH_GUI_LOG_LEVEL=DEBUG patch-gui

# Modalità CLI con log personalizzato
PATCH_GUI_LOG_FILE="$HOME/logs/patch_gui-app.log" PATCH_GUI_LOG_LEVEL=WARNING \
  patch-gui apply --root . diff.patch
```

---

## 🛟 Risoluzione problemi

### `ModuleNotFoundError: No module named 'unidiff'`

1. Attiva il virtualenv:

   ```bash
   source .venv/bin/activate
   python -c "import sys; print(sys.executable)"
   pip show unidiff
   ```

   Se `pip show` non trova il pacchetto:

   ```bash
   pip install unidiff
   ```

2. In **VS Code** seleziona `.venv/bin/python`. Se l'esecuzione usa ancora `/usr/bin/env python3`, avvia i comandi dal terminale con l'ambiente attivo.

### Errori Qt (`xcb`, display) su WSL

- Installa i pacchetti elencati in [Requisiti e dipendenze](#-requisiti-e-dipendenze).
- Verifica che **WSLg** sia abilitato. In ambienti senza WSLg puoi usare un server X esterno (meno consigliato).

### Avvisi Pylance / typing

- Il progetto è tipizzato per ridurre i warning. Per un'esperienza più permissiva:

  ```jsonc
  // .vscode/settings.json
  {
    "python.analysis.typeCheckingMode": "basic"
  }
  ```

- Per librerie senza stub (es. `unidiff`) vengono usate annotazioni conservative (`Any`).

### Code Spell Checker (cSpell) e testo in italiano

```json
{
  "cSpell.language": "en,it",
  "cSpell.words": ["hunk", "ripristino", "anteprima", "ricorsiva", "similarità", "WSLg", "PySide6", "unidiff"]
}
```

---

## 🗂️ Backup & report

```text
~/.diff_backups/
  2025YYYYMMDD-HHMMSS-fff/
    path/del/file/originale.ext
  reports/
    results/
      2025YYYYMMDD-HHMMSS-fff/
        apply-report.json
        apply-report.txt
```

---

## 🛠️ Note sulla manutenzione

- Le dipendenze sono definite in `pyproject.toml` e `requirements.txt` (per ambienti legacy).
- Il comando `python -m build_translations` rigenera i file `.qm` partendo dalle sorgenti `.ts`.
- Usa `generate_logo_assets.py` per ricreare le icone vettoriali/bitmap quando aggiorni l'identità visiva.
- Consulta [WARP.md](WARP.md) per linee guida sugli aggiornamenti periodici.

---

## 📄 Licenza

Patch GUI è distribuito sotto licenza [MIT](LICENSE).
