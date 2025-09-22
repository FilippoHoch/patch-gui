# Patch GUI – Diff Applier

<p align="center">
  <a href="https://www.python.org/">
    <img src="https://img.shields.io/badge/python-3.10%2B-3776ab?logo=python&logoColor=white" alt="Python 3.10+" />
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/license-MIT-00b894" alt="MIT License" />
  </a>
  <a href="https://github.com/patch-gui/patch-gui/releases">
    <img src="https://img.shields.io/github/v/release/patch-gui/patch-gui?display_name=tag&color=ff7675" alt="Ultima release" />
  </a>
  <a href="USAGE.md">
    <img src="https://img.shields.io/badge/docs-uso%20avanzato-6c5ce7" alt="Guida all'uso" />
  </a>
</p>

Patch GUI applica patch *unified diff* offrendo un'interfaccia Qt curata e una CLI con
le stesse euristiche. Pensato per chi preferisce una revisione visiva ma vuole
mantenere l'automazione nei flussi di lavoro Git.

## Indice

1. [Panoramica](#panoramica)
2. [Requisiti](#requisiti)
3. [Installazione](#installazione)
4. [Avvio rapido](#avvio-rapido)
5. [Modalità CLI](#modalità-cli)
6. [GUI in breve](#gui-in-breve)
7. [Backup e report](#backup-e-report)
8. [Configurazione persistente](#configurazione-persistente)
9. [Sviluppo e test](#sviluppo-e-test)
10. [Risoluzione problemi](#risoluzione-problemi)
11. [Licenza](#licenza)

## Panoramica

- **Anteprima diff a tre colonne**: elenco file, hunk con stato e visualizzazione
  colorata con numeri di riga reali.
- **Dry-run di default** con opzione per applicare realmente le modifiche,
  generando sempre report dettagliati.
- **Ricerca file flessibile** con soglia fuzzy configurabile e gestione delle
  ambiguità direttamente da GUI o CLI.
- **Backup automatici e report** (`json`/`txt`) ordinati per timestamp e pronti
  per la condivisione o l'audit.
- **Internazionalizzazione**: interfaccia e CLI sono disponibili in italiano e
  inglese, con traduzioni Qt aggiornabili.

Maggiori esempi, scorciatoie e screenshot sono raccolti in [USAGE.md](USAGE.md).

## Requisiti

- Python **3.10 o superiore**.
- [PySide6](https://doc.qt.io/qtforpython/) (installato automaticamente con
  l'extra `gui`).
- [unidiff](https://github.com/matiasb/python-unidiff) per l'applicazione delle
  patch.
- Su Windows è consigliato **WSL Ubuntu** con **WSLg** attivo per usare la GUI.

Dipendenze utili in ambienti Ubuntu/WSL:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git libgl1 libegl1 \
  libxkbcommon-x11-0 libxcb-xinerama0
```

## Installazione

### 1. Prepara l'ambiente virtuale

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

### 2. Installa Patch GUI

```bash
pip install .        # solo CLI
pip install .[gui]   # CLI + interfaccia grafica PySide6
```

Per usare l'app come dipendenza di un progetto esterno:

```bash
pip install patch-gui
pip install "patch-gui[gui]"  # con interfaccia grafica
```

### 3. Opzionale: configurazione VS Code (WSL)

- Avvia `code .` dalla root del repository.
- `Ctrl+Shift+P` → **Python: Select Interpreter** → `.venv/bin/python`.
- Suggerimento `.vscode/settings.json`:

  ```json
  {
    "python.defaultInterpreterPath": ".venv/bin/python",
    "python.analysis.typeCheckingMode": "basic",
    "cSpell.language": "en,it"
  }
  ```

## Avvio rapido

GUI:

```bash
source .venv/bin/activate
patch-gui          # richiede l'extra "gui"
# oppure
python -m patch_gui
```

CLI:

```bash
patch-gui apply --root . diff.patch
patch-gui apply --root . --dry-run --threshold 0.90 diff.patch
# Leggi da STDIN e salva i backup altrove
git diff | patch-gui apply --root . --backup ~/diff_backups -
```

## Modalità CLI

`patch-gui apply` condivide le stesse euristiche della GUI. Le opzioni più
utili:

- `--dry-run`: simula l'esecuzione senza modificare i file.
- `--threshold`: regola la tolleranza fuzzy (default `0.85`).
- `--backup`: directory personalizzata per backup e report.
- `--report-json` / `--report-txt`: percorsi espliciti per i report.
- `--no-report`: disattiva la generazione dei file di report.
- `--summary-format`: controlla il riepilogo su stdout (`text`, `json`, `ai`, `none`). L'opzione `ai` usa, se disponibile, un endpoint esterno definito tramite la variabile d'ambiente `PATCH_GUI_AI_SUMMARY_ENDPOINT`.
- `--exclude-dir`: aggiunge cartelle all'elenco di esclusioni.
- `--no-default-exclude`: rimuove le esclusioni predefinite (es. `.git`,
  `.venv`).
- `--non-interactive`: evita prompt e salta i conflitti.
- `--auto-accept`: accetta automaticamente il candidato migliore senza
  richiedere input.
- `--log-level`: livello di logging (`debug`, `info`, `warning`, `error`,
  `critical`).

Comandi aggiuntivi:

- `patch-gui download-exe`: scarica l'eseguibile Windows dalla pagina delle
  release. Usa `--output` per impostare il percorso di destinazione e `--tag`
  per selezionare una release specifica.
- `patch-gui config`: visualizza o modifica la configurazione persistente.
  Esempi:

  ```bash
  patch-gui config show
  patch-gui config set threshold 0.9
  patch-gui config reset log_file
  ```

## GUI in breve

1. **Layout a tre colonne** con elenco file, hunk e anteprima diff.
2. **Toolbar visibile** per dry-run, soglia fuzzy, lingua e cartella di backup.
3. **Dialoghi contestuali** per risolvere file ambigui o hunk in conflitto.
4. **Indicatori di avanzamento** e riepilogo finale con accesso diretto ai
   report generati.
5. **Ripristino backup** dal menu **File → Ripristina da backup…** scegliendo
   il timestamp desiderato.

## Backup e report

Struttura predefinita:

```text
~/.diff_backups/
  2025YYYYMMDD-HHMMSS-fff/
    percorso/del/file/originale.ext
  reports/
    results/
      2025YYYYMMDD-HHMMSS-fff/
        apply-report.json
        apply-report.txt
```

- I backup sono creati solo fuori dal dry-run.
- I report vengono generati anche nelle simulazioni (puoi disattivarli con
  `--no-report`).
- La retention configurabile rimuove automaticamente i backup più vecchi.

## Configurazione persistente

Le impostazioni vengono salvate in `settings.toml` sotto:

- Linux: `~/.config/patch-gui/`
- macOS: `~/Library/Application Support/Patch GUI/`
- Windows: `%APPDATA%\Patch GUI\`

La configurazione include soglia fuzzy, directory escluse, percorsi di backup,
livello di log, gestione dei report e parametri di rotazione del file di log.
Puoi modificarla dalla GUI o tramite `patch-gui config`.

## Sviluppo e test

```bash
pip install -e .[gui]
pip install -r requirements.txt
pytest
```

Per allineare i controlli con la CI:

```bash
pip install pre-commit
pre-commit install
pre-commit run --all-files
```

Le traduzioni Qt si ricompilano con:

```bash
python -m build_translations
```

Per pubblicare una release consulta la checklist in [RELEASE.md](RELEASE.md).

## Risoluzione problemi

### `ModuleNotFoundError: No module named 'unidiff'`

Verifica l'ambiente virtuale:

```bash
source .venv/bin/activate
pip install unidiff
```

### Errori Qt (`xcb`, display) su WSL

Installa i pacchetti elencati in [Requisiti](#requisiti) e assicurati che **WSLg**
sia attivo. In assenza di WSLg usa un server X esterno.

### Avvisi Pylance / typing

Imposta un controllo più permissivo in `.vscode/settings.json`:

```jsonc
{
  "python.analysis.typeCheckingMode": "basic"
}
```

## Licenza

Patch GUI è distribuito sotto licenza [MIT](LICENSE).
