<h1 align="center">Patch GUI – Diff Applier</h1>

<p align="center">
  <strong>L'app desktop e CLI per applicare patch <em>unified diff</em> in modo sicuro, elegante e guidato.</strong>
</p>

<p align="center">
  <a href="CHANGELOG.md">
    <img src="https://img.shields.io/badge/release-v0.2.0-0984e3?logo=semantic-release&logoColor=white" alt="Release 0.2.0" />
  </a>
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

## ✨ Novità principali

- **Tema visivo aggiornato**: badge, gradienti e colori coerenti con l'interfaccia grafica rendono il diff più leggibile.
- **Report e backup potenziati**: puoi configurare direttamente da CLI/GUI i percorsi dei log, la rotazione e quanti backup conservare.
- **Changelog e processo di rilascio strutturati**: trovi in [CHANGELOG.md](CHANGELOG.md) tutte le note della versione 0.2.0 e in [RELEASE.md](RELEASE.md) la procedura ufficiale per generare pacchetti e pubblicare una release.

Consulta la sezione [🚀 Panoramica](#-panoramica) per esplorare tutte le funzionalità.

---

## 📚 Indice rapido

1. [Panoramica](#-panoramica)
2. [Download & pacchetti](#-download--pacchetti)
3. [Avvio rapido](#-avvio-rapido)
4. [Modalità CLI](#-modalità-cli-senza-gui)
5. [Funzionalità principali](#-funzionalità-principali)
6. [Test & qualità](#-test--qualità)
7. [Internazionalizzazione](#-internazionalizzazione)
8. [Backup & report](#-backup--report)
9. [Risoluzione problemi](#-risoluzione-problemi)
10. [Manutenzione dipendenze](#-manutenzione-dipendenze)
11. [Note e licenza](#-note)

---

## 🚀 Panoramica

Patch GUI nasce per chi lavora quotidianamente con diff complessi, code review e patch condivise via email. L'applicazione unisce un'interfaccia moderna a strumenti avanzati per controllare ogni riga applicata.

Con Patch GUI puoi:

- **Caricare patch** da file, clipboard o testo incollato.
- **Analizzare ogni hunk** con anteprima contestuale e modalità `dry-run`.
- **Gestire patch fuzzy** con soglia configurabile e gestione interattiva delle ambiguità.
- **Generare backup e report** automatici per tracciare ogni esecuzione.
- **Integrare la CLI** (`patch-gui apply`) in script e workflow CI/CD.

> 💡 Per una guida passo-passo consulta [USAGE.md](USAGE.md).

---

## 📦 Download & pacchetti

### Installazione rapida (ambiente locale)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install .[gui]  # include CLI + interfaccia grafica
```

Se ti serve solo la CLI, puoi usare `pip install .` senza l'extra `gui`.

### Costruire i pacchetti ufficiali

1. Assicurati di avere `build` e `twine` installati: `pip install build twine`.
2. Esegui `python -m build` per generare `sdist` e `wheel` nella cartella `dist/`.
3. Valida i pacchetti con `twine check dist/*`.
4. Pubblica gli artefatti come descritto in [RELEASE.md](RELEASE.md).

| Artefatto | Descrizione | Quando usarlo |
| --- | --- | --- |
| `patch_gui-0.2.0-py3-none-any.whl` | Wheel universale con GUI opzionale | Installazione rapida su ambienti controllati |
| `patch-gui-0.2.0.tar.gz` | Sorgenti (sdist) con script di build traduzioni | Distribuzione su PyPI o ambienti air-gapped |

---

## ⚡ Avvio rapido

```bash
source .venv/bin/activate
patch-gui  # richiede l'extra "gui"

# oppure
python -m patch_gui
```

> Se hai installato solo la CLI (`pip install .`), usa `patch-gui apply ...`.

---

## 🧾 Modalità CLI (senza GUI)

```bash
patch-gui apply --root /percorso/al/progetto diff.patch

# Opzioni utili
patch-gui apply --root . --dry-run --threshold 0.90 diff.patch
git diff | patch-gui apply --root . --backup ~/diff_backups -
patch-gui apply --root . --dry-run --log-level debug diff.patch
patch-gui apply --root . --non-interactive diff.patch
```

- `--dry-run` simula l'applicazione senza toccare i file; i report vengono generati a meno di `--no-report`.
- `--threshold` imposta la soglia fuzzy (default 0.85).
- `--backup` permette di scegliere la cartella base (default `~/.diff_backups`).
- `--report-json` / `--report-txt` impostano i percorsi dei report generati.
- `--no-report` disattiva entrambi i file di report.
- `--exclude-dir NAME` aggiunge directory personalizzate all'elenco di esclusione.
- `--no-default-exclude` disabilita la lista predefinita di esclusioni.
- `--non-interactive` mantiene il comportamento storico saltando file ambigui.
- `--log-level` gestisce la verbosità (`debug`, `info`, `warning`, `error`, `critical`).

L'uscita restituisce `0` solo se tutti gli hunk vengono applicati correttamente.

---

## 🧩 Funzionalità principali

- **Diff viewer potenziato** con numeri di riga sincronizzati e badge colorati per aggiunte/rimozioni.
- **Controllo fuzzy interattivo** per scegliere come risolvere conflitti o applicazioni multiple.
- **Gestione automatica dei backup** con timestamp e struttura ordinata in `~/.diff_backups`.
- **Report JSON/TXT** per integrare risultati in workflow automatizzati.
- **Temi coerenti** tra GUI e documentazione per un'esperienza uniforme.

---

## ✅ Test & qualità

Esegui la suite automatizzata con:

```bash
pytest
```

Per pubblicare una nuova versione segui sempre la checklist descritta in [RELEASE.md](RELEASE.md).

---

## 🌍 Internazionalizzazione

- Le stringhe sono gestite tramite file `.ts` e `.qm` in `patch_gui/translations/`.
- Usa `build_translations.py` per rigenerare i cataloghi prima di creare una release.
- L'app rileva automaticamente la lingua del sistema, con fallback all'inglese.

---

## 🗂️ Backup & report

- I backup vengono salvati per default in `~/.diff_backups` organizzati per timestamp.
- Ogni esecuzione produce (se non disabilitato) un report JSON e uno testuale con statistiche dettagliate sugli hunk applicati.
- Puoi personalizzare percorsi e politiche di conservazione dalle impostazioni avanzate.

---

## 🛠️ Manutenzione dipendenze

- Python 3.10+ è supportato ufficialmente.
- Dipendenze chiave: **PySide6 6.7.3**, **unidiff 0.7.5**, **charset-normalizer 3.3.2+**.
- Per ambienti Ubuntu/WSL installa anche: `libgl1`, `libegl1`, `libxkbcommon-x11-0`, `libxcb-xinerama0`.

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git \
  libgl1 libegl1 libxkbcommon-x11-0 libxcb-xinerama0
```

---

## 🆘 Risoluzione problemi

- Errore Qt "xcb": verifica di aver installato i pacchetti aggiuntivi elencati sopra.
- GUI lenta su WSL: abilita WSLg e assicurati di avere driver grafici aggiornati.
- Report mancanti: controlla che `--no-report` non sia stato passato e che i percorsi siano scrivibili.

Apri una issue se riscontri problemi non coperti da questa sezione.

---

## 📄 Note

Patch GUI è rilasciato sotto licenza [MIT](LICENSE). Consulta [USAGE.md](USAGE.md) per esempi dettagliati e [CHANGELOG.md](CHANGELOG.md) per l'elenco completo delle modifiche.
