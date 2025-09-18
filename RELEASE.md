# 📦 Guida al rilascio di Patch GUI

Questa guida accompagna i maintainer nella pubblicazione di una nuova release,
dalla preparazione dei pacchetti fino alla loro distribuzione su GitHub e PyPI.
Le istruzioni sono pensate per rimanere sincronizzate con la GUI e con la
documentazione principale: tieni sempre aperto anche il `CHANGELOG.md` mentre
procedi.

---

## 🔁 Ciclo di rilascio

1. **Raccogli le novità** completando le voci in `CHANGELOG.md` nella sezione
   *Non rilasciato*.
2. **Aggiorna la versione** in `pyproject.toml` e nel changelog quando decidi di
   pubblicare (rispetta il [SemVer](https://semver.org/lang/it/)).
3. **Esegui i test** automatici e manuali riportati qui sotto.
4. **Genera i pacchetti** (`sdist` e `wheel`) e verifica la loro integrità.
5. **Firma e pubblica** gli artifact su PyPI e crea la release GitHub con
   changelog e allegati.
6. **Annuncia** internamente l'uscita e apri la sezione *Non rilasciato* per la
   versione successiva.

---

## ✅ Checklist pre-release

- [ ] `CHANGELOG.md` aggiornato e coerente con il numero di versione.
- [ ] `README.md` e `USAGE.md` riletti per assicurarsi che non citino funzioni
      obsolete.
- [ ] Localizzazioni aggiornate (`python -m build_translations`).
- [ ] `pytest` eseguito con successo.
- [ ] Eventuali manuali o screenshot aggiornati (se necessario).

---

## 🛠️ Generare i pacchetti ufficiali

> Suggerimento: lavora all'interno di un ambiente virtuale pulito e assicurati
> di aver eseguito `git clean -fdx` se vuoi partire da zero.

Installa gli strumenti necessari una sola volta:

```bash
python -m pip install --upgrade build twine
```

Compila le traduzioni Qt e crea gli artifact distribuiti:

```bash
python -m build_translations
python -m build
```

Conferma che i file sotto `dist/` siano validi e installabili:

```bash
python -m twine check dist/*
python -m pip install --force-reinstall dist/patch_gui-<version>-py3-none-any.whl
patch-gui --help  # oppure "python -m patch_gui" per la GUI
```

> Dopo il test ricorda di rimuovere l'installazione dal virtualenv con
> `python -m pip uninstall patch-gui`.

---

## 🌐 Pubblicare su PyPI

1. Verifica di avere un token o credenziali valide (`~/.pypirc`).
2. Carica gli artifact con:

   ```bash
   python -m twine upload dist/*
   ```

3. Controlla la pagina del progetto su PyPI e prova `pip install patch-gui` da
   un ambiente pulito.

---

## 🚀 Creare la release GitHub

1. Crea e firma il tag, ad esempio:

   ```bash
   git tag -s v<version> -m "Patch GUI <version>"
   git push origin v<version>
   ```

2. Prepara la bozza della release includendo:
   - Titolo `Patch GUI <version>`.
   - Corpo con il changelog della versione.
   - Allegati: `patch-gui.exe` (se disponibile), `*.whl`, `*.tar.gz`.

3. Pubblica la release e verifica che il comando
   `patch-gui download-exe --tag v<version>` recuperi l'eseguibile corretto.

---

## 📅 Dopo il rilascio

- Aggiorna `CHANGELOG.md` creando una nuova sezione *Non rilasciato* vuota.
- Innalza la versione di sviluppo se necessario (es. `0.2.0.dev0`).
- Apri eventuali issue di follow-up emersi durante la release.
- Comunica sui canali interni/esterni il link alla release e a PyPI.

---

Questa checklist vive insieme alla documentazione del progetto: se noti passaggi
che possono essere automatizzati o semplificati, proponi un aggiornamento
aggiungendo sempre una nota nel changelog.
