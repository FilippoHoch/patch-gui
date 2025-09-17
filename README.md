<h1 align="center">Patch GUI – Diff Applier</h1>

<p align="center">
  <strong>App desktop e CLI in Python per applicare patch <em>unified diff</em> in modo rapido, sicuro e interattivo.</strong>
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

---

## 🚀 Panoramica

Patch GUI è pensata per sviluppatori che lavorano con diff complessi, pull request o patch inviate via email. L'app consente di:

- **Caricare patch** da file, clipboard o testo incollato.
- **Ispezionare ogni hunk** con anteprima e modalità dry‑run.
- **Applicare patch fuzzy** con soglia configurabile e gestione interattiva delle ambiguità.
- **Generare backup e report** automatici per tenere traccia di ogni esecuzione.
- **Usare la CLI** (`patch-gui apply`) negli script o nei workflow CI.

> 💡 Per una guida passo-passo consulta [USAGE.md](USAGE.md).

---

## 📚 Indice rapido

1. [Requisiti](#-requisiti)
2. [Installazione](#-installazione-consigliata-con-virtualenv)
3. [Avvio rapido](#-avvio-rapido)
4. [Modalità CLI](#-modalità-cli-senza-gui)
5. [Test & pre-commit](#-test)
6. [Guida all'uso](#-guida-alluso)
7. [Internazionalizzazione](#-internazionalizzazione)
8. [Opzioni tecniche](#-opzionidettagli-tecnici)
9. [Troubleshooting](#-risoluzione-problemi)
10. [Backup & report](#-struttura-backupreport)
11. [Manutenzione dipendenze](#-manutenzione-dipendenze)
12. [Note e licenza](#-note)

---

## 🧰 Requisiti

- **WSL Ubuntu** (consigliato; funziona anche su Linux nativo e macOS).
- **Python 3.10+**.
- Dipendenze testate: **PySide6 6.7.3** e **unidiff 0.7.5** (vedi [Manutenzione dipendenze](#-manutenzione-dipendenze)).
- **WSLg** abilitato per mostrare la GUI in Windows 11/10 21H2+.

Pacchetti utili in ambiente Ubuntu/WSL:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git libgl1 libegl1 libxkbcommon-x11-0 libxcb-xinerama0
```

> ℹ️ I pacchetti `libgl1`/`libegl1`/`libxkbcommon-x11-0`/`libxcb-xinerama0` risolvono i tipici errori Qt (`plugin xcb`) in WSL.

---

## 🛠️ Installazione (consigliata con virtualenv)

Nella root del progetto:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install .          # installa la sola CLI
# oppure (per aggiungere l'interfaccia grafica PySide6)
pip install .[gui]
```

> `pip install .` porta con sé solo le dipendenze minime per la CLI.
> Usa `pip install .[gui]` per includere PySide6 e la GUI.

### 💻 VS Code (WSL)

1. Apri la cartella del progetto **dentro WSL** (`code .`).
2. `Ctrl+Shift+P` → **Python: Select Interpreter** → scegli `.venv/bin/python`.
3. (Consigliato) Crea `.vscode/settings.json`:

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

> Se il pulsante **Run** usa ancora `/usr/bin/env python3`, assicurati che l'estensione Python punti all'interprete corretto o lancia gli script dal terminale con l'ambiente attivo.

---

## ⚡ Avvio rapido

```bash
source .venv/bin/activate
patch-gui  # richiede l'extra "gui"
# oppure
python -m patch_gui
```

> Se hai installato solo la CLI (`pip install .`), usa `patch-gui apply ...`.

### 🧾 Modalità CLI (senza GUI)

```bash
patch-gui apply --root /percorso/al/progetto diff.patch
# oppure
python -m patch_gui apply --root /percorso/al/progetto diff.patch

# Esempi di opzioni
patch-gui apply --root . --dry-run --threshold 0.90 diff.patch
git diff | patch-gui apply --root . --backup ~/diff_backups -
# log dettagliati su stdout
patch-gui apply --root . --dry-run --log-level debug diff.patch
# per disabilitare le richieste interattive in caso di ambiguità
patch-gui apply --root . --non-interactive diff.patch
```

- `--dry-run` simula l'applicazione lasciando i file invariati; i report vengono generati a meno di `--no-report`.
- `--threshold` imposta la soglia fuzzy (default 0.85).
- `--backup` permette di scegliere la cartella base (default `~/.diff_backups`).
- `--report-json` / `--report-txt` impostano i percorsi dei report generati (default `~/.diff_backups/reports/results/<timestamp-ms>/apply-report.json|.txt`, dove `<timestamp-ms>` segue il formato `YYYYMMDD-HHMMSS-fff`).
- `--no-report` disattiva entrambi i file di report.
- `--non-interactive` mantiene il comportamento storico: se il percorso è ambiguo il file viene saltato senza prompt.
- `--log-level` imposta la verbosità del logger (`debug`, `info`, `warning`, `error`, `critical`; default `warning`). La variabile `PATCH_GUI_LOG_LEVEL` fornisce lo stesso controllo.
- L'uscita termina con codice `0` solo se tutti gli hunk vengono applicati.

---

## ✅ Test

Esegui la suite automatizzata con:

```bash
pytest
```

## 🧹 Pre-commit

Per avere formattazione automatica (**Black**), linting (**Ruff**), type checking (**mypy**) e test rapidi (**pytest --quiet**):

```bash
pip install pre-commit
pre-commit install
```

Esecuzione manuale di tutti gli hook:

```bash
pre-commit run --all-files
```

### 🔎 Verifica manuale barra di avanzamento

1. Avvia la GUI (`patch-gui`) e analizza un diff con più file/hunk.
2. Premi **Applica patch** (anche in dry‑run): la barra di stato mostra la **QProgressBar** con la percentuale di avanzamento.
3. Attendi il completamento per verificare che la barra raggiunga il 100 % e scompaia.

---

## 🧭 Guida all'uso

1. **Root progetto** → seleziona la cartella base: i percorsi nei diff sono risolti relativamente a questa root.
2. **Carica diff**:
   - Apri un file `.diff`.
   - Incolla dagli appunti.
   - Incolla testo nel riquadro e clicca **Analizza testo diff**.
   - Supporta diff standard (`git diff`, `git format-patch`) e blocchi `*** Begin Patch` / `*** Update File`.
3. **Analizza diff**: nel pannello sinistro trovi file e hunk da rivedere.
4. **Dry‑run** (default): imposta la **Soglia fuzzy** (es. 0.85) e premi **Applica patch** per simulare.
5. **Applicazione reale**: disattiva Dry‑run e clicca **Applica patch**.
6. **Avanzamento**: la barra di stato mostra il progresso in tempo reale.
7. **Ambiguità**: se sono trovate più posizioni plausibili, appare un dialog con tutte le opzioni e relativo contesto.
8. **File mancanti**: se non trovati sotto la root, vengono saltati (come da preferenza).
9. **Backup & report**: ogni run reale crea `~/.diff_backups/<timestamp-ms>/` con copie originali (a meno di specificare `--backup`) e genera `apply-report.json` e `apply-report.txt`. Il suffisso `<timestamp-ms>` include millisecondi (`YYYYMMDD-HHMMSS-fff`) per rendere univoca ogni esecuzione. Anche in dry‑run, se i report non sono disattivati, vengono creati (senza backup) per documentare la simulazione.
10. **Ripristino**: usa **Ripristina da backup…**, scegli il timestamp e i file verranno ripristinati.

Per una guida dettagliata con screenshot e flussi completi consulta [USAGE.md](USAGE.md).

---

## 🌍 Internazionalizzazione

- I file di traduzione Qt (`.ts`) si trovano in `patch_gui/translations/`.
- La CLI e l'entry point testuale usano `gettext` (`patch_gui/localization.py`) con inglese di default.
- Durante `pip install .` o `python -m build` viene eseguito `python -m build_translations`, che invoca `lrelease`/`pyside6-lrelease` per produrre i binari `.qm`.
- Se gli strumenti Qt non sono disponibili, l'app compila al volo nella cache Qt. La GUI prova a caricare `.qm` già presenti e usa `lrelease` solo se assenti/obsoleti.
- Traduzioni incluse: **inglese** e **italiano**. Se non è disponibile una lingua compatibile, l'interfaccia resta in inglese.

### ➕ Aggiungere una nuova lingua

1. Copia `patch_gui/translations/patch_gui_en.ts` in `patch_gui/translations/patch_gui_<codice>.ts` (es. `patch_gui_es.ts`).
2. Aggiorna i blocchi `<translation>…</translation>` mantenendo intatti i placeholder (es. `{app_name}`).
3. Rigenera i binari con `python -m build_translations` (richiede `lrelease` o `pyside6-lrelease` nel `PATH`).
4. I file `.qm` generati sono ignorati da Git ma inclusi nei pacchetti costruiti.

Per forzare una lingua senza cambiare il locale di sistema:

```bash
export PATCH_GUI_LANG=it
patch-gui
# oppure
PATCH_GUI_LANG=it patch-gui apply --root . diff.patch
```

---

## ⚙️ Opzioni/Dettagli tecnici

- **Soglia fuzzy**: regola la tolleranza nel confronto del contesto (`difflib.SequenceMatcher`).
- **EOL**: preserva lo stile originale (LF/CRLF) al salvataggio.
- **Ricerca file**: tenta prima il percorso relativo esatto (ripulendo prefissi `a/`/`b/`), poi ricerca per nome in modo ricorsivo; in caso di multipli chiede quale usare. Con `--non-interactive` i file ambigui vengono saltati.
- **Formati supportati**: qualsiasi file di testo (JS, TS, HTML, CSS, MD, Rust, …).
- **Logging**:
  - `PATCH_GUI_LOG_LEVEL` controlla la verbosità (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` o valori numerici come `20`). Default `INFO`.
  - `PATCH_GUI_LOG_FILE` imposta il percorso del file di log (default `~/.patch_gui.log`).

```bash
# Avvio GUI con log dettagliati nel percorso di default (~/.patch_gui.log)
PATCH_GUI_LOG_LEVEL=DEBUG patch-gui

# Modalità CLI con log in un percorso personalizzato
PATCH_GUI_LOG_FILE="$HOME/logs/patch_gui-app.log" PATCH_GUI_LOG_LEVEL=WARNING \
  patch-gui apply --root . diff.patch
```

---

## 🛟 Risoluzione problemi

### `ModuleNotFoundError: No module named 'unidiff'`

1. Assicurati di aver **attivato il virtualenv**:

   ```bash
   source .venv/bin/activate
   python -c "import sys; print(sys.executable)"
   pip show unidiff
   ```

   Se `pip show` non trova il pacchetto:

   ```bash
   pip install unidiff
   ```

2. In **VS Code**, seleziona l'interprete `.venv/bin/python` (vedi sopra). Se il runner usa ancora `/usr/bin/env python3`, esegui dallo **Integrated Terminal** con venv attivo.

### Errori Qt (plugin `xcb`, display, ecc.) su WSL

- Installa i pacchetti elencati in [Requisiti](#-requisiti).
- Verifica che **WSLg** sia attivo (su Windows 11 è di default). In ambienti senza WSLg puoi usare un X‑Server esterno, ma non è consigliato.

### Avvisi Pylance/typing

- Il progetto è tipizzato per ridurre i warning. Per una modalità più permissiva:

  ```jsonc
  // .vscode/settings.json
  {
    "python.analysis.typeCheckingMode": "basic"
  }
  ```

- In caso di falsi positivi su librerie senza type stubs (es. `unidiff`), il codice usa annotazioni conservative (`Any`).

### Code Spell Checker (cSpell) e testo in italiano

Aggiungi l'italiano e alcune parole tecniche:

```json
{
  "cSpell.language": "en,it",
  "cSpell.words": ["hunk", "ripristino", "anteprima", "ricorsiva", "similarità", "WSLg", "PySide6", "unidiff"]
}
```

---

## 🗂️ Struttura backup/report

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

## ♻️ Manutenzione dipendenze

Versioni verificate:

- `PySide6==6.7.3` (extra opzionale `gui`: Qt for Python 6.7 LTS, compatibile con Python 3.10–3.12 e con fix di stabilità per i dialoghi su Linux).
- `unidiff==0.7.5`.

### Procedura di aggiornamento

1. **Verifica compatibilità**:
   - Leggi le note di rilascio di Qt for Python rispetto al supporto Python 3.10+.
   - Controlla il changelog di `unidiff` (GitHub/PyPI) per breaking changes.
2. **Prepara un ambiente pulito**:

   ```bash
   python3 -m venv .venv-upgrade
   source .venv-upgrade/bin/activate
   python -m pip install --upgrade pip
   ```

3. **Installa le versioni candidate** (sostituisci `<versione>`):

   ```bash
   pip install PySide6==<versione> unidiff==<versione>
   ```

4. **Esegui smoke test**:
   - Compila i moduli: `python -m compileall patch_gui`.
   - Avvia l'app (`python -m patch_gui`) e verifica: caricamento diff, dry-run, applicazione reale, ripristino da backup.

5. **Aggiorna il progetto**:
   - Aggiorna le versioni in `requirements.txt` (e nel `pyproject.toml` se necessario).
   - Esegui `pip freeze` o aggiorna la documentazione.

6. **Documenta il cambiamento** aggiornando questa sezione con versioni e test.

7. Quando hai finito, `deactivate` e rimuovi la virtualenv temporanea.

---

## 📝 Note

- L'app **non** modifica file binari.
- Per diff molto grandi l'anteprima/ricerca potrebbe richiedere più tempo.

## 📄 Licenza

Distribuito con licenza [MIT](LICENSE).

