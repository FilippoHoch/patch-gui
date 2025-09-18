# 📦 Processo di rilascio

Questa guida descrive come preparare, verificare e pubblicare una nuova versione di
Patch GUI. Segui tutti i passaggi in ordine per garantire pacchetti e note di
rilascio coerenti.

## 1. Aggiornamento versioni e changelog

1. Scegli il numero di versione secondo il [Versionamento Semantico](https://semver.org/lang/it/).
2. Aggiorna la versione in:
   - `pyproject.toml`
   - `patch_gui/_version.py`
3. Sposta le voci in `CHANGELOG.md` dalla sezione **[Non rilasciato]** alla nuova
   sezione con la versione e la data odierna.
4. Includi sempre un riassunto delle novità nella sezione "Aggiunto/Modificato/Fissato".

## 2. Verifica qualità

```bash
python -m pip install --upgrade pip build twine
python -m pip install -e .[gui]
pytest
```

Se vengono introdotte nuove stringhe testuali, rigenera le traduzioni prima dei
test usando:

```bash
python build_translations.py --release
```

## 3. Costruzione pacchetti

1. Pulisci la cartella `dist/` e gli artefatti precedenti:

   ```bash
   rm -rf build dist *.egg-info
   ```

2. Costruisci sdist e wheel:

   ```bash
   python -m build
   ```

3. Verifica l'integrità dei pacchetti generati:

   ```bash
   twine check dist/*
   ```

## 4. Pubblicazione

1. Crea un commit dedicato con gli aggiornamenti di versione e changelog.
2. Tagga il commit con `git tag vX.Y.Z` e spingi sia il branch sia il tag.
3. Su GitHub crea una Release associando il tag appena creato.
4. Copia nella descrizione il blocco corrispondente del changelog e allega i file
   `dist/*.whl` e `dist/*.tar.gz` come asset.
5. Dopo la pubblicazione, aggiorna eventuale documentazione che fa riferimento
   alla versione corrente.

## 5. Dopo il rilascio

- Riporta `CHANGELOG.md` alla sezione **[Non rilasciato]** con placeholder vuoti.
- Apri (se necessario) un issue per pianificare il prossimo ciclo di sviluppo.

Seguendo questi passaggi avremo release ripetibili e pacchetti pronti per PyPI o
per la distribuzione interna.
